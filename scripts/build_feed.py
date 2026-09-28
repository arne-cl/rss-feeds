#!/usr/bin/env python3
"""Build an RSS feed from a Quora profile page.

Quora blocks plain requests and its HTML embeds answer data in escaped JSON,
so this script:

1. Tries a direct fetch with Chrome TLS impersonation (curl_cffi) and parses
   the answer objects embedded in the page's JSON blobs (full answer text +
   creation timestamps).
2. Falls back to the r.jina.ai reader proxy and parses the rendered DOM
   (excerpt text + answer dates).

The profile page only shows the latest few answers, so newly parsed items are
merged into the previous feed file to keep history and preserve dates.

Usage: python scripts/build_feed.py
Optional env: JINA_API_KEY (avoids r.jina.ai rate limits on shared IPs)
              QUORA_PROFILE_HTML=<file> (parse a saved page copy offline)
"""

import json
import os
import re
import sys
import time
import logging
from datetime import datetime, timezone, date
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from curl_cffi import requests as creq
from feedgen.feed import FeedGenerator

PROFILE_URL = "https://www.quora.com/profile/Alan-Kay-11"
ANSWER_PATH = re.compile(r"^https://www\.quora\.com/[^/]+/answer/Alan-Kay-11/?$")
FEED_TITLE = "Alan Kay on Quora"
OUTPUT_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "feeds", "alankay-quora.xml")
)
MAX_ITEMS = 100

log = logging.getLogger("build_feed")


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


def fetch_page(url: str) -> tuple[str, str]:
    path = os.environ.get("QUORA_PROFILE_HTML")
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
# Parsing strategy 1: direct HTML with embedded JSON
# --------------------------------------------------------------------------

def _qtext_to_text(json_str) -> str:
    """Render a Quora qtext document (JSON string of sections/spans) to text."""
    if not isinstance(json_str, str):
        return ""
    try:
        doc = json.loads(json_str)
    except ValueError:
        return ""
    sections = doc.get("sections", []) if isinstance(doc, dict) else []
    paragraphs = []
    for section in sections:
        if not isinstance(section, dict):
            continue
        text = "".join(
            span.get("text", "") for span in section.get("spans", []) if isinstance(span, dict)
        ).strip()
        if text:
            paragraphs.append(text)
    return "\n".join(paragraphs)


def _iter_store_answers(html: str):
    """Yield Answer nodes from the JSON blobs embedded in inlineQueryResults."""
    for sm in re.finditer(r"<script[^>]*>", html):
        end = html.find("</script>", sm.end())
        if end == -1:
            continue
        block = html[sm.end() : end]
        if "permaUrl" not in block:
            continue
        for pm in re.finditer(r'\.push\("((?:[^"\\]|\\.)*)"\)', block):
            try:
                data = json.loads(json.loads('"' + pm.group(1) + '"'))
            except ValueError:
                continue
            stack = [data]
            while stack:
                node = stack.pop()
                if isinstance(node, dict):
                    if node.get("__typename") == "Answer" and "permaUrl" in node:
                        yield node
                    stack.extend(node.values())
                elif isinstance(node, list):
                    stack.extend(node)


def title_from_url(url: str) -> str:
    slug = url.split("/")[3]
    return slug.replace("-", " ")


def parse_direct(html: str) -> list[dict]:
    items, seen = [], set()
    for ans in _iter_store_answers(html):
        url = urljoin("https://www.quora.com", ans["permaUrl"])
        if not ANSWER_PATH.match(url) or url in seen:
            continue
        seen.add(url)

        question = ans.get("question")
        title = ""
        if isinstance(question, dict):
            title = _qtext_to_text(question.get("title"))

        published = None
        created = ans.get("creationTime")
        if isinstance(created, (int, float)):
            published = datetime.fromtimestamp(created / 1e6, tz=timezone.utc)

        items.append(
            {
                "id": url,
                "title": title or title_from_url(url),
                "link": url,
                "description": _qtext_to_text(ans.get("content")),
                "published": published,
            }
        )
    log.info("direct JSON parse: %d answer(s)", len(items))
    return items


# --------------------------------------------------------------------------
# Parsing strategy 2: rendered DOM (jina reader HTML)
# --------------------------------------------------------------------------

def parse_timestamp(text: str):
    """Parse Quora timestamps like 'Sep 19', 'Sep 19, 2024'. Relative ones -> None."""
    text = text.strip()
    for fmt in ("%b %d, %Y", "%b %d"):
        try:
            dt = datetime.strptime(text, fmt)
        except ValueError:
            continue
        if fmt == "%b %d":
            today = date.today()
            d = date(today.year, dt.month, dt.day)
            if d > today:
                d = d.replace(year=today.year - 1)
            return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
        return dt.replace(tzinfo=timezone.utc)
    return None


def clean_excerpt(text: str) -> str:
    text = text.split("(more)")[0].strip()
    return re.sub(r"\s+", " ", text).rstrip("…").strip()


def parse_dom(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    anchors = [a for a in soup.find_all("a", href=True) if ANSWER_PATH.match(a["href"])]
    items, seen = [], set()
    for a in anchors:
        url = a["href"]
        if url in seen:
            continue
        seen.add(url)

        card = a
        title_el = None
        for _ in range(15):
            card = card.parent
            if card is None:
                break
            title_el = card.find(class_=re.compile(r"regular_title"))
            if title_el:
                break
        if title_el is None:
            log.warning("no title found for %s, using slug", url)
            title = title_from_url(url)
            excerpt = ""
        else:
            title = title_el.get_text(" ", strip=True)
            full_text = card.get_text(" ", strip=True)
            excerpt = clean_excerpt(full_text.split(title, 1)[-1])

        items.append(
            {
                "id": url,
                "title": title,
                "link": url,
                "description": excerpt,
                "published": parse_timestamp(a.get_text(" ", strip=True)),
            }
        )
    log.info("DOM parse: %d answer(s)", len(items))
    return items


# --------------------------------------------------------------------------
# Feed assembly
# --------------------------------------------------------------------------

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
        pub = None
        pub_tag = item.find("pubdate")
        if pub_tag is not None:
            try:
                pub = parsedate_to_datetime(pub_tag.get_text(strip=True))
            except (TypeError, ValueError):
                pass
        desc = item.find("description")
        title = item.find("title")
        prev[url] = {
            "id": url,
            "title": title.get_text(" ", strip=True) if title else "",
            "link": url,
            "description": desc.get_text() if desc else "",
            "published": pub,
        }
    log.info("loaded %d item(s) from previous feed", len(prev))
    return prev


def sort_key(item: dict):
    pub = item["published"]
    if pub is None:
        return datetime.min.replace(tzinfo=timezone.utc)
    if pub.tzinfo is None:
        pub = pub.replace(tzinfo=timezone.utc)
    return pub


def build_feed(items: list[dict]) -> bytes:
    fg = FeedGenerator()
    fg.id(PROFILE_URL)
    fg.title(FEED_TITLE)
    fg.link(href=PROFILE_URL)
    fg.description(f"Answers by Alan Kay on Quora (auto-generated from {PROFILE_URL})")
    fg.language("en")
    fg.updated(datetime.now(timezone.utc))

    for item in items:
        fe = fg.add_entry()
        fe.id(item["id"])
        fe.title(item["title"])
        fe.link(href=item["link"])
        fe.description(item["description"])
        if item["published"]:
            fe.published(item["published"])
            fe.updated(item["published"])

    return fg.rss_str(pretty=True)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    try:
        html, source = fetch_page(PROFILE_URL)
    except Exception as exc:  # noqa: BLE001
        log.error("all fetch attempts failed: %s", exc)
        return 1

    items = parse_direct(html) if source == "direct" else []
    if not items:
        if source == "direct":
            try:
                html = fetch_jina(PROFILE_URL)
            except Exception as exc:  # noqa: BLE001
                log.error("jina fallback fetch failed: %s", exc)
                return 1
        items = parse_dom(html)

    if not items:
        log.error("no answers parsed — page layout may have changed; keeping previous feed")
        return 1

    merged = load_previous(OUTPUT_PATH)
    for item in items:
        old = merged.get(item["id"])
        if old and item["published"] is None:
            item["published"] = old["published"]
        merged[item["id"]] = item

    ordered = sorted(merged.values(), key=sort_key, reverse=True)[:MAX_ITEMS]
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "wb") as f:
        f.write(build_feed(ordered))
    log.info("wrote %d item(s) to %s", len(ordered), OUTPUT_PATH)
    return 0


if __name__ == "__main__":
    sys.exit(main())
