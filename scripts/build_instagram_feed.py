#!/usr/bin/env python3
"""Build an RSS feed from an Instagram profile page.

Instagram provides no feeds and blocks most scrapers, so this script:

1. With ``INSTAGRAM_SESSIONID`` set, fetches the private ``web_profile_info``
   JSON API first and parses the timeline edges (shortcodes, captions,
   timestamps, media URLs, and every slide of carousel posts). This data is
   strictly richer than the profile page's, so it is preferred when available.
2. Falls back to a direct fetch of ``https://www.instagram.com/<account>/``
   with Chrome TLS impersonation (curl_cffi) and parses the media objects
   embedded in the page's ``<script type="application/json">`` blobs (post
   shortcode, caption text, cover image, and a date string inside
   accessibility_caption).
3. Falls back to the r.jina.ai reader proxy and parses the rendered DOM
   (post links, image alt texts as titles).

Carousel posts embed one ``<img>`` per slide in the item content; the RSS
enclosure is the first slide. Video slides show a poster image plus a
``<video controls>`` tag. A fresh parse never overwrites richer content
stored by an earlier build (e.g. after a sessionid expiry).

The profile page only shows the latest few posts, so newly parsed items are
merged into the previous feed file to keep history and preserve dates.

Soft failures (fetch, fallback fetch, unparseable page) do not abort with a
non-zero exit: they are recorded as a rolling "Feed build failed" item
(error + stacktrace) inside the feed, keeping all previous items, so feed
subscribers can see the breakage. The next successful build removes that
item again.

Usage: python scripts/build_instagram_feed.py <account>
Optional env: JINA_API_KEY (avoids r.jina.ai rate limits on shared IPs)
              INSTAGRAM_SESSIONID (web_profile_info API fallback)
              INSTAGRAM_PROFILE_HTML=<file> (parse a saved page copy offline)
"""

import html as html_mod
import json
import os
import re
import sys
import logging
import time
from datetime import datetime, timezone

from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common

ACCOUNT_RE = re.compile(r"^[A-Za-z0-9._]{1,30}$")
POST_URL_RE = re.compile(r"https://www\.instagram\.com/p/([A-Za-z0-9_-]{5,})/?")
ACCESSIBILITY_DATE_RE = re.compile(r"on (\w+ \d{1,2}, \d{4})")
TITLE_MAX_LEN = 80
MAX_ITEMS = 100

FEEDS_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "feeds")
)

log = logging.getLogger("build_instagram_feed")


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

def validate_account(account) -> str:
    """Return the account if it is a plausible Instagram username, else raise."""
    if not isinstance(account, str) or not ACCOUNT_RE.match(account):
        raise ValueError(f"invalid Instagram account: {account!r}")
    return account


def instagram_url(account: str) -> str:
    return f"https://www.instagram.com/{account}/"


def output_path(account: str) -> str:
    return os.path.join(FEEDS_DIR, f"instagram-{account.lower()}.xml")


# --------------------------------------------------------------------------
# Fetching
# --------------------------------------------------------------------------

IG_APP_ID = "936619743392459"
API_PROFILE_URL = (
    "https://www.instagram.com/api/v1/users/web_profile_info/?username={account}"
)


def _payload_node_lists(payload: dict) -> list[list]:
    """Media node lists from the known API response shapes.

    web_profile_info nests edges under data.user.edge_owner_to_timeline_media;
    the (sniffed) app GraphQL uses data.xdt_api__v1__feed__user_timeline_graphql_connection.
    """
    data = payload.get("data") or {}
    lists = []
    media = (data.get("user") or {}).get("edge_owner_to_timeline_media")
    if isinstance(media, dict) and media.get("edges"):
        lists.append(media["edges"])
    for key in ("xdt_api__v1__feed__user_timeline_graphql_connection",):
        conn = data.get(key)
        if isinstance(conn, dict) and conn.get("edges"):
            lists.append(conn["edges"])
    return lists


def _poster_url(node: dict) -> str:
    return (
        node.get("display_url")
        or node.get("display_uri")
        or ((node.get("image_versions2") or {}).get("candidates") or [{}])[0].get("url")
        or ""
    )


def _video_url(node: dict) -> str:
    if node.get("video_url"):
        return node["video_url"]
    vv = node.get("video_versions") or []
    if vv and isinstance(vv[0], dict) and vv[0].get("url"):
        return vv[0]["url"]
    return ""


def _api_media_url(node: dict) -> str:
    return _video_url(node) or _poster_url(node)


def _carousel_children(node: dict) -> list[dict]:
    """Child media dicts of a carousel, in slide order, in any known shape."""
    children = node.get("carousel_media")
    if isinstance(children, list) and children:
        return [c for c in children if isinstance(c, dict)]
    edges = (node.get("edge_sidecar_to_children") or {}).get("edges") or []
    nodes = [(e or {}).get("node") or {} for e in edges]
    return [n for n in nodes if n]


def _slide_html(child: dict) -> str:
    """Poster <img> plus a <video controls> tag for video slides."""
    parts = []
    poster = _poster_url(child)
    alt = child.get("accessibility_caption") or ""
    if poster:
        alt_attr = f' alt="{html_mod.escape(alt, quote=True)}"' if alt else ""
        parts.append(f'<img src="{html_mod.escape(poster, quote=True)}"{alt_attr} />')
    video = _video_url(child)
    if video:
        parts.append(
            f'<video controls preload="none" src="{html_mod.escape(video, quote=True)}">'
            "</video>"
        )
    return "\n".join(parts)


def _item_content(post_url: str, caption: str, slides: list[dict]) -> str:
    escaped_caption = html_mod.escape(caption).replace("\n", "<br>")
    body = "\n".join(html for html in (_slide_html(s) for s in slides) if html)
    return (
        f"{body}\n"
        f"<p>{escaped_caption}</p>\n"
        f'<p><a href="{post_url}">View on Instagram</a></p>'
    )


def fetch_api_profile(account: str) -> str | None:
    """web_profile_info JSON via the INSTAGRAM_SESSIONID cookie, or None.

    429 throttles get a bounded backoff (10s, 30s); other errors and a
    still-throttled session after the last retry raise immediately so
    main() can fall back to the weaker parses.
    """
    session_id = os.environ.get("INSTAGRAM_SESSIONID")
    if not session_id:
        return None
    headers = {"x-ig-app-id": IG_APP_ID, "Accept": "application/json"}
    url = API_PROFILE_URL.format(account=account)
    delays = (10, 30)
    for attempt in range(len(delays) + 1):
        try:
            return common.fetch_direct(
                url, cookies={"sessionid": session_id}, headers=headers
            )
        except Exception as exc:  # noqa: BLE001
            if common.status_of(exc) != 429 or attempt == len(delays):
                raise
            log.warning(
                "web_profile_info 429 for %s, retrying in %ds",
                account,
                delays[attempt],
            )
            time.sleep(delays[attempt])
    raise RuntimeError("unreachable")


# --------------------------------------------------------------------------
# Parsing strategy 1: direct HTML with embedded JSON
# --------------------------------------------------------------------------

def _iter_json_blobs(html: str):
    for sm in re.finditer(r'<script type="application/json"[^>]*>(.*?)</script>', html, re.S):
        try:
            yield json.loads(sm.group(1))
        except ValueError:
            continue


def _walk(root):
    stack = [root]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            yield node
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)


def parse_accessibility_date(text):
    """Parse 'Photo by X on September 23, 2026.' style captions."""
    if not text:
        return None
    m = ACCESSIBILITY_DATE_RE.search(text)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%B %d, %Y").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _media_kind(media_type) -> str:
    return {1: "Photo", 2: "Video", 8: "Carousel"}.get(media_type, "Post")


def _item_title(code: str, caption: str, media_type) -> str:
    first_line = re.sub(r"\s+", " ", caption.split("\n", 1)[0]).strip()
    if not first_line:
        return f"{_media_kind(media_type)} {code}"
    if len(first_line) > TITLE_MAX_LEN:
        first_line = first_line[: TITLE_MAX_LEN - 1].rstrip() + "…"
    return first_line


def _item_from_node(node: dict):
    code = node.get("code")
    if not code:
        return None
    url = f"https://www.instagram.com/p/{code}/"
    caption = (node.get("caption") or {}).get("text") or ""
    item = {
        "id": url,
        "title": _item_title(code, caption, node.get("media_type")),
        "link": url,
        "description": caption,
        "published": parse_accessibility_date(node.get("accessibility_caption")),
    }
    children = _carousel_children(node)
    slides = children or [node]
    first = slides[0]
    media_url = _poster_url(first) or _poster_url(node)
    if media_url:
        item["enclosure"] = {"url": media_url, "type": "image/jpeg", "length": 0}
        item["content"] = _item_content(url, caption, slides)
    return item


def parse_direct(html: str) -> list[dict]:
    items, seen = [], set()
    for blob in _iter_json_blobs(html):
        for node in _walk(blob):
            if "__isXIGPolarisMedia" not in node:
                continue
            code = node.get("code")
            if not code or code in seen:
                continue
            seen.add(code)
            item = _item_from_node(node)
            if item:
                items.append(item)
    log.info("direct JSON parse: %d post(s)", len(items))
    return items


# --------------------------------------------------------------------------
# Parsing strategy 2: web_profile_info API JSON (sessionid cookie)
# --------------------------------------------------------------------------

def _api_caption(node: dict) -> str:
    caption = node.get("caption")
    if isinstance(caption, dict) and caption.get("text"):
        return caption["text"]
    edges = (node.get("edge_media_to_caption") or {}).get("edges") or []
    if edges and isinstance(edges[0], dict):
        return (edges[0].get("node") or {}).get("text") or ""
    return ""


def _api_item(node: dict) -> dict | None:
    code = node.get("shortcode") or node.get("code")
    if not code:
        return None
    url = f"https://www.instagram.com/p/{code}/"
    caption = _api_caption(node)

    published = None
    taken = node.get("taken_at_timestamp") or node.get("taken_at")
    if isinstance(taken, (int, float)):
        published = datetime.fromtimestamp(taken, tz=timezone.utc)

    children = _carousel_children(node)
    slides = children or [node]
    first = slides[0]
    media_url = _api_media_url(first) or _api_media_url(node)
    item = {
        "id": url,
        "title": _item_title(code, caption, node.get("media_type")),
        "link": url,
        "description": caption,
        "published": published,
    }
    if media_url:
        is_video = bool(_video_url(first))
        item["enclosure"] = {
            "url": media_url,
            "type": "video/mp4" if is_video else "image/jpeg",
            "length": 0,
        }
        item["content"] = _item_content(url, caption, slides)
    return item


def parse_api(text: str) -> list[dict]:
    try:
        payload = json.loads(text)
    except ValueError:
        payload = None
    if not isinstance(payload, dict):
        return []
    items, seen = [], set()
    for edges in _payload_node_lists(payload):
        for edge in edges:
            node = edge.get("node") if isinstance(edge, dict) else None
            item = _api_item(node) if node else None
            if item and item["id"] not in seen:
                seen.add(item["id"])
                items.append(item)
    log.info("api JSON parse: %d post(s)", len(items))
    return items


# --------------------------------------------------------------------------
# Parsing strategy 2: rendered DOM (jina reader HTML)
# --------------------------------------------------------------------------

def parse_dom(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    items, seen = [], set()
    for a in soup.find_all("a", href=True):
        m = POST_URL_RE.match(a["href"])
        if not m or m.group(1) in seen:
            continue
        code = m.group(1)
        seen.add(code)
        img = a.find("img", alt=True)
        title = (img["alt"] if img else "") or a.get_text(" ", strip=True)
        if not title:
            title = f"Post {code}"
        items.append(
            {
                "id": a["href"],
                "title": title,
                "link": a["href"],
                "description": "",
                "published": None,
            }
        )
    log.info("DOM parse: %d post(s)", len(items))
    return items


# --------------------------------------------------------------------------
# Profile metadata
# --------------------------------------------------------------------------

def _content_images(content: str | None) -> int:
    return content.count("<img") if content else 0


def restore_richer_content(items: list[dict], previous: dict[str, dict]) -> None:
    """Keep the stored content/enclosure when a fresh parse saw fewer slides.

    E.g. after a sessionid expiry the direct parse only sees carousel covers;
    the previously stored API content must survive the merge instead of being
    overwritten by the weaker reparse.
    """
    for item in items:
        old = previous.get(item["id"])
        if not old:
            continue
        if _content_images(old.get("content")) > _content_images(item.get("content")):
            item["content"] = old["content"]
            if old.get("enclosure"):
                item["enclosure"] = old["enclosure"]


def profile_metadata(html: str) -> dict:
    for blob in _iter_json_blobs(html):
        for node in _walk(blob):
            if "username" in node and ("full_name" in node or "all_media_count" in node):
                meta = {
                    "username": node.get("username") or "",
                    "full_name": node.get("full_name") or "",
                    "biography": node.get("biography") or "",
                }
                if meta["username"]:
                    return meta
    return {}


# --------------------------------------------------------------------------
# Feed failure warning + metadata
# --------------------------------------------------------------------------

def previous_feed_metadata(out: str) -> dict:
    """Channel-level title/description of the previous feed file, if any."""
    if not os.path.exists(out):
        return {}
    try:
        with open(out, encoding="utf-8") as f:
            soup = BeautifulSoup(f.read(), "xml")
    except Exception as exc:  # noqa: BLE001
        log.warning("could not parse previous feed metadata (%s)", exc)
        return {}
    title = soup.find("title")
    description = soup.find("description")
    if title is None:
        return {}
    return {
        "title": title.get_text(" ", strip=True),
        "description": description.get_text(" ", strip=True) if description else "",
    }


def _feed_kwargs(account: str, meta: dict) -> dict:
    """write_feed metadata derived from profile meta, falling back to the
    previous feed's channel metadata (which failure builds don't have)."""
    url = instagram_url(account)
    prev = previous_feed_metadata(output_path(account))
    name = meta.get("full_name") or account
    title = f"{name} on Instagram"
    if not meta.get("full_name") and prev.get("title"):
        title = prev["title"]
    description = (
        meta.get("biography")
        or prev.get("description")
        or f"Instagram posts by {name} (auto-generated from {url})"
    )
    return {
        "feed_id": url,
        "title": title,
        "link": url,
        "description": description,
        "language": "en",
    }


def write_warning_feed(account: str, exc: Exception) -> int:
    """Record a failed build as an item in the feed, keeping previous items."""
    return common.write_warning_feed(
        output_path(account),
        MAX_ITEMS,
        instagram_url(account),
        exc,
        **_feed_kwargs(account, {}),
    )


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print(f"usage: {os.path.basename(sys.argv[0])} <account>", file=sys.stderr)
        return 2
    try:
        account = validate_account(argv[0])
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    url = instagram_url(account)
    out = output_path(account)
    offline = bool(os.environ.get("INSTAGRAM_PROFILE_HTML"))
    try:
        page, source = common.fetch_page(url, "INSTAGRAM_PROFILE_HTML")
    except Exception as exc:  # noqa: BLE001
        return write_warning_feed(account, exc)

    # The session API data is strictly richer (exact dates, captions, and all
    # carousel slides — profile-page JSON only carries the cover), so prefer
    # it whenever a session cookie is configured.
    items = []
    if not offline and os.environ.get("INSTAGRAM_SESSIONID"):
        try:
            api_text = fetch_api_profile(account)
            items = parse_api(api_text) if api_text is not None else []
        except Exception as exc:  # noqa: BLE001
            log.warning("session api fetch failed (%s)", exc)
    if not items:
        items = parse_direct(page)
    if not items and not offline:
        if source == "direct":
            try:
                page = common.fetch_jina(url)
            except Exception as exc:  # noqa: BLE001
                return write_warning_feed(account, exc)
        items = parse_dom(page)

    if not items:
        try:
            raise RuntimeError(
                "no posts parsed — page layout may have changed; keeping previous feed"
            )
        except RuntimeError as exc:
            return write_warning_feed(account, exc)

    meta = profile_metadata(page)
    previous = common.load_previous(out)
    restore_richer_content(items, common.without_warning(previous))
    merged = common.merge_items(common.without_warning(previous), items)
    common.write_feed(list(merged.values()), out, MAX_ITEMS, **_feed_kwargs(account, meta))
    return 0


if __name__ == "__main__":
    sys.exit(main())
