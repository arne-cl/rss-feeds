#!/usr/bin/env python3
"""Shared helpers for the feed builders in this repository.

Handles fetching (direct with Chrome TLS impersonation, r.jina.ai fallback),
merging new items into the previous feed file, and RSS assembly via feedgen.
"""

import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from bs4 import BeautifulSoup
from curl_cffi import requests as creq
from feedgen.feed import FeedGenerator

log = logging.getLogger("feed_common")


# --------------------------------------------------------------------------
# Fetching
# --------------------------------------------------------------------------

def fetch_direct(url: str) -> str:
    r = creq.get(
        url,
        impersonate="chrome",
        timeout=30,
        headers={"Accept": "text/html", "Accept-Language": "en-US,en;q=0.9"},
    )
    r.raise_for_status()
    return r.text


def fetch_jina(url: str) -> str:
    headers = {"x-respond-with": "html"}
    api_key = os.environ.get("JINA_API_KEY")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    last_exc = None
    for attempt in range(3):
        try:
            r = creq.get(f"https://r.jina.ai/{url}", headers=headers, timeout=60)
            r.raise_for_status()
            return r.text
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            wait = 2**attempt * 2
            log.warning("jina attempt %d failed (%s), retrying in %ds", attempt + 1, exc, wait)
            time.sleep(wait)
    raise last_exc


def fetch_page(url: str, local_html_env: str) -> tuple[str, str]:
    """Fetch url, or read a local file if the env var local_html_env is set.

    Returns (html, source) with source being "local", "direct" or "jina".
    """
    path = os.environ.get(local_html_env)
    if path:
        log.info("using local HTML copy: %s", path)
        with open(path, encoding="utf-8") as f:
            return f.read(), "direct"
    try:
        html = fetch_direct(url)
        log.info("direct fetch ok (%d bytes)", len(html))
        return html, "direct"
    except Exception as exc:  # noqa: BLE001
        log.warning("direct fetch failed (%s), falling back to jina", exc)
    return fetch_jina(url), "jina"


# --------------------------------------------------------------------------
# Merging with the previous feed
# --------------------------------------------------------------------------

def squash(text: str) -> str:
    """Case/punctuation-insensitive key for title comparisons."""
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def load_previous(path: str) -> dict[str, dict]:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            soup = BeautifulSoup(f.read(), "xml")
    except Exception as exc:  # noqa: BLE001
        log.warning("could not parse previous feed (%s), starting fresh", exc)
        return {}
    prev = {}
    for item in soup.find_all("item"):
        link = item.find("link")
        if link is None or not link.get_text(strip=True):
            continue
        url = link.get_text(strip=True)
        guid = item.find("guid")
        item_id = guid.get_text(strip=True) if guid else ""
        if not item_id:
            item_id = url
        pub = None
        pub_tag = item.find("pubdate") or item.find("pubDate")
        if pub_tag is not None:
            try:
                pub = parsedate_to_datetime(pub_tag.get_text(strip=True))
            except (TypeError, ValueError):
                pass
        desc = item.find("description")
        title = item.find("title")
        entry = {
            "id": item_id,
            "title": title.get_text(" ", strip=True) if title else "",
            "link": url,
            "description": desc.get_text() if desc else "",
            "published": pub,
        }
        encoded = item.find("content:encoded")
        if encoded is not None:
            entry["content"] = encoded.get_text()
        prev[item_id] = entry
    log.info("loaded %d item(s) from previous feed", len(prev))
    return prev


def merge_items(previous: dict[str, dict], items: list[dict]) -> dict[str, dict]:
    """Merge new items into the previous feed's items (by id).

    New items without a published date keep the previously stored one.
    Previous entries that duplicate a new item under an older id scheme
    (same link + date, or same normalized title + date) are dropped, so
    id-scheme migrations don't leave shadow copies behind.
    """
    merged = dict(previous)
    for item in items:
        old = merged.get(item["id"])
        if old is None:
            # id-scheme migration: fall back to the same link target
            old = next(
                (e for e in previous.values() if e["link"] == item["link"]), None
            )
        if old:
            if item["published"] is None:
                item["published"] = old["published"]
            # cached article content belongs to the link target, so it can
            # safely cross id schemes
            if not item.get("content") and old.get("content"):
                item["content"] = old["content"]
        merged[item["id"]] = item

    link_dates = set()
    title_dates = set()
    for item in items:
        if item["published"] is None:
            continue
        date = item["published"].date()
        link_dates.add((item["link"], date))
        title_dates.add((squash(item["title"]), date))

    new_ids = {item["id"] for item in items}

    def superseded(entry: dict) -> bool:
        if entry["published"] is None:
            return False
        date = entry["published"].date()
        return (entry["link"], date) in link_dates or (
            squash(entry["title"]),
            date,
        ) in title_dates

    return {
        key: value
        for key, value in merged.items()
        if key in new_ids or not superseded(value)
    }


# --------------------------------------------------------------------------
# Feed assembly
# --------------------------------------------------------------------------

def sort_key(item: dict):
    pub = item["published"]
    if pub is None:
        return datetime.min.replace(tzinfo=timezone.utc)
    if pub.tzinfo is None:
        pub = pub.replace(tzinfo=timezone.utc)
    return pub


def build_feed(
    items: list[dict],
    *,
    feed_id: str,
    title: str,
    link: str,
    description: str,
    language: str,
) -> bytes:
    fg = FeedGenerator()
    fg.id(feed_id)
    fg.title(title)
    fg.link(href=link)
    fg.description(description)
    fg.language(language)
    fg.updated(datetime.now(timezone.utc))

    for item in items:
        fe = fg.add_entry(order="append")
        fe.id(item["id"])
        fe.title(item["title"])
        fe.link(href=item["link"])
        fe.description(item["description"])
        if item.get("content"):
            fe.content(item["content"], type="html")
        if item["published"]:
            fe.published(item["published"])
            fe.updated(item["published"])

    return fg.rss_str(pretty=True)


def write_feed(ordered: list[dict], output_path: str, max_items: int, **metadata) -> None:
    """Sort, cap, and write items to output_path."""
    ordered = sorted(ordered, key=sort_key, reverse=True)[:max_items]
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(build_feed(ordered, **metadata))
    log.info("wrote %d item(s) to %s", len(ordered), output_path)
