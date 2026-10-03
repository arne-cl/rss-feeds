# 0007: More Instagram accounts, in-feed failure warning

## Problem

1. Add RSS feeds for four more Instagram accounts (workflow only, no README
   rows): `kultur_bei_racha_roger`, `martinmaleschka`, `tumvlt`, `jamborjoanna`.
2. Instagram build failures currently only surface as a CI `::warning::` log
   line; subscribers see a stale feed with no hint. Instead, the generated
   feed itself should carry a warning item (with error and stacktrace).

## Approach

- `build_instagram_feed.py`: on soft failures (fetch, jina fallback,
  unparseable page) write previous feed + one warning item and exit 0:
  - title "Feed build failed", description = error, content = stacktrace in
    `<pre>`, published = now, link = profile URL.
  - Stable item id (`<profile-url>#build-status`) so repeated failures
    replace the entry instead of accumulating (merge-by-id).
  - Next successful build drops the `#build-status` entry from `previous`.
  - Usage/invalid-account errors keep exit 2.
- Workflow: simple `for account in …` loop over all 5 accounts, drop the
  `|| echo ::warning::` workaround (script exits 0 on soft failures; typos
  still exit 2 and fail the step).
- Housekeeping: `venv/` renamed to `.venv/` so local setup matches
  AGENTS.md/README across machines; stale `.gitignore` entry removed.

## Hurdles

- (to be filled during implementation)

## Status

todo
