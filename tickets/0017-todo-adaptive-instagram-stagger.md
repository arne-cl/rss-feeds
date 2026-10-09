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

- Default delay between Instagram builds drops to ~0-2s.
- Track 429s from the profile/permalink fetches (the builders already
  classify them); on the first 429, sleep the current 45s before the
  next account, and keep backing off for the rest of the run
  (e.g. exponential 45s → 90s → 180s, capped).
- The backoff state lives in the update script (shell) or the build
  script (exit code / stdout marker) — decide during implementation;
  keep `update_local.sh` readable.
- Soft-fail behaviour stays untouched: a persistent 429 still ends in a
  "Feed build failed" warning item, never a hard abort mid-run.

TDD: characterise the backoff decision (429 seen → delay, none → no
delay, repeated 429s → grow up to cap) in `tests/` before changing the
script wiring.

## Hurdles

(to be filled during implementation)

## Verification

(to be filled: full `update_local.sh` runtime before/after, no new
429-driven warning feeds, pytest count)

## Status

todo
