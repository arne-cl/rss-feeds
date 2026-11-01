# 0021: RSS feed for rbb24 "Polen Update"

## Problem

rbb24 publishes a video series "Polen Update"
(<https://www.rbb24.de/panorama/polen-update/>) but offers no RSS feed for
it — the only RSS the rbb exposes are sports-club feeds on `/hilfe/`. The
overview page lists the latest ~17 video teasers without dates and mostly
without descriptions; each teaser links to a video detail page.

## Findings (live checks 2026-11-01)

- Overview page: `article.teaser` elements under `<main>`; rooflines always
  contain "Polen" ("Video | Polen-Update", or "Video" label + "Polen
  Update"), but teaser link paths vary (`/panorama/av/av24/…`,
  `/panorama/polen-update/av24/…`, `/politik/av/av24/…`) — filter by
  roofline, not URL path.
- Detail page contains JSON-LD `NewsArticle` (`datePublished`, headline,
  description) and `VideoObject` (`contentUrl` → direct MP4 on
  `rbb-progressive.ard-mcdn.de`, `duration`, `thumbnailUrl`), plus
  `<meta name="date" content="2026-10-30-T16:48:38">` (odd dash before T —
  prefer JSON-LD).

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

- (to be filled)

## Verification

- (to be filled)

## Status

todo
