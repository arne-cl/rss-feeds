#!/usr/bin/env python3
"""Shared helpers for the feed builders in this repository.

Handles fetching (direct with Chrome TLS impersonation, r.jina.ai fallback),
merging new items into the previous feed file, and RSS assembly via feedgen.
"""

import html as html_mod
import json
import logging
import os
import re
import sys
import time
import traceback
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
        enc = item.find("enclosure")
        if enc is not None and enc.get("url"):
            try:
                length = int(enc.get("length") or 0)
            except ValueError:
                length = 0
            entry["enclosure"] = {
                "url": enc["url"],
                "length": length,
                "type": enc.get("type") or "application/octet-stream",
            }
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
            # a fresh parse may not see the media button anymore; keep the
            # last known enclosure rather than dropping it silently
            if not item.get("enclosure") and old.get("enclosure"):
                item["enclosure"] = old["enclosure"]
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
# Soft failures
# --------------------------------------------------------------------------

WARNING_ID_SUFFIX = "#build-status"
WARNING_TITLE = "Feed build failed"


def build_warning_item(warning_url: str, exc: Exception) -> dict:
    """Item describing a failed build (stable id so reruns replace it)."""
    stacktrace = "".join(
        traceback.format_exception(type(exc), exc, exc.__traceback__)
    )
    return {
        "id": warning_url + WARNING_ID_SUFFIX,
        "title": WARNING_TITLE,
        "link": warning_url,
        "description": str(exc) or repr(exc),
        "published": datetime.now(timezone.utc),
        "content": (
            "<p>The last feed update failed; the items below are the most "
            "recent entries known.</p>\n"
            f"<pre>{html_mod.escape(stacktrace, quote=False)}</pre>"
        ),
    }


def without_warning(previous: dict[str, dict]) -> dict[str, dict]:
    """Drop stale build-failure entries once the feed builds again."""
    return {
        key: value
        for key, value in previous.items()
        if not key.endswith(WARNING_ID_SUFFIX)
    }


def write_warning_feed(
    output_path: str, max_items: int, warning_url: str, exc: Exception, **metadata
) -> int:
    """Record a failed build as an item in the feed, keeping previous items.

    Also prints a GitHub Actions ``::warning::`` annotation (single line) so
    the breakage is visible on the CI run, not only inside the feed XML.
    Returns 0 so one flaky source does not abort the whole workflow.
    """
    log.error("feed build failed: %s", exc)
    message = " ".join(str(exc).split()) or repr(exc)
    print(f"::warning::{WARNING_TITLE}: {message}")
    warning = build_warning_item(warning_url, exc)
    merged = merge_items(load_previous(output_path), [warning])
    write_feed(list(merged.values()), output_path, max_items, **metadata)
    return 0


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
    itunes_author: str | None = None,
    itunes_summary: str | None = None,
    itunes_image: str | None = None,
    itunes_category: str | None = None,
    itunes_explicit: str | None = None,
) -> bytes:
    fg = FeedGenerator()
    fg.id(feed_id)
    fg.title(title)
    fg.link(href=link)
    fg.description(description)
    fg.language(language)
    fg.updated(datetime.now(timezone.utc))

    needs_itunes = any(
        (
            itunes_author,
            itunes_summary,
            itunes_image,
            itunes_category,
            itunes_explicit,
        )
    ) or any(item.get("image") for item in items)
    if needs_itunes:
        fg.load_extension("podcast")
        if itunes_author:
            fg.podcast.itunes_author(itunes_author)
        if itunes_summary:
            fg.podcast.itunes_summary(itunes_summary)
        if itunes_image:
            fg.podcast.itunes_image(itunes_image)
        if itunes_category:
            fg.podcast.itunes_category(itunes_category)
        if itunes_explicit:
            fg.podcast.itunes_explicit(itunes_explicit)

    for item in items:
        fe = fg.add_entry(order="append")
        fe.id(item["id"])
        fe.title(item["title"])
        fe.link(href=item["link"])
        fe.description(item["description"])
        if item.get("content"):
            fe.content(item["content"], type="html")
        if item.get("enclosure"):
            enc = item["enclosure"]
            fe.enclosure(enc["url"], enc.get("length") or 0, enc["type"])
        if item.get("image"):
            fe.podcast.itunes_image(item["image"])
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
