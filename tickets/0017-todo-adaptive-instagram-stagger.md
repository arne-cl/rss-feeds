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

(to be filled during implementation)

## Verification

(to be filled: full `update_local.sh` runtime before/after, no new
429-driven warning feeds, pytest count)

## Status

todo
