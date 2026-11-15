# 0022: Podcast feed for BRF1 "Rock Monsieur" (shared BRF1 show module)

## Problem

BRF1's music show "Rock Monsieur" (thursdays 20–21h,
https://1.brf.be/sendungen/rock-monsieur/) has no podcast feed, just like
"Chansons, Lieder und Folk" before it (ticket 0006). We want the same kind
of RSS feed with embedded audio (`<enclosure>`).

## Findings (site research)

- The Rock Monsieur pages use the **identical** pixelpress theme and
  structure as Chansons: "Sendungsprofil" teaser with the 2 newest episodes
  (not repeated in the archive list), ~10 archive cards, pagination.
- Episode pages embed the same player stub with a
  `https://streaming2.brf.be/play/<6-hex-hash>` URL; the play snippet
  returns a stable MP3 URL (verified live: episode 1231559 → hash `568fbf`
  → `https://streaming2.brf.be/audio/2026/46/37a8adab...mp3`).
- All current card images are `.jpg` (no feedgen `.jpeg` issue).
- Show metadata: title "Rock Monsieur", "Donnerstag, 20 - 21 Uhr",
  description "Rock Monsieur präsentiert Musik vom Tellerrand: …",
  cover `wp-content/uploads/sites/2/2021/05/rockmonsieur_motiv-1420x968.jpg`.
- **Some Rock Monsieur episodes have no article text at all** (player +
  excerpt only) — this surfaced a caching gap in the chansons-inherited
  enrich logic, see hurdles.

## Approach

Since the chansons builder was 100% reusable except for constants (and more
BRF1 shows may follow), extract instead of copy:

1. New `scripts/brf1_show_feed.py` with all parsing/enrichment/main logic
   parametrized by a frozen `ShowConfig` (slug, title, description, image,
   output path, env prefix, max_items). Config passed explicitly to
   `parse_archive`/`enrich_items`/`main` (no shared mutable module state —
   both test modules run in one pytest process).
2. `build_brf_chansons_feed.py` became a thin wrapper with the Chansons
   config; tests target the shared module now (`brf1_show_feed.parse_archive(CFG, …)`,
   patch targets moved to `brf1_show_feed.*`).
3. `scripts/build_brf_rock_monsieur_feed.py` wrapper: slug `rock-monsieur`,
   title "Rock Monsieur (BRF1)", output `feeds/brf1-rock-monsieur.xml`,
   env prefix `ROCK_MONSIEUR` (`ROCK_MONSIEUR_HTML`, `ROCK_MONSIEUR_PAGES_DIR`,
   `ROCK_MONSIEUR_PLAY_DIR`).
4. Fixtures: archive page, episode page 1231559, play snippet `568fbf`;
   test file mirroring the chansons tests.
5. Wired into `scripts/update_local.sh` + README (feeds table, local dev).

## Hurdles

- **Enclosure-without-content episodes defeated the cache**: two episodes
  (1231217, 1225071) have empty article bodies; the old "cached" check
  required content AND enclosure, so they were re-fetched (page + play
  snippet + HEAD) on every run. Fixed: an enclosure alone now marks an
  item as fully enriched. Deliberately *not* caching content-without-
  enclosure entries, so transient play-endpoint failures keep being
  retried instead of being baked into the feed forever.
- The chansons tests monkeypatched module-level functions of the old
  monolithic script; after the split, patching the wrapper would not
  affect the shared implementation, so patch targets moved to
  `brf1_show_feed` (config flows in as an argument, `dataclasses.replace`
  replaces the former `OUTPUT_PATH` monkeypatching).
- Offline comparison of the refactored chansons builder against the
  committed feed shows image-URL drift (fixture is an older page copy —
  different WordPress size variants) plus the expected `lastBuildDate`
  change; content/items identical, so behavior preserved.

## Verification

- `.venv/bin/pytest`: 373 passed (355 baseline + 1 cache test + 17
  rock-monsieur).
- Refactor sanity: offline chansons rebuild vs. committed feed — identical
  apart from `lastBuildDate` and fixture-age image drift.
- Live run 1: 12 episodes parsed, 12 enclosures resolved. Live run 2 (after
  cache fix): 0 resolutions, output byte-identical except `lastBuildDate`.
- Enclosure URL verified: HTTP 200, `audio/mpeg`, 55981809 bytes,
  `Accept-Ranges: bytes`.

## Status

done
