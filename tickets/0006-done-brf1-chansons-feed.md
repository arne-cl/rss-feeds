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
   - `parse_episode()` → article paragraphs (content:encoded), fuller
     excerpt, play hash.
   - `resolve_audio()` → (mp3 URL, audio/mpeg) from the play snippet.
   - `enrich_items()`: new items only; content/enclosure/description cached
     in the previous feed so known episodes are never re-fetched; offline
     env overrides `CHANSONS_HTML`, `CHANSONS_PAGES_DIR`, `CHANSONS_PLAY_DIR`.
   - `attach_audio_lengths()`: HEAD Content-Length, best effort.
   - `common.build_feed` gained optional iTunes tags (podcast extension:
     author/summary/image/category/explicit + per-entry image) — all
     existing feeds unaffected (no itunes namespace unless requested).
   - Feed `feeds/brf1-chansons.xml`, MAX_ITEMS=100, backfill archive
     page 1 only (12 episodes); older items persist via merge.
2. Fixtures: archive page, one episode page, one play snippet.
3. Strict red/green TDD, phases committed separately.
4. CI: builder added to `.github/workflows/update.yml`; README row +
   offline-mode docs.

## Hurdles

- **Missing `__main__` block on first live run**: the module imported fine
  (so all tests passed) but running it did nothing — exit 0, no output, no
  feed. Tests can't catch this; only the live run did. Fixed immediately.
- **feedgen itunes:image accepts only `.jpg`/`.png`**: a `.jpeg` thumbnail
  crashed the build (ValueError "Image file must be png or jpg");
  `parse_archive` now keeps only `.jpg`/`.png` images (one episode
  currently loses its art — acceptable).
- **Teaser vs. archive duplication**: the 2 newest episodes live only in
  the "Sendungsprofil" teaser, not in the archive card list; both sections
  are parsed and deduplicated by episode id.
- `html.escape` also escapes quotes (`&quot;`) in content:encoded — valid
  and renders identically; test expectation adjusted (fixed the test, not
  the implementation).
- AGENTS.md/README/ticket 0005 claim the venv is `.venv/`, but the real
  path is `venv/` (`venv/bin/pytest`).

## Verification

- `venv/bin/pytest`: 122 passed (95 baseline + 27 new).
- Live run: 12 episodes parsed, 12 enclosures `audio/mpeg` with real
  Content-Lengths (~56 MB), pubDates `+0200` (Europe/Brussels), iTunes
  channel tags + per-episode art.
- Second live run: cache hit (0 audio resolutions), byte-identical output.
- Enclosure URL verified reachable: HTTP 200, `audio/mpeg`, 56488879 bytes,
  `Accept-Ranges: bytes`.

## Status

done
