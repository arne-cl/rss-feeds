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

- The initial commit 7b2a779 contained both `update_local.sh` and the
  poster-only feed: the feed was built before the env was sourced. The
  very next timer run (which would have self-healed the feed via
  permalink enrichment) hadn't happened yet, and the journal silence
  initially looked like "timer broken" rather than "manual build
  without env". Git history of the feed file (`add IG feed` vs the
  timer's `Update feeds` commits) disambiguated this.
- `web_profile_info` is hard-429'd right now (even with the valid
  session), so every build pays the 10s/30s backoff before falling
  back to direct+permalink — same as tickets 0013/0015; the cookie
  itself works (verified via permalink fetch).

## Verification

- `.venbin/pytest` before and after: 272 passed (no code change).
- Live permalink check before rebuild: `parse_permalink` for
  `DewrImEgtHx` → 1 `<img>`, 1 `<video>`, `video/mp4`,
  `2026-10-21 15:00:37+00:00`.
- Real rebuild with env sourced (direct parse + 12 permalink
  enrichments, ~40s API backoff): 11/12 items now carry
  `video/mp4` enclosures with `<video controls>` players (carousel
  items 3 and 5 slides), one genuine photo post stays `image/jpeg`;
  all pubDates are exact timestamps (`Wed, 21 Oct 2026 15:00:37` etc.,
  zero `00:00:00` left).

## Status

done
