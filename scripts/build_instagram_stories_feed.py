#!/usr/bin/env python3
"""Build a combined RSS feed from the followed accounts' Instagram stories.

Stories (the 24-hour posts) never appear in the profile timeline, and the
story REST endpoints are gated (HTML shell / CSRF pair). What works — same
pattern as the permalink enrichment (ticket 0015) — is fetching
``https://www.instagram.com/stories/<account>/`` with the
``INSTAGRAM_SESSIONID`` cookie: the page embeds a Relay preloader blob
holding ``result.data.xdt_api__v1__feed__reels_media.reels_media.items[]``,
the story media nodes with ``image_versions2`` / ``video_versions``,
``taken_at`` and ``expiring_at``.

Story nodes are identified by carrying media versions **and**
``expiring_at`` — feed posts never have an expiry, and the empty-shape
blob nests differently, so key-walking alone would give false negatives.

All accounts' stories land in one feed (``feeds/instagram-stories.xml``).
Items keep unique deep links and timestamped titles so the merge's
supersede filter cannot drop an older same-day story of the same account;
previous items stay until the item cap pushes them out, so readers that
poll after expiry still see them.

Fetch failures are soft per account; if every account fails, a rolling
"Feed build failed" item is written (tickets 0007/0008).

Usage: python scripts/build_instagram_stories_feed.py [account ...]
Optional env: INSTAGRAM_SESSIONID (required for live fetching)
              INSTAGRAM_STORIES_HTML=<file> (parse a saved page copy offline)
"""

import html as html_mod
import logging
import os
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
import build_instagram_feed as posts

MAX_ITEMS = 100
DELAY = 2

DEFAULT_ACCOUNTS = [
    "tiny_ruins",
    "martinmaleschka",
    "tumvlt",
    "jamborjoanna",
    "daxwerner",
    "thebeths",
    "susibumms",
    "waveybobson",
    "moritz.huertgen",
    "reinder_wijnveld",
    "ostmoderne_philokartie",
    "sveamaus",
    "betelsfoodfeast",
]

FEEDS_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "feeds")
)


def output_path() -> str:
    return os.path.join(FEEDS_DIR, "instagram-stories.xml")

log = logging.getLogger("build_instagram_stories_feed")


def feed_metadata(accounts: list[str]) -> dict:
    return {
        "feed_id": "https://www.instagram.com/",
        "title": "Instagram Stories",
        "link": "https://www.instagram.com/",
        "description": (
            "24-hour stories from followed accounts: " + ", ".join(accounts)
        ),
        "language": "en",
    }


def fetch_story_page(account: str) -> str:
    """Stories page HTML for one account via the session cookie."""
    session_id = os.environ.get("INSTAGRAM_SESSIONID")
    if not session_id:
        raise RuntimeError("stories need INSTAGRAM_SESSIONID")
    return common.fetch_direct(
        f"https://www.instagram.com/stories/{account}/",
        cookies={"sessionid": session_id},
    )


def _story_item(node: dict, account: str) -> dict:
    poster = posts._poster_url(node)
    video = posts._video_url(node)
    user = node.get("user") or {}
    name = user.get("full_name") or user.get("username") or account
    taken = node.get("taken_at")
    published = (
        datetime.fromtimestamp(taken, tz=timezone.utc) if taken else None
    )
    tray_url = f"https://www.instagram.com/stories/{account}/"
    pk = str(node.get("pk") or node.get("id") or "").split("_")[0]
    link = f"{tray_url}{pk}/" if pk else tray_url

    body = []
    if poster:
        body.append(f'<img src="{html_mod.escape(poster, quote=True)}" />')
    if video:
        body.append(
            f'<video controls preload="none" src="{html_mod.escape(video, quote=True)}">'
            "</video>"
        )
    expiry = ""
    expires = node.get("expiring_at")
    if expires:
        exp = datetime.fromtimestamp(expires, tz=timezone.utc)
        expiry = f" · expires {exp:%Y-%m-%d %H:%M} UTC"
    body.append(
        f'<p>Story by <a href="{tray_url}">{html_mod.escape(name)}</a>{expiry}</p>'
    )

    stamp = f" · {published:%Y-%m-%d %H:%M}" if published else ""
    item = {
        "id": node.get("id"),
        "title": f"Story by {name}{stamp}",
        "link": link,
        "description": "",
        "published": published,
        "content": "\n".join(body),
    }
    if video:
        item["enclosure"] = {"url": video, "type": "video/mp4", "length": 0}
    elif poster:
        item["enclosure"] = {"url": poster, "type": "image/jpeg", "length": 0}
    return item


def parse_stories_page(html: str, account: str) -> list[dict]:
    """Story items from one stories page, deduped by media id.

    A story node carries media versions and ``expiring_at``; feed posts
    and other media shapes don't, which keeps the walk across all JSON
    blobs specific.
    """
    items, seen = [], set()
    for blob in posts._iter_json_blobs(html):
        for node in posts._walk(blob):
            if not isinstance(node, dict) or node.get("expiring_at") is None:
                continue
            node_id = node.get("id")
            if not node_id or node_id in seen:
                continue
            if not (posts._video_url(node) or posts._poster_url(node)):
                continue
            seen.add(node_id)
            items.append(_story_item(node, account))
    log.info("stories parse: %d item(s) for %s", len(items), account)
    return items


def write_warning_feed(accounts: list[str], exc: Exception) -> int:
    return common.write_warning_feed(
        output_path(), MAX_ITEMS, "https://www.instagram.com/", exc,
        **feed_metadata(accounts),
    )


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    argv = sys.argv[1:] if argv is None else argv
    accounts = [posts.validate_account(a) for a in argv] or DEFAULT_ACCOUNTS

    offline_path = os.environ.get("INSTAGRAM_STORIES_HTML")
    if not offline_path and not os.environ.get("INSTAGRAM_SESSIONID"):
        return write_warning_feed(
            accounts, RuntimeError("stories need INSTAGRAM_SESSIONID")
        )
    out = output_path()

    items, failures = [], 0
    for index, account in enumerate(accounts):
        if index and not offline_path:
            time.sleep(DELAY)
        try:
            if offline_path:
                with open(offline_path, encoding="utf-8") as f:
                    html = f.read()
            else:
                html = fetch_story_page(account)
        except Exception as exc:  # noqa: BLE001
            failures += 1
            log.warning("stories fetch failed for %s (%s)", account, exc)
            continue
        items.extend(parse_stories_page(html, account))

    if failures and failures == len(accounts):
        return write_warning_feed(accounts, RuntimeError("all story fetches failed"))

    previous = common.load_previous(out)
    merged = common.merge_items(common.without_warning(previous), items)
    common.write_feed(list(merged.values()), out, MAX_ITEMS, **feed_metadata(accounts))
    return 0


if __name__ == "__main__":
    sys.exit(main())
