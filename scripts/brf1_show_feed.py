#!/usr/bin/env python3
"""Build podcast feeds for BRF1 music shows (https://1.brf.be/sendungen/).

BRF only publishes official podcasts for news/sport (podcast.brf.be); its
music shows are plain WordPress category archives on 1.brf.be. All shows
share the same pixelpress theme, so one parametrized builder covers them
and each show ships as a thin wrapper script supplying its ShowConfig:

- The archive page lists episode cards plus a "Sendungsprofil" teaser with
  the two newest episodes (which do not repeat in the archive list below).
  Each card carries title, episode URL `/sendungen/<slug>/<id>/`,
  `<time datetime="…">`, excerpt and thumbnail.
- Each episode page embeds an audio player whose inline JS loads
  https://streaming2.brf.be/play/<hash>; that endpoint returns an HTML
  snippet with a stable direct MP3 URL, used as the RSS <enclosure>.

Offline/testing env overrides (prefix per show, e.g. CHANSONS,
ROCK_MONSIEUR): <PREFIX>_HTML=<file> (parse a saved archive copy),
<PREFIX>_PAGES_DIR=<dir> (saved episode pages, offline mode),
<PREFIX>_PLAY_DIR=<dir> (saved play-endpoint snippets, offline mode).
"""

import html as html_module
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime
from functools import cached_property
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

import common

PLAY_URL_RE = re.compile(r"https://streaming2\.brf\.be/play/([0-9a-f]+)")
PLAY_URL_TEMPLATE = "https://streaming2.brf.be/play/{}"
BRF_TZ = ZoneInfo("Europe/Brussels")

log = logging.getLogger("brf1_show_feed")


@dataclass(frozen=True)
class ShowConfig:
    """Per-show parameters; see the wrapper scripts for real values."""

    slug: str  # e.g. "chansons" -> https://1.brf.be/sendungen/chansons/
    title: str
    description: str  # show description; the feed adds a suffix
    image: str  # show cover (only .jpg/.png pass feedgen's itunes:image)
    output_path: str
    env_prefix: str  # e.g. "CHANSONS" -> CHANSONS_HTML, CHANSONS_PAGES_DIR, ...
    max_items: int = 100

    @cached_property
    def show_url(self) -> str:
        return f"https://1.brf.be/sendungen/{self.slug}/"

    @cached_property
    def episode_url_re(self) -> re.Pattern:
        return re.compile(
            rf"^https://1\.brf\.be/sendungen/{re.escape(self.slug)}/(\d+)/?$"
        )

    @cached_property
    def html_env(self) -> str:
        return f"{self.env_prefix}_HTML"

    @cached_property
    def pages_dir_env(self) -> str:
        return f"{self.env_prefix}_PAGES_DIR"

    @cached_property
    def play_dir_env(self) -> str:
        return f"{self.env_prefix}_PLAY_DIR"


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


# --------------------------------------------------------------------------
# Archive page
# --------------------------------------------------------------------------

def parse_archive(cfg: ShowConfig, html: str) -> list[dict]:
    """Episode entries from the archive page (teaser + archive cards).

    The two newest episodes only appear in the "Sendungsprofil" teaser at
    the top, not in the archive card list; both sections are parsed and
    deduplicated by episode id.
    """
    soup = BeautifulSoup(html, "html.parser")
    items = []
    seen = set()
    for card in soup.select(".card-item a.inner-card[href]"):
        match = cfg.episode_url_re.match(urljoin(cfg.show_url, card["href"]))
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
                "id": urljoin(cfg.show_url, f"{episode_id}/"),
                "title": _norm(title_el.get_text(" ", strip=True)),
                "link": urljoin(cfg.show_url, f"{episode_id}/"),
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


def _episode_local_path(cfg: ShowConfig, link: str) -> str | None:
    match = cfg.episode_url_re.match(link)
    if not match:
        return None
    return os.path.join(os.environ[cfg.pages_dir_env], match.group(1) + ".html")


def _play_local_path(cfg: ShowConfig, play_hash: str) -> str:
    return os.path.join(os.environ[cfg.play_dir_env], play_hash + ".html")


def enrich_items(
    cfg: ShowConfig, items: list[dict], previous: dict[str, dict]
) -> None:
    """Attach article content and the audio enclosure to items.

    Everything is cached inside the feed itself: items whose previous entry
    already carries content and an enclosure are not fetched again. With
    <PREFIX>_PAGES_DIR / <PREFIX>_PLAY_DIR set, only saved page copies are
    used (offline mode — no requests at all).
    """
    by_id = {entry["id"]: entry for entry in previous.values()}
    enriched = 0
    for item in items:
        old = by_id.get(item["id"])
        # An enclosure means fully enriched: some pages have no article
        # text at all (player + excerpt only), so content is optional.
        # Entries with content but no enclosure keep being retried —
        # their audio resolution failed before.
        if old and old.get("enclosure"):
            if old.get("content"):
                item["content"] = old["content"]
            item["enclosure"] = old["enclosure"]
            item["description"] = old.get("description") or item["description"]
            continue

        page_html = None
        if os.environ.get(cfg.pages_dir_env):
            page_html = _read_local_copy(_episode_local_path(cfg, item["link"]))
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
        if os.environ.get(cfg.play_dir_env):
            play_html = _read_local_copy(_play_local_path(cfg, parsed["play_hash"]))
        else:
            play_url = PLAY_URL_TEMPLATE.format(parsed["play_hash"])
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

def main(cfg: ShowConfig) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    kwargs = dict(
        feed_id=cfg.show_url,
        title=cfg.title,
        link=cfg.show_url,
        description=f"{cfg.description} (auto-generated from {cfg.show_url})",
        language="de",
        itunes_author="BRF1",
        itunes_summary=cfg.description,
        itunes_image=cfg.image,
        itunes_category="Music",
        itunes_explicit="no",
    )

    try:
        html, _source = common.fetch_page(cfg.show_url, cfg.html_env)
    except Exception as exc:  # noqa: BLE001
        return common.write_warning_feed(
            cfg.output_path, cfg.max_items, cfg.show_url, exc, **kwargs
        )

    previous = common.load_previous(cfg.output_path)
    items = parse_archive(cfg, html)
    if not items:
        exc = RuntimeError(
            "no episodes parsed — page layout may have changed; "
            "keeping previous feed"
        )
        return common.write_warning_feed(
            cfg.output_path, cfg.max_items, cfg.show_url, exc, **kwargs
        )

    enrich_items(cfg, items, previous)
    attach_audio_lengths(items)
    merged = common.merge_items(common.without_warning(previous), items)
    common.write_feed(list(merged.values()), cfg.output_path, cfg.max_items, **kwargs)
    return 0
