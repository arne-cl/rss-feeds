#!/usr/bin/env python3
"""Build a podcast feed for BRF1's "Chansons, Lieder und Folk" show.

The show (mondays 20-21h, https://1.brf.be/sendungen/chansons/) is not
published as a podcast by BRF. The archive page lists episode cards (plus a
"Sendungsprofil" teaser with the two newest episodes, which do not repeat in
the archive list below). Each episode page embeds an audio player whose
inline JS loads https://streaming2.brf.be/play/<hash>; that endpoint returns
a snippet with a stable direct MP3 URL, used as the RSS <enclosure>.

Usage: python scripts/build_brf_chansons_feed.py
Optional env: CHANSONS_HTML=<file> (parse a saved archive copy offline),
CHANSONS_PAGES_DIR=<dir> (saved episode pages, offline mode),
CHANSONS_PLAY_DIR=<dir> (saved play-endpoint snippets, offline mode).
"""

import html as html_module
import os
import re
import sys
import logging
from datetime import datetime
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common

SHOW_URL = "https://1.brf.be/sendungen/chansons/"
FEED_TITLE = "Chansons, Lieder und Folk (BRF1)"
OUTPUT_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "feeds", "brf1-chansons.xml")
)
MAX_ITEMS = 100
ARCHIVE_HTML_ENV = "CHANSONS_HTML"
PAGES_DIR_ENV = "CHANSONS_PAGES_DIR"
PLAY_DIR_ENV = "CHANSONS_PLAY_DIR"
PLAY_URL_RE = re.compile(r"https://streaming2\.brf\.be/play/([0-9a-f]+)")
EPISODE_URL_RE = re.compile(
    r"^https://1\.brf\.be/sendungen/chansons/(\d+)/?$"
)
BRF_TZ = ZoneInfo("Europe/Brussels")

log = logging.getLogger("build_brf_chansons_feed")


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


# --------------------------------------------------------------------------
# Archive page
# --------------------------------------------------------------------------

def parse_archive(html: str) -> list[dict]:
    """Episode entries from the archive page (teaser + archive cards).

    The two newest episodes only appear in the "Sendungsprofil" teaser at
    the top, not in the archive card list; both sections are parsed and
    deduplicated by episode id.
    """
    soup = BeautifulSoup(html, "html.parser")
    items = []
    seen = set()
    for card in soup.select(".card-item a.inner-card[href]"):
        match = EPISODE_URL_RE.match(urljoin(SHOW_URL, card["href"]))
        if not match:
            continue
        episode_id = match.group(1)
        if episode_id in seen:
            continue
        title_el = card.select_one("h4.card-title")
        time_el = card.select_one(".datetime-wrapper time[datetime]")
        if title_el is None or time_el is None:
            continue
        excerpt_el = card.select_one(".content-wrapper p")
        img_el = card.select_one("img[data-src]")
        # feedgen only accepts .jpg/.png for itunes:image
        image = img_el["data-src"] if img_el else ""
        if not image.lower().endswith((".jpg", ".png")):
            image = ""
        seen.add(episode_id)
        items.append(
            {
                "id": urljoin(SHOW_URL, f"{episode_id}/"),
                "title": _norm(title_el.get_text(" ", strip=True)),
                "link": urljoin(SHOW_URL, f"{episode_id}/"),
                "description": _norm(excerpt_el.get_text(" ", strip=True))
                if excerpt_el
                else "",
                "published": datetime.strptime(
                    time_el["datetime"].strip(), "%Y-%m-%d %H:%M"
                ).replace(tzinfo=BRF_TZ),
                "image": image,
            }
        )
    items.sort(key=lambda item: item["published"], reverse=True)
    log.info("parsed %d episode(s) from archive", len(items))
    return items


# --------------------------------------------------------------------------
# Episode page + play endpoint
# --------------------------------------------------------------------------

def parse_episode(html: str) -> dict:
    """Content, excerpt and audio play hash from an episode page.

    The play hash sits inside an inline script tag (the player stub loads
    https://streaming2.brf.be/play/<hash> via jQuery.get), so it must be
    extracted from the raw HTML before scripts are stripped.
    """
    match = PLAY_URL_RE.search(html)
    play_hash = match.group(1) if match else None

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()

    blocks = []
    article = soup.select_one("section.classic-content article")
    if article:
        for par in article.find_all("p"):
            text = _norm(par.get_text(" ", strip=True))
            if text:
                blocks.append(text)
    content = (
        "<p>" + "</p><p>".join(html_module.escape(b) for b in blocks) + "</p>"
        if blocks
        else None
    )

    excerpt_el = soup.select_one("p.excerpt.under-title")
    excerpt = (
        _norm(excerpt_el.get_text(" ", strip=True)) if excerpt_el else None
    )
    return {"play_hash": play_hash, "content": content, "excerpt": excerpt}


def resolve_audio(play_html: str) -> dict | None:
    """Audio URL + MIME type from a streaming2.brf.be/play/ snippet."""
    soup = BeautifulSoup(play_html, "html.parser")
    source = soup.select_one("audio source[src]") or soup.select_one(
        "[data-src]"
    )
    if source is None or not source.get("src") and not source.get("data-src"):
        return None
    url = source.get("src") or source.get("data-src")
    return {"url": url, "type": source.get("type") or "audio/mpeg"}


# --------------------------------------------------------------------------
# Enrichment (episode pages, audio resolution, lengths)
# --------------------------------------------------------------------------

def fetch_episode_page(link: str) -> str:
    """Fetch an episode page (kept separate so tests can stub it)."""
    return common.fetch_direct(link)


def fetch_play_snippet(play_url: str) -> str:
    """Fetch a streaming2.brf.be/play/ snippet (stub in tests)."""
    return common.fetch_direct(play_url)


def _read_local_copy(path: str | None) -> str | None:
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return f.read()
    return None


def _episode_local_path(link: str) -> str | None:
    match = EPISODE_URL_RE.match(link)
    if not match:
        return None
    return os.path.join(os.environ[PAGES_DIR_ENV], match.group(1) + ".html")


def _play_local_path(play_hash: str) -> str:
    return os.path.join(os.environ[PLAY_DIR_ENV], play_hash + ".html")


def enrich_items(items: list[dict], previous: dict[str, dict]) -> None:
    """Attach article content and the audio enclosure to items.

    Everything is cached inside the feed itself: items whose previous entry
    already carries content and an enclosure are not fetched again. With
    CHANSONS_PAGES_DIR / CHANSONS_PLAY_DIR set, only saved page copies are
    used (offline mode — no requests at all).
    """
    by_id = {entry["id"]: entry for entry in previous.values()}
    enriched = 0
    for item in items:
        old = by_id.get(item["id"])
        if old and old.get("content") and old.get("enclosure"):
            item["content"] = old["content"]
            item["enclosure"] = old["enclosure"]
            item["description"] = old.get("description") or item["description"]
            continue

        page_html = None
        if os.environ.get(PAGES_DIR_ENV):
            page_html = _read_local_copy(_episode_local_path(item["link"]))
        else:
            try:
                page_html = fetch_episode_page(item["link"])
            except Exception as exc:  # noqa: BLE001
                log.warning("could not fetch %s: %s", item["link"], exc)
        if not page_html:
            continue
        parsed = parse_episode(page_html)
        if parsed["excerpt"]:
            item["description"] = parsed["excerpt"]
        if parsed["content"]:
            item["content"] = parsed["content"]

        if not parsed["play_hash"]:
            continue
        play_html = None
        if os.environ.get(PLAY_DIR_ENV):
            play_html = _read_local_copy(_play_local_path(parsed["play_hash"]))
        else:
            play_url = f"https://streaming2.brf.be/play/{parsed['play_hash']}"
            try:
                play_html = fetch_play_snippet(play_url)
            except Exception as exc:  # noqa: BLE001
                log.warning("could not fetch %s: %s", play_url, exc)
        if not play_html:
            continue
        audio = resolve_audio(play_html)
        if audio:
            item["enclosure"] = {**audio, "length": 0}
            enriched += 1
    log.info("resolved audio for %d item(s)", enriched)


def fetch_content_length(url: str) -> int:
    """Content-Length via HEAD request (0 when unavailable)."""
    r = common.creq.head(url, impersonate="chrome", timeout=30)
    r.raise_for_status()
    return int(r.headers.get("Content-Length") or 0)


def attach_audio_lengths(items: list[dict]) -> None:
    """Fill enclosure lengths via HEAD requests (best effort)."""
    for item in items:
        enclosure = item.get("enclosure")
        if not enclosure or enclosure.get("length"):
            continue
        try:
            enclosure["length"] = fetch_content_length(enclosure["url"])
        except Exception as exc:  # noqa: BLE001
            log.warning("no Content-Length for %s: %s", enclosure["url"], exc)


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

SHOW_DESCRIPTION = (
    "Eine Sendung, die, wenn es sie nicht schon seit über 30 Jahren geben "
    "würde, für Ostbelgien erfunden werden müsste. Am Schnittpunkt der "
    "Kulturen stellt der BRF französische Chansons, deutschsprachige Lieder "
    "und internationale Folk- und Worldmusic vor. Montag, 20 - 21 Uhr."
)
SHOW_IMAGE = (
    "https://1.brf.be/wp-content/uploads/sites/2/2015/06/CLF-1420x968.jpg"
)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    try:
        html, _source = common.fetch_page(SHOW_URL, ARCHIVE_HTML_ENV)
    except Exception as exc:  # noqa: BLE001
        log.error("fetch failed: %s", exc)
        return 1

    previous = common.load_previous(OUTPUT_PATH)
    items = parse_archive(html)
    if not items:
        log.error(
            "no episodes parsed — page layout may have changed; "
            "keeping previous feed"
        )
        return 1

    enrich_items(items, previous)
    attach_audio_lengths(items)
    merged = common.merge_items(previous, items)
    common.write_feed(
        list(merged.values()),
        OUTPUT_PATH,
        MAX_ITEMS,
        feed_id=SHOW_URL,
        title=FEED_TITLE,
        link=SHOW_URL,
        description=f"{SHOW_DESCRIPTION} (auto-generated from {SHOW_URL})",
        language="de",
        itunes_author="BRF1",
        itunes_summary=SHOW_DESCRIPTION,
        itunes_image=SHOW_IMAGE,
        itunes_category="Music",
        itunes_explicit="no",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
