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

## Approach

Since the chansons builder is 100% reusable except for constants, and more
BRF1 shows could follow, extract instead of copy:

1. New `scripts/brf1_show_feed.py` with all parsing/enrichment/main logic
   from `build_brf_chansons_feed.py`, parametrized by a frozen `ShowConfig`
   (slug, title, description, image, output path, env prefix, max_items).
   Config is passed explicitly to functions (no shared mutable module
   state — both test modules run in one pytest process).
2. `build_brf_chansons_feed.py` becomes a thin wrapper with the Chansons
   config; existing tests keep passing (patch targets move to the shared
   module).
3. `scripts/build_brf_rock_monsieur_feed.py` wrapper: slug `rock-monsieur`,
   title "Rock Monsieur (BRF1)", output `feeds/brf1-rock-monsieur.xml`,
   env prefix `ROCK_MONSIEUR` (`ROCK_MONSIEUR_HTML`, `ROCK_MONSIEUR_PAGES_DIR`,
   `ROCK_MONSIEUR_PLAY_DIR`).
4. Fixtures: archive page, one episode page (1231559), one play snippet
   (`568fbf`); new test file mirroring the chansons tests.
5. Wire into `scripts/update_local.sh` + README (feeds table, local dev).
6. Strict red/green TDD, phases committed separately; live run twice
   (2nd run must be cache-hit/byte-identical), HEAD-verify an enclosure.

## Status

todo
