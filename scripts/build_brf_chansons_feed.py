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
                "image": img_el["data-src"] if img_el else "",
            }
        )
    items.sort(key=lambda item: item["published"], reverse=True)
    log.info("parsed %d episode(s) from archive", len(items))
    return items
