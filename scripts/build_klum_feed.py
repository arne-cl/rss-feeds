#!/usr/bin/env python3
"""Build an RSS feed from Günther Klum's news page (https://klum.com/news).

The page is a static Duda/1&1 website-builder site: news items are stacked
rows, each rendered twice (a mobile and a desktop variant) with slightly
different wording and — rarely — conflicting dates. Items are date + text,
optionally with a "MEHR INFORMATIONEN" button linking to YouTube or internal
pages. Some buttons point at media files on Duda's CDN (e.g. a WhatsApp
video mp4) with signed, expiring URLs; those are kept verbatim as the item
link AND exposed as an RSS <enclosure> — the weekly rebuild refreshes the
signature, so the URL stays live as long as the item is listed. Some items
have no button at all.

Item links therefore use the best stable URL available: the button href
(relative URLs resolved, mangled YouTube hosts normalized) with a fallback
to the news page itself. Item ids are always stable synthetic anchors:
https://www.klum.com/news#<YYYYMMDD>-<slug>.

Usage: python scripts/build_klum_feed.py
Optional env: KLUM_NEWS_HTML=<file> (parse a saved page copy offline)
"""

import os
import re
import sys
import html as html_module
import logging
import unicodedata
from datetime import datetime, timezone
from urllib.parse import urljoin

from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common

PAGE_URL = "https://www.klum.com/news"
FEED_TITLE = "Günther Klum News"
OUTPUT_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "feeds", "klum-news.xml")
)
MAX_ITEMS = 100
PAGES_DIR_ENV = "KLUM_PAGES_DIR"

DATE_RE = re.compile(r"(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})")
MOBILE_CLASSES = {"hide-for-large", "hide-for-medium"}
MEDIA_CDN_HOSTS = {"cdn.website-editor.net", "le-cdn.website-editor.net"}
MEDIA_TYPES = {
    ".mp4": "video/mp4",
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".mp3": "audio/mpeg",
}
MANGLED_YOUTUBE_HOSTS = {
    "www.yout-ube.com": "www.youtube.com",
    "yout-ube.com": "www.youtube.com",
    "www.you-tube.com": "www.youtube.com",
    "you-tube.com": "www.youtube.com",
}

log = logging.getLogger("build_klum_feed")


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------

def _norm(text: str) -> str:
    text = text.replace("\ufeff", " ")
    return re.sub(r"\s+", " ", text).strip()


def _squash(text: str) -> str:
    """Case/punctuation-insensitive key for title comparisons."""
    return common.squash(text)


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _title_overlap(a: str, b: str) -> bool:
    """True if the titles' word sets overlap heavily (Jaccard >= 0.5)."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return False
    return len(ta & tb) / len(ta | tb) >= 0.5


def _slugify(text: str) -> str:
    ascii_text = (
        unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    )
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
    return slug[:60].rstrip("-") or "item"


def _best_link(href: str) -> str:
    """Resolve a button href to an absolute URL (or the page URL)."""
    resolved = urljoin(PAGE_URL, href.strip())
    match = re.match(r"https?://([^/]+)", resolved)
    if not match:
        return PAGE_URL
    host = match.group(1).lower()
    if host in MANGLED_YOUTUBE_HOSTS:
        resolved = resolved.replace(match.group(1), MANGLED_YOUTUBE_HOSTS[host], 1)
    return resolved


def media_type(url: str) -> str:
    """MIME type guessed from the URL's file extension."""
    path = re.match(r"https?://[^/?#]+([^?#]*)", url)
    suffix = os.path.splitext(path.group(1).lower())[1] if path else ""
    return MEDIA_TYPES.get(suffix, "application/octet-stream")


def _is_media_url(url: str) -> bool:
    """True for Duda CDN file links (signed or not, real path required)."""
    match = re.match(r"https?://([^/?#]+)(/.+)", url)
    return bool(match and match.group(1).lower() in MEDIA_CDN_HOSTS)


def fetch_content_length(url: str) -> int:
    """Content-Length via HEAD request (0 when unavailable)."""
    r = common.creq.head(url, impersonate="chrome", timeout=30, allow_redirects=True)
    r.raise_for_status()
    return int(r.headers.get("Content-Length") or 0)


def attach_media_lengths(items: list[dict]) -> None:
    """Fill enclosure lengths via HEAD requests (best effort)."""
    for item in items:
        enclosure = item.get("enclosure")
        if not enclosure:
            continue
        try:
            enclosure["length"] = fetch_content_length(enclosure["url"])
        except Exception as exc:  # noqa: BLE001
            log.warning("no Content-Length for %s: %s", enclosure["url"], exc)


def _extract(html: str, mobile: bool) -> list[dict]:
    """Collect candidate items from the mobile or desktop row variants.

    Within a column, consecutive paragraphs belong to one item; a paragraph
    starting with a date begins a new item (some items are split across a
    date-only paragraph and title paragraphs, others carry body text in
    extra headings).
    """
    soup = BeautifulSoup(html, "html.parser")
    items = []
    seen_cols = set()
    for row in soup.select("div.dmRespRow"):
        if (bool(MOBILE_CLASSES & set(row.get("class", [])))) != mobile:
            continue
        for col in row.select("div.dmRespCol"):
            if id(col) in seen_cols:
                continue
            seen_cols.add(id(col))
            groups: list[dict] = []
            for child in col.children:
                name = getattr(child, "name", None)
                if name == "div" and "dmNewParagraph" in child.get("class", []):
                    text = _norm(child.get_text(" ", strip=True))
                    if not text:
                        continue
                    if DATE_RE.match(text) or not groups:
                        groups.append({"texts": [text], "links": []})
                    else:
                        groups[-1]["texts"].append(text)
                elif name == "a" and child.get("href"):
                    if groups:
                        groups[-1]["links"].append(child["href"])
                    else:
                        groups.append({"texts": [], "links": [child["href"]]})
            for group in groups:
                text = _norm(" ".join(group["texts"]))
                if not text:
                    continue
                date_match = DATE_RE.match(text)
                if date_match:
                    published = datetime(
                        int(date_match.group(3)),
                        int(date_match.group(2)),
                        int(date_match.group(1)),
                        tzinfo=timezone.utc,
                    )
                    title = _norm(text[date_match.end():])
                else:
                    published, title = None, text
                if not title:
                    continue
                link = PAGE_URL
                media = None
                for href in group["links"]:
                    candidate = _best_link(href)
                    if media is None and _is_media_url(candidate):
                        media = candidate
                    if link == PAGE_URL and candidate != PAGE_URL:
                        link = candidate
                items.append(
                    {
                        "published": published,
                        "title": title,
                        "link": link,
                        "media": media,
                    }
                )
    return items


def _is_copy_of(candidate: dict, other: dict) -> bool:
    """True if candidate is a responsive duplicate of an already kept item."""
    if other["published"] and candidate["published"]:
        if f"{other['published']:%d.%m.}" != f"{candidate['published']:%d.%m.}":
            return False
    elif not (other["published"] or candidate["published"]):
        pass
    else:
        return False
    if _squash(other["title"]) == _squash(candidate["title"]):
        return True
    if (
        other["title"].lower().split()[:4] == candidate["title"].lower().split()[:4]
        and candidate["published"]
    ):
        return True
    if (
        other["link"] == candidate["link"] != PAGE_URL
        and candidate["published"]
    ):
        return True
    # responsive variants can word the same post very differently
    # ("Oktoberfest 2026 im Gasthaus ZUM HORN" vs "Oktoberfest im Gasthaus
    # Zum Horn in Bergisch Gladbach"); same date + heavy word overlap
    if (
        other["published"]
        and candidate["published"]
        and _title_overlap(other["title"], candidate["title"])
    ):
        return True
    return False


def parse_klum(html: str) -> list[dict]:
    desktop = _extract(html, mobile=False)
    mobile = _extract(html, mobile=True)
    log.info("desktop rows: %d item(s), mobile rows: %d item(s)", len(desktop), len(mobile))

    used = set()
    for item in desktop:
        if item["published"] is None:
            for idx, candidate in enumerate(mobile):
                if idx in used or candidate["published"] is None:
                    continue
                short_other = candidate["title"].lower()[:25]
                short_own = item["title"].lower()[:25]
                if item["title"].lower().startswith(short_other) or candidate[
                    "title"
                ].lower().startswith(short_own):
                    item["published"] = candidate["published"]
                    used.add(idx)
                    break

    candidates = desktop + [m for i, m in enumerate(mobile) if i not in used]
    kept = []
    for candidate in candidates:
        copy_of = next(
            (other for other in kept if _is_copy_of(candidate, other)), None
        )
        if copy_of is not None:
            # the desktop rendering sometimes points at a Duda alias
            # (/empty-page<id>) while the mobile one has the canonical slug
            if "/empty-page" in copy_of["link"] and "/empty-page" not in candidate["link"]:
                copy_of["link"] = candidate["link"]
            continue
        kept.append(candidate)

    items = []
    for item in kept:
        date_part = (
            f"{item['published']:%Y%m%d}" if item["published"] else "undated"
        )
        anchor = f"{PAGE_URL}#{date_part}-{_slugify(item['title'])}"
        entry = {
            "id": anchor,
            "title": item["title"],
            "link": item["link"],
            "description": item["title"],
            "published": item["published"],
        }
        if item.get("media"):
            entry["enclosure"] = {
                "url": item["media"],
                "type": media_type(item["media"]),
                "length": 0,  # filled by attach_media_lengths in live runs
            }
        items.append(entry)
    log.info("parsed %d unique item(s)", len(items))
    return items


def prune_superseded(merged: dict[str, dict], items: list[dict]) -> dict[str, dict]:
    """Drop previously stored entries the current parse merged away.

    After an id-scheme migration or a dedup-rule change the previous feed
    can still hold entries (e.g. a responsive variant under its own anchor
    id) that duplicate a freshly parsed item.
    """
    new_ids = {item["id"] for item in items}
    return {
        key: entry
        for key, entry in merged.items()
        if key in new_ids
        or not any(_is_copy_of(entry, item) for item in items)
    }


# --------------------------------------------------------------------------
# Article content embedding
# --------------------------------------------------------------------------

BLOCK_TAGS = ["p", "h1", "h2", "h3", "h4", "h5", "h6"]
KLUM_HOSTS = {"www.klum.com", "klum.com"}


def fetch_article(link: str) -> str:
    """Fetch an article page (kept separate so tests can stub it)."""
    return common.fetch_direct(link)


def is_embeddable_page(link: str) -> bool:
    """True for internal klum.com article pages worth embedding.

    Excludes the news index itself, YouTube links and .pdfx viewer pages.
    Duda empty-page aliases are included — they serve real content.
    """
    if link == PAGE_URL:
        return False
    match = re.match(r"https?://([^/?#]+)([^?#]*)", link)
    if not match:
        return False
    host = match.group(1).lower()
    path = match.group(2)
    if host not in KLUM_HOSTS:
        return False
    if path in ("", "/news", "/news/"):
        return False
    if ".pdfx" in path:
        return False
    return True


def extract_page_content(page_html: str) -> str | None:
    """Article HTML (simple <p> blocks) from a Duda page, or None.

    Duda renders article text inside div.dmNewParagraph containers;
    everything else (menu, footer, boilerplate) lives outside them.
    """
    soup = BeautifulSoup(page_html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    blocks = []
    for par in soup.select("div.dmNewParagraph"):
        for block in par.find_all(BLOCK_TAGS):
            if block.find(BLOCK_TAGS):
                continue  # container block; its children are listed too
            for br in block.find_all("br"):
                br.replace_with("\n")
            for part in block.get_text().split("\n"):
                text = _norm(part)
                if text:
                    blocks.append(text)
    if not blocks:
        return None
    return "<p>" + "</p><p>".join(html_module.escape(b) for b in blocks) + "</p>"


def _local_page_path(link: str) -> str | None:
    """Path of a saved page copy for link inside $KLUM_PAGES_DIR."""
    match = re.match(r"https?://[^/?#]+([^?#]*)", link)
    if not match:
        return None
    segment = match.group(1).rstrip("/").rsplit("/", 1)[-1]
    if not segment:
        return None
    return os.path.join(os.environ[PAGES_DIR_ENV], segment + ".html")


def embed_content(items: list[dict], previous: dict[str, dict]) -> None:
    """Attach article HTML ("content") to items linking to internal pages.

    Content is cached inside the feed itself: entries loaded from the
    previous feed carry their content, so already-fetched pages are never
    requested again. With KLUM_PAGES_DIR set, only saved page copies are
    used (offline mode — no requests at all).
    """
    by_id = {entry["id"]: entry for entry in previous.values()}
    by_link = {entry["link"]: entry for entry in previous.values()}
    offline_dir = os.environ.get(PAGES_DIR_ENV)
    embedded = 0
    for item in items:
        link = item["link"]
        if not is_embeddable_page(link):
            continue
        old = by_id.get(item["id"]) or by_link.get(link)
        if old and old.get("content"):
            item["content"] = old["content"]
            continue
        page_html = None
        if offline_dir:
            path = _local_page_path(link)
            if path and os.path.exists(path):
                with open(path, encoding="utf-8") as f:
                    page_html = f.read()
        else:
            try:
                page_html = fetch_article(link)
            except Exception as exc:  # noqa: BLE001
                log.warning("could not fetch %s: %s", link, exc)
        if not page_html:
            continue
        content = extract_page_content(page_html)
        if content:
            item["content"] = content
            embedded += 1
    log.info("embedded article content for %d item(s)", embedded)


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    kwargs = dict(
        feed_id=PAGE_URL,
        title=FEED_TITLE,
        link=PAGE_URL,
        description=f"News von Günther Klum (auto-generated from {PAGE_URL})",
        language="de",
    )

    try:
        html, _source = common.fetch_page(PAGE_URL, "KLUM_NEWS_HTML")
    except Exception as exc:  # noqa: BLE001
        return common.write_warning_feed(OUTPUT_PATH, MAX_ITEMS, PAGE_URL, exc, **kwargs)

    previous = common.load_previous(OUTPUT_PATH)
    items = parse_klum(html)
    if not items:
        exc = RuntimeError(
            "no news items parsed — page layout may have changed; keeping previous feed"
        )
        return common.write_warning_feed(OUTPUT_PATH, MAX_ITEMS, PAGE_URL, exc, **kwargs)

    embed_content(items, previous)
    attach_media_lengths(items)
    merged = common.merge_items(
        common.without_warning(previous), items
    )
    merged = prune_superseded(merged, items)
    common.write_feed(list(merged.values()), OUTPUT_PATH, MAX_ITEMS, **kwargs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
