#!/usr/bin/env python3
"""Build a podcast-style RSS feed from the rbb24 "Polen Update" video series
(https://www.rbb24.de/panorama/polen-update/).

The overview page lists the latest ~30 video teasers — without dates and
mostly without descriptions. Teaser link paths vary across rbb24 sections
(/panorama/av/av24/, /panorama/polen-update/av24/, /politik/av/av24/), but
the roofline always contains "Polen" (rarely only the URL does, e.g. a
topic-kicker roofline like "Neue Bahnverbindungen"), so teasers are kept
when either roofline or URL mentions polen.

Each video detail page carries JSON-LD: NewsArticle (datePublished,
description) and VideoObject (contentUrl → direct MP4 on the ARD CDN,
thumbnails). New items are enriched once from their detail page; results
are cached inside the feed itself, so already-fetched pages are never
requested again. The MP4 URLs carry a content UUID (no expiring signature)
and are exposed as video/mp4 enclosures, making the feed playable in
podcast apps.

Usage: python scripts/build_rbb24_polen_update_feed.py
Optional env: RBB24_POLEN_HTML=<file> (parse a saved overview page offline)
              RBB24_POLEN_PAGES_DIR=<dir> (saved video pages, offline mode)
"""

import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from urllib.parse import urljoin

from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common

PAGE_URL = "https://www.rbb24.de/panorama/polen-update/"
FEED_TITLE = "Polen Update (rbb24)"
OUTPUT_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "feeds", "rbb24-polen-update.xml")
)
MAX_ITEMS = 100
HTML_ENV = "RBB24_POLEN_HTML"
PAGES_DIR_ENV = "RBB24_POLEN_PAGES_DIR"

FEED_DESCRIPTION = (
    "Polen Update: aktuelle Nachrichten und Trends aus dem Nachbarland – "
    "die Videos der rbb|24-Reihe."
)

log = logging.getLogger("build_rbb24_polen_update_feed")


# --------------------------------------------------------------------------
# Overview page
# --------------------------------------------------------------------------

def _absolute(url: str) -> str | None:
    if not url:
        return None
    if url.startswith("http"):
        return url
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("/"):
        return urljoin(PAGE_URL, url)
    return None


def feed_cover(html: str) -> str | None:
    """Series cover image from the overview page's og:image meta tag."""
    soup = BeautifulSoup(html, "html.parser")
    meta = soup.find(
        "meta", attrs={"content": True, "name": "og:image"}
    ) or soup.find("meta", attrs={"content": True, "property": "og:image"})
    return _absolute(meta["content"]) if meta else None


def _is_polen_teaser(article, href: str) -> bool:
    roofline = article.select_one(".teaser__roofline")
    text = roofline.get_text(" ", strip=True).lower() if roofline else ""
    return "polen" in text or "polen" in href.lower()


def parse_overview(html: str) -> list[dict]:
    """Teaser items from the series overview page (newest first)."""
    soup = BeautifulSoup(html, "html.parser")
    items = []
    seen_links = set()
    for article in soup.select("main article.teaser"):
        anchor = article.select_one("a.teaser__text-container[href]")
        if anchor is None:
            continue
        link = _absolute(anchor["href"])
        if not link or link in seen_links:
            continue
        if not _is_polen_teaser(article, anchor["href"]):
            continue
        title_el = article.select_one(".teaser__title")
        title = " ".join(title_el.get_text(" ", strip=True).split()) if title_el else ""
        if not title:
            continue
        seen_links.add(link)
        text_el = article.select_one(".teaser__text")
        description = (
            " ".join(text_el.get_text(" ", strip=True).split()) if text_el else title
        )
        img = article.select_one("figure.teaser__image-container img[src]")
        items.append(
            {
                "id": link,
                "title": title,
                "link": link,
                "description": description,
                "published": None,
                "image": _absolute(img["src"]) if img else "",
            }
        )
    log.info("parsed %d teaser item(s)", len(items))
    return items


# --------------------------------------------------------------------------
# Video detail page
# --------------------------------------------------------------------------

def parse_video_page(html: str) -> dict:
    """Date, description and MP4 from a video page's JSON-LD blocks."""
    soup = BeautifulSoup(html, "html.parser")
    published = None
    description = ""
    enclosure = None
    image = None
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except (TypeError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        kind = data.get("@type")
        if published is None and data.get("datePublished"):
            published = _parse_iso_date(data["datePublished"])
        if kind == "NewsArticle" and not description:
            description = data.get("description") or ""
        if kind == "VideoObject":
            content_url = data.get("contentUrl") or ""
            if content_url.lower().endswith(".mp4") and enclosure is None:
                enclosure = {"url": content_url, "type": "video/mp4", "length": 0}
            thumbnails = data.get("thumbnailUrl") or []
            if thumbnails:
                image = thumbnails[-1]
    if published is None:
        published = _parse_fallback_date(soup)
    return {
        "published": published,
        "description": description,
        "enclosure": enclosure,
        "image": image,
    }


def _parse_iso_date(text: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _parse_fallback_date(soup) -> datetime | None:
    """<meta name="date" content="2026-10-30-T16:48:38"> (rbb24 quirk)."""
    meta = soup.find("meta", attrs={"name": "date", "content": True})
    if meta is None:
        return None
    text = meta["content"].strip()
    if len(text) > 10 and text[10] == "-" and text[11] == "T":
        text = text[:10] + text[10:]
    return _parse_iso_date(text)


def fetch_video_page(link: str) -> str:
    """Fetch a video detail page (kept separate so tests can stub it)."""
    return common.fetch_direct(link)


def _local_page_path(link: str) -> str | None:
    """Path of a saved page copy for link inside $RBB24_POLEN_PAGES_DIR."""
    match = re.match(r"https?://[^/?#]+([^?#]*)", link)
    if not match:
        return None
    segment = match.group(1).rstrip("/").rsplit("/", 1)[-1]
    if not segment:
        return None
    return os.path.join(os.environ[PAGES_DIR_ENV], segment)


def _read_local_copy(path: str | None) -> str | None:
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return f.read()
    return None


def enrich_items(items: list[dict], previous: dict[str, dict]) -> None:
    """Attach date, description and MP4 enclosure to new items.

    Everything is cached inside the feed itself: items whose previous entry
    already carries a date and an enclosure are not fetched again. Items
    whose previous enrichment failed (no date/enclosure) are retried. With
    RBB24_POLEN_PAGES_DIR set, only saved page copies are used (offline
    mode — no requests at all).
    """
    by_id = {entry["id"]: entry for entry in previous.values()}
    enriched = 0
    for item in items:
        old = by_id.get(item["id"])
        if old and old.get("published") and old.get("enclosure"):
            item["description"] = old.get("description") or item["description"]
            item["published"] = old["published"]
            item["enclosure"] = old["enclosure"]
            item["image"] = old.get("image") or item["image"]
            continue
        page_html = None
        if os.environ.get(PAGES_DIR_ENV):
            page_html = _read_local_copy(_local_page_path(item["link"]))
        else:
            try:
                page_html = fetch_video_page(item["link"])
            except Exception as exc:  # noqa: BLE001
                log.warning("could not fetch %s: %s", item["link"], exc)
        if not page_html:
            continue
        parsed = parse_video_page(page_html)
        if parsed["published"] and item["published"] is None:
            item["published"] = parsed["published"]
        if parsed["description"]:
            item["description"] = parsed["description"]
        if parsed["enclosure"]:
            item["enclosure"] = parsed["enclosure"]
        if parsed["image"]:
            item["image"] = parsed["image"]
        enriched += 1
    log.info("enriched %d item(s) from video pages", enriched)


# --------------------------------------------------------------------------
# Media lengths
# --------------------------------------------------------------------------

def fetch_content_length(url: str) -> int:
    """Content-Length via HEAD request (0 when unavailable)."""
    r = common.creq.head(url, impersonate="chrome", timeout=30)
    r.raise_for_status()
    return int(r.headers.get("Content-Length") or 0)


def attach_media_lengths(items: list[dict]) -> None:
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

def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    kwargs = dict(
        feed_id=PAGE_URL,
        title=FEED_TITLE,
        link=PAGE_URL,
        description=f"{FEED_DESCRIPTION} (auto-generated from {PAGE_URL})",
        language="de",
        itunes_author="rbb24",
        itunes_summary=FEED_DESCRIPTION,
        itunes_category="News",
        itunes_explicit="no",
    )

    try:
        html, _source = common.fetch_page(PAGE_URL, HTML_ENV)
    except Exception as exc:  # noqa: BLE001
        return common.write_warning_feed(OUTPUT_PATH, MAX_ITEMS, PAGE_URL, exc, **kwargs)

    previous = common.load_previous(OUTPUT_PATH)
    items = parse_overview(html)
    if not items:
        exc = RuntimeError(
            "no videos parsed — page layout may have changed; keeping previous feed"
        )
        return common.write_warning_feed(OUTPUT_PATH, MAX_ITEMS, PAGE_URL, exc, **kwargs)

    cover = feed_cover(html)
    if cover:
        kwargs["itunes_image"] = cover

    enrich_items(items, previous)
    attach_media_lengths(items)
    merged = common.merge_items(common.without_warning(previous), items)
    common.write_feed(list(merged.values()), OUTPUT_PATH, MAX_ITEMS, **kwargs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
