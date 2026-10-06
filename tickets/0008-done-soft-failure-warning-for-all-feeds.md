# 0008: Soft-failure warning item for all feed builders

## Problem

CI run 2026-10-05 failed: Quora direct fetch got 403, the r.jina.ai fallback
returned HTTP 200 but with a rate-limit/error body (no answer links) because
the `JINA_API_KEY` secret is not set on the repo. `parse_dom` found 0 answers,
`build_quora_feed.py` exited 1, and `bash -e` aborted the whole "Build feeds"
step — klum, brf-chansons and all 5 Instagram builds never ran, nothing was
committed. One flaky feed takes down the entire weekly update.

Ticket 0007 already solved this for Instagram: soft failures write a rolling
"Feed build failed" item into the feed and exit 0. The other three builders
(quora, klum, brf) still hard-fail with exit 1.

## Approach

- Generalized the warning-item mechanism into `common.py`:
  - `build_warning_item(warning_url, exc)` — stable id `<url>#build-status`,
    description = error, content = stacktrace in `<pre>`, published = now
    (works outside `except` blocks via `exc.__traceback__`).
  - `without_warning(previous)` — drop stale warning entries on success.
  - `write_warning_feed(output_path, max_items, warning_url, exc, **kwargs)`
    — previous items + one warning item, exit 0.
  - Prints a GitHub Actions `::warning::` annotation (newline-collapsed to a
    single line) so breakage is visible on the run, not only in the XML.
- Applied to `build_quora_feed.py`, `build_klum_feed.py`,
  `build_brf_chansons_feed.py`: fetch failure, jina fallback failure,
  unparseable page → warning feed + `::warning::`, exit 0. Success strips
  stale warning entries from previous.
- Quora diagnostic: when parsing yields 0 items, log the first 300 chars of
  the fetched page so CI can distinguish rate-limiting from layout changes.
- Quora also got the offline guard Instagram had: with `QUORA_PROFILE_HTML`
  set, a failed direct parse no longer silently hits r.jina.ai (network).
- Refactored `build_instagram_feed.py` to use the shared helpers (kept its
  previous-feed metadata fallback); dropped its local copy of the mechanism.
- Updated the workflow comment ("Instagram is the flakiest source" → all
  builders soft-fail).

## Manual (outside repo)

Set the `JINA_API_KEY` repository secret (free key from jina.ai). Without it
Quora keeps hitting rate-limit pages on shared runner IPs and every weekly
run will carry a warning item instead of fresh answers.

## Hurdles

- The CI log showed "0 answers parsed" with no fetch error: r.jina.ai serves
  rate-limit/error bodies with HTTP 200, so `fetch_jina`'s retry loop sees
  success. Only the API key prevents it (not fixable in code without knowing
  the exact error-body format).
- `QUORA_PROFILE_HTML` & co. take a file path, not inline HTML — synthetic
  test pages must be written to disk first.
- Quora answer permalinks are `/<question-slug>/answer/Alan-Kay-11` (the
  `ANSWER_PATH` regex requires the `-Alan-Kay-11` suffix); the synthetic
  fixture needed that exact shape.
- Test bug (twice, klum + brf): the "success removes stale warning" tests
  forgot to restore the real `fetch_page` after the failure phase, so phase 2
  re-failed. Same bug class as in ticket 0007.
- `bk.common.fetch_page = common.fetch_page` in a debug script was a no-op
  self-assignment (same module object) — the stub stayed active and sent me
  chasing a nonexistent production bug.

## Verification

- `.venv/bin/pytest`: 157 passed (128 baseline + 10 common + 9 quora + 6 klum
  + 5 brf, minus 1 replaced hard-fail test).
- Offline E2E: `QUORA_PROFILE_HTML=/dev/null` → exit 0, `::warning::` on
  stdout, "Feed build failed" item added, previous 3 items kept; real feed
  restored via git.

## Status

done
