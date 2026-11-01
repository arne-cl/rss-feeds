# 0021: RSS feed for rbb24 "Polen Update"

## Problem

rbb24 publishes a video series "Polen Update"
(<https://www.rbb24.de/panorama/polen-update/>) but offers no RSS feed for
it — the only RSS the rbb exposes are sports-club feeds on `/hilfe/`. The
overview page lists the latest video teasers without dates and mostly
without descriptions; each teaser links to a video detail page.

## Findings (live checks 2026-11-01)

- Overview page: `article.teaser` elements under `<main>` (30 of them);
  rooflines almost always contain "Polen" ("Video | Polen-Update", or
  "Video" label + "Polen Update"), but teaser link paths vary
  (`/panorama/av/av24/…`, `/panorama/polen-update/av24/…`,
  `/politik/av/av24/…`).
- Detail pages contain JSON-LD `NewsArticle` (`datePublished`, headline,
  description) and `VideoObject` (`contentUrl` → direct MP4 on
  `rbb-progressive.ard-mcdn.de`, `duration`, `thumbnailUrl`), plus
  `<meta name="date" content="2026-10-30-T16:48:38">` (odd dash before T —
  JSON-LD preferred; meta only as fallback).

## Approach (user decisions)

- Podcast-style feed with MP4 enclosures (like `brf1-chansons`): each new
  item's detail page is fetched once for date/description/MP4; results are
  cached inside the feed so old items are never re-fetched.
- Naming: `scripts/build_rbb24_polen_update_feed.py` →
  `feeds/rbb24-polen-update.xml`.

## Testability (red/green)

Baseline: 325 passed. New test module
`tests/test_build_rbb24_polen_update_feed.py` with saved fixtures
(`rbb24-polen-update.html`, `rbb24-polen-update-pages/<slug>.html`),
covering parse_overview, parse_video_page, enrich_items (stub/offline/
cache), media lengths, offline main() end-to-end, soft-failure warnings.

## Hurdles

- The overview actually lists 30 teasers (first estimates from a truncated
  page fetch said ~17). One teaser's roofline is a topic kicker ("Neue
  Bahnverbindungen") without "Polen" — teasers are kept when roofline OR
  URL contains "polen".
- The series og:image lives in `<meta name="og:image">` — attribute
  `name=`, not `property=` like usual.
- `_local_page_path` copied from klum appended `.html` to a segment that
  already ends in `.html` → cached-copy lookups never matched. Fixed by
  using the segment verbatim (rbb24 URLs always end in `.html`).
- Second live run exposed a cache regression: the fresh overview parse
  (title-as-description fallback, 468x262 teaser image) overwrote the
  richer detail-page description/image of cached items, and
  `common.load_previous` never parsed `itunes:image` in the first place.
  Fix: `load_previous` now reads `itunes:image` into `entry["image"]`, and
  `enrich_items`' cached branch restores old description/image. The buggy
  run had already overwritten the cached values, so the feed had to be
  rebuilt from scratch.

## Verification

- `pytest`: 355 passed (baseline 325 + 30 new).
- Live build: 30 items, 30 `video/mp4` enclosures, 30 pubDates, newest
  first. Enclosure MP4 answers HEAD 200 with Content-Length 21890128 —
  matching the written `<enclosure length>`.
- Rebuild: "enriched 0 item(s)" (everything cached), output identical to
  the previous run except `lastBuildDate`.
- Feed URL:
  https://raw.githubusercontent.com/arne-cl/rss-feeds/main/feeds/rbb24-polen-update.xml

## Status

done
