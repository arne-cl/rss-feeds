# 0006: Podcast feed for BRF1 "Chansons, Lieder und Folk"

## Problem

BRF1's music magazine "Chansons, Lieder und Folk" (mondays 20–21h,
https://1.brf.be/sendungen/chansons/) has no podcast feed — BRF only
publishes official podcasts for news/sport (podcast.brf.be). We need an
RSS feed with properly embedded audio (`<enclosure>`) for a podcast client.

## Findings (site research)

- Archive page lists ~10 cards + a 2-card "Sendungsprofil" teaser section
  (the 2 newest episodes only appear in the teaser — they are NOT repeated
  in the archive list on page 1); cards carry title, episode URL
  `/sendungen/chansons/<id>/`, `<time datetime="…">`, excerpt, thumbnail,
  `has-audio` marker.
- Episode page embeds an audio player stub whose inline JS fetches
  `https://streaming2.brf.be/play/<6-hex-hash>`; that endpoint returns an
  HTML snippet with a stable direct MP3 URL
  (`https://streaming2.brf.be/audio/<year>/<week>/<md5>.mp3`, ~56 MB/show,
  HEAD gives Content-Length, CORS `*`).
- WP REST API is locked (401) → BeautifulSoup scraping like the other
  builders.

## Approach

1. `scripts/build_brf_chansons_feed.py`:
   - `parse_archive()` → episodes (id=episode URL, title, published,
     description, image); dedupe teaser vs. archive cards.
   - `parse_episode()` → article paragraphs (content:encoded) + play hash.
   - `resolve_audio()` → (mp3 URL, audio/mpeg) from the play snippet.
   - HEAD for enclosure lengths; new items only, cached in previous feed
     (klum-style), offline env overrides `CHANSONS_HTML`,
     `CHANSONS_PAGES_DIR`, `CHANSONS_PLAY_DIR`.
   - `common.build_feed` gains optional iTunes tags (podcast extension)
     for cover art / author; feed `feeds/brf1-chansons.xml`, MAX_ITEMS=100.
   - Backfill: archive page 1 only (12 episodes); older items persist via
     merge.
2. Fixtures: archive page, one episode page, one play snippet.
3. Strict red/green TDD, phases committed separately.
4. CI: add builder to `.github/workflows/update.yml`; README row.

## Status

todo
