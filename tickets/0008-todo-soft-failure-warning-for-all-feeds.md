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

- Generalize the warning-item mechanism into `common.py`:
  - `build_warning_item(warning_url, exc)` — stable id `<url>#build-status`,
    description = error, content = stacktrace in `<pre>`, published = now.
  - `without_warning(previous)` — drop stale warning entries on success.
  - `write_warning_feed(output_path, max_items, warning_url, exc, **kwargs)`
    — previous items + one warning item, exit 0.
  - Emit a GitHub Actions `::warning::` annotation (single line) so breakage
    is visible on the run, not only inside the feed XML.
- Apply to `build_quora_feed.py`, `build_klum_feed.py`,
  `build_brf_chansons_feed.py` (fetch failure, jina fallback failure,
  unparseable page → warning feed, exit 0; usage errors keep exiting 2 where
  applicable). On success, strip stale warning entries from previous.
- Quora bonus diagnostic: when parsing yields 0 items, log a short excerpt of
  the fetched HTML so CI logs distinguish "rate-limited" from "layout changed".
- Refactor `build_instagram_feed.py` to use the shared helpers (keep its
  previous-feed metadata fallback for failure builds).
- Update the workflow comment ("Instagram is the flakiest source" no longer
  true).

## Manual (outside repo)

Set the `JINA_API_KEY` repository secret (free key from jina.ai). Without it
Quora keeps hitting rate-limit pages on shared runner IPs.

## Hurdles

(tbd)

## Status

todo
