# 0017: Adaptive Instagram stagger instead of fixed 45s sleep

## Problem

`update_local.sh` sleeps 45s between each of the 11 Instagram builds —
**8.25 minutes of pure sleep per run**, ~95% of total runtime (measured
2026-10-09, ticket 0016: ~12-15 min total, ~3-4 min actual fetching).
The stagger protects against Instagram's 429 rate limit (ticket 0013),
but it is paid unconditionally, even when the rate budget is completely
free (e.g. first run after two idle days) — and it slows down every
manual/verification run too.

## Approach

Make the stagger reactive instead of unconditional:

- Default delay between Instagram builds drops to 2s.
- New `scripts/instagram_stagger.py` runner builds the accounts in
  sequence and owns the backoff state; `update_local.sh` calls it once
  instead of looping/sleeping itself.
- `build_instagram_feed.py` prints a machine-readable marker
  (`::instagram-throttled::`) when a **permalink** fetch gets a 429.
  A `web_profile_info` 429 is ignored for staggering: tickets 0013/0015
  established that endpoint returns a fake/neutered 429 even when the
  session works, and permalinks then succeed. Profile-page 429s already
  fall back to jina inside `fetch_page`.
- Backoff: no throttle → keep 2s; first 429 → 45s before the next
  account; further 429s → 90s, then cap at 180s. Once throttled, keep
  the cautious delay for the rest of the run.
- Soft-fail behaviour stays untouched: a persistent 429 still ends in a
  "Feed build failed" warning item, never a hard abort mid-run.

TDD: `next_delay()` and the runner loop are unit-tested before changing
the script wiring; the builder marker is covered by enrichment/main
tests.

## Hurdles

- The script list had grown to **13** accounts (ticket text said 11/12);
  the old loop slept 45s even after the last build.
- `web_profile_info` 429s must not count as throttle markers: they are
  the known fake/neutered response (0013/0015) and occurred during the
  real verification run while every permalink succeeded. Counting them
  would have kept the unconditional sleep forever.
- Only permalink enrichment can report a real throttle; profile-page
  429s already fall back to jina inside `common.fetch_page`.
- Backoff deliberately persists after a throttle for the rest of the
  run, so a persistently throttled run can be slower than the old fixed
  45s (45→90→180 cap). That is the intended protection.
- Did not run the full `update_local.sh` because it auto-pushes; the
  runner was exercised on one real account instead. The next timer run
  applies it to all accounts.

## Verification

- Baseline 257 passed → final `pytest`: **272 passed**.
- `next_delay`/runner red→green: default 2s, first 429 45s, then
  90/180 cap, cautious delay retained after success, failures abort,
  output passed through.
- Builder: permalink 429 returns `True` from `enrich_with_slides` and
  prints `::instagram-throttled::`; successful enrichment does not.
- Real runner integration: `python scripts/instagram_stagger.py
  moritz.huertgen` exit 0, 76.6s, no marker (API 429 ignored, all 12
  permalinks parsed), feed refreshed and committed.
- Sleep budget: old loop 13×45 = 585s; new unthrottled run 12×2 = 24s
  (~9.35 min saved).

## Status

done
