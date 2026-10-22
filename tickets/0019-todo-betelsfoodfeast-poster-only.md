# 0019: betelsfoodfeast feed is poster-only (initial build without session env)

## Problem

The `betelsfoodfeast` feed shows the poster still ("screenshot") instead of
the embedded video for its posts. Same failure mode as ticket 0018
(moritz.huertgen), where a weak parse's poster-only content won.

Live diagnosis (2026-10-22):

- `feeds/instagram-betelsfoodfeast.xml` (added in 7b2a779, built ~08:59
  manually): all 12 items have `image/jpeg` enclosures and day-precision
  `00:00:00` pubDates → everything came from the direct profile parse;
  neither the web_profile_info API nor permalink enrichment contributed.
- `journalctl` has no betelsfoodfeast entries: the timer (last run Oct 21,
  ending at sveamaus) predates the account's addition to
  `update_local.sh`, so the initial build was a manual run — evidently
  without `INSTAGRAM_SESSIONID` sourced, hence no API parse and no
  permalink enrichment.
- Session check: `check_instagram_session.py betelsfoodfeast` →
  `rate_limited` (fake 429 after 10s/30s backoff; tickets 0013/0015).
  The cookie itself still works: a permalink fetch with the sessionid
  returns the full item (`parse_permalink`: 1 `<img>`, 1 `<video>`,
  enclosure `video/mp4`, `2026-10-21 15:00:37+00:00`).

No code bug: ticket 0018's media-score fix already handles the upgrade.
The fix is a rebuild with the session env sourced, exercising the
direct-parse → permalink-enrichment path.

## Approach

- Source `~/.config/rss-feeds/env`, rebuild
  `scripts/build_instagram_feed.py betelsfoodfeast`, verify videos
  (`<video>` tags, `video/mp4` enclosures) and exact pubDates appear.
- Baseline before changes: 272 passed (no code change expected).

## Hurdles

- (recorded during implementation)

## Status

todo
