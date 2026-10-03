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
- `previous_feed_metadata()` re-reads channel title/description from the old
  XML so failure feeds keep the previous feed's metadata (failure builds
  have no profile page to parse).
- Workflow: simple `for account in …` loop over all 5 accounts, drop the
  `|| echo ::warning::` workaround (script exits 0 on soft failures; typos
  still exit 2 and fail the step).
- Housekeeping: `venv/` renamed to `.venv/` so local setup matches
  AGENTS.md/README across machines; stale `.gitignore` entry removed.

## Hurdles

- Renaming `venv/` → `.venv/` broke the absolute paths baked into the venv's
  console scripts (`bin/pytest`, `bin/pip*`, `bin/activate*`) and
  `pyvenv.cfg`; fixed with `sed` over `.venv/bin/*` + `pyvenv.cfg`, verified
  with `.venv/bin/pytest` (122 passed) and `.venv/bin/pip --version`.
- Test bug (red phase): `_fail_fetch` monkeypatched `common.fetch_page` for
  the whole test, so the "success clears the warning" phase still hit the
  raising stub. Fixed the test by capturing the real fetcher and re-setting
  it mid-test, not the implementation.
- `html_mod.escape()` default escapes quotes too; inside feedgen's already
  escaped `content:encoded` that rendered as `&amp;quot;`. Switched to
  `quote=False` (`<`, `>`, `&` suffice for a stacktrace).
- Live builds: `martinmaleschka`, `tumvlt`, `jamborjoanna` → 12 posts each.
  `kultur_bei_racha_roger` (public, has bio) got a profile shell without
  embedded media (`all_media_count: null`, no `__isXIGPolarisMedia` nodes) —
  Instagram's anonymous-fetch variance; r.jina.ai fallback 403s without an
  API key from this IP. Result: the new warning feed, live — exactly the
  designed behavior. CI (JINA_API_KEY, different IP) should fill the feed on
  the next run; committed the warning feed as valid output.

## Verification

- `.venv/bin/pytest`: 128 passed (122 baseline + 7 new warning tests, 1
  outdated test updated).
- Offline end-to-end: `INSTAGRAM_PROFILE_HTML=/dev/null` → feed with 13
  items (warning + 12 previous posts), stacktrace in `content:encoded`,
  stable guid; real feed restored afterwards.
- Live: 4 new feeds generated and committed.

## Status

done
