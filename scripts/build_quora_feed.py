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

Soft failures (fetch, fallback fetch, unparseable page) do not abort with a
non-zero exit: they are recorded as a rolling "Feed build failed" item
(error + stacktrace) inside the feed, keeping all previous items, so feed
subscribers can see the breakage. The next successful build removes that
item again.

Usage: python scripts/build_quora_feed.py
Optional env: JINA_API_KEY (avoids r.jina.ai rate limits on shared IPs)
              QUORA_PROFILE_HTML=<file> (parse a saved page copy offline)
"""

import json
import os
import re
import sys
import logging
from datetime import datetime, timezone, date
from urllib.parse import urljoin

from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common

PROFILE_URL = "https://www.quora.com/profile/Alan-Kay-11"
ANSWER_PATH = re.compile(r"^https://www\.quora\.com/[^/]+/answer/Alan-Kay-11/?$")
FEED_TITLE = "Alan Kay on Quora"
OUTPUT_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "feeds", "alankay-quora.xml")
)
MAX_ITEMS = 100

log = logging.getLogger("build_quora_feed")


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
# Main
# --------------------------------------------------------------------------

def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    offline = bool(os.environ.get("QUORA_PROFILE_HTML"))
    kwargs = dict(
        feed_id=PROFILE_URL,
        title=FEED_TITLE,
        link=PROFILE_URL,
        description=f"Answers by Alan Kay on Quora (auto-generated from {PROFILE_URL})",
        language="en",
    )

    try:
        html, source = common.fetch_page(PROFILE_URL, "QUORA_PROFILE_HTML")
    except Exception as exc:  # noqa: BLE001
        return common.write_warning_feed(
            OUTPUT_PATH, MAX_ITEMS, PROFILE_URL, exc, **kwargs
        )

    items = parse_direct(html) if source == "direct" else []
    if not items and not offline:
        if source == "direct":
            try:
                html = common.fetch_jina(PROFILE_URL)
            except Exception as exc:  # noqa: BLE001
                return common.write_warning_feed(
                    OUTPUT_PATH, MAX_ITEMS, PROFILE_URL, exc, **kwargs
                )
        items = parse_dom(html)

    if not items:
        # Rate-limit pages and layout changes look identical in "0 answers";
        # log what was actually fetched so CI can tell them apart.
        log.error("page excerpt: %s", re.sub(r"\s+", " ", html[:300]))
        exc = RuntimeError(
            "no answers parsed — page layout may have changed; keeping previous feed"
        )
        return common.write_warning_feed(
            OUTPUT_PATH, MAX_ITEMS, PROFILE_URL, exc, **kwargs
        )

    merged = common.merge_items(
        common.without_warning(common.load_previous(OUTPUT_PATH)), items
    )
    common.write_feed(list(merged.values()), OUTPUT_PATH, MAX_ITEMS, **kwargs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
