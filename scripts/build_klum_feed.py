#!/usr/bin/env python3
"""Build an RSS feed from Günther Klum's news page (https://klum.com/news).

The page is a static Duda/1&1 website-builder site: news items are stacked
rows, each rendered twice (a mobile and a desktop variant) with slightly
different wording and — rarely — conflicting dates. Items are date + text,
optionally with a "MEHR INFORMATIONEN" button linking to YouTube or internal
pages. One button is an expiring signed CDN mp4 URL; some items have no
button at all.

Item links therefore use the best stable URL available: the button href
(relative URLs resolved, mangled YouTube hosts normalized, expiring signed
CDN URLs rejected) with a fallback to the news page itself. Item ids are
always stable synthetic anchors: https://www.klum.com/news#<YYYYMMDD>-<slug>.

Usage: python scripts/build_klum_feed.py
Optional env: KLUM_NEWS_HTML=<file> (parse a saved page copy offline)
"""

import os
import re
import sys
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

DATE_RE = re.compile(r"(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})")
MOBILE_CLASSES = {"hide-for-large", "hide-for-medium"}
UNSTABLE_HOSTS = {"cdn.website-editor.net", "le-cdn.website-editor.net"}
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
    """Resolve a button href to a stable absolute URL, or the page URL."""
    resolved = urljoin(PAGE_URL, href.strip())
    match = re.match(r"https?://([^/]+)", resolved)
    if not match:
        return PAGE_URL
    host = match.group(1).lower()
    if host in UNSTABLE_HOSTS or "Expires=" in resolved or "Signature=" in resolved:
        return PAGE_URL
    if host in MANGLED_YOUTUBE_HOSTS:
        resolved = resolved.replace(match.group(1), MANGLED_YOUTUBE_HOSTS[host], 1)
    return resolved


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
                for href in group["links"]:
                    candidate = _best_link(href)
                    if candidate != PAGE_URL:
                        link = candidate
                        break
                items.append({"published": published, "title": title, "link": link})
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
        items.append(
            {
                "id": anchor,
                "title": item["title"],
                "link": item["link"],
                "description": item["title"],
                "published": item["published"],
            }
        )
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
# Main
# --------------------------------------------------------------------------

def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    try:
        html, _source = common.fetch_page(PAGE_URL, "KLUM_NEWS_HTML")
    except Exception as exc:  # noqa: BLE001
        log.error("fetch failed: %s", exc)
        return 1

    items = parse_klum(html)
    if not items:
        log.error("no news items parsed — page layout may have changed; keeping previous feed")
        return 1

    merged = common.merge_items(common.load_previous(OUTPUT_PATH), items)
    merged = prune_superseded(merged, items)
    common.write_feed(
        list(merged.values()),
        OUTPUT_PATH,
        MAX_ITEMS,
        feed_id=PAGE_URL,
        title=FEED_TITLE,
        link=PAGE_URL,
        description=f"News von Günther Klum (auto-generated from {PAGE_URL})",
        language="de",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
