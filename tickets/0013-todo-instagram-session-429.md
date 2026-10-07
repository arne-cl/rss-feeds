# 0013: Instagram session API 429 — feeds silently stuck cover-only

## Problem

The user's feeds contain **zero multi-slide carousel items** (every item
holds exactly 1 `<img>` = cover), although ticket 0011 builds slides
from the session API. Root cause chain, verified 2026-10-07:

- `~/.config/rss-feeds/env` has `INSTAGRAM_SESSIONID`, and
  `systemd/rss-feeds-update.service` loads it (the timer itself is NOT
  installed on this machine — builds are manual `update_local.sh` runs,
  last one today ~12:45).
- The sessionid is **valid but throttled**: API returns
  `HTTP 429` (with cookie) vs `401` (anonymous). Probed 3× across an
  hour, two accounts — consistent 429.
- `main()` treats API failure as soft: logs "session api fetch failed",
  falls back to the direct profile-page parse → cover-only content.
  1 img vs 1 img means `restore_richer_content` never downgrades, but
  nothing ever upgrades either → feeds stay slide-less silently.
- Process failure (mine): I built the XSLT preview (ticket 0012) on top
  without ever checking that the session — the data source for the very
  slides the preview is meant to show — actually works.

## Decisions

- User-requested rule in `AGENTS.md`: **verify secrets/env actually
  work (real test call, result recorded in the ticket) before building
  features/fixes on top of them.**
- New `scripts/check_instagram_session.py [account]`: single API call,
  classify `ok` / `rate_limited` (429) / `auth_failed` (401, 403) /
  `error`; exit 0/2/3/4; never prints the cookie. Classifier is a pure
  function → offline unit tests.
- `fetch_api_profile`: retry 429 twice (10s, 30s backoff) to ride out
  transient blips; soft fallback unchanged.
- `update_local.sh`: `sleep 45` between the 12 instagram account builds
  (~9 min extra per run) to protect the rate budget.
- Fresh sessionid: user logs into instagram.com in Chromium and copies
  `sessionid` from DevTools → Application → Cookies (HttpOnly, so
  `document.cookie` won't show it) into `~/.config/rss-feeds/env`.
  Validity checked with the new script. A fresh login usually starts
  with a clean rate-limit budget. Caveats: don't log out of that
  browser afterwards (invalidates the sessionid); if a fresh session
  also 429s instantly, the throttle is IP-based and only waiting helps.
- Playwright-based login helper: separate ticket (0014), planned after
  this one.

## Acceptance

1. Checker exits 0 against the (fresh) sessionid.
2. `update_local.sh` rebuild produces items with >1 `<img>` on carousel
   posts, feeds committed/pushed as usual.
3. Headless Chromium + Firefox screenshots (`--virtual-time-budget` so
   CDN images load) of a real multi-slide entry via the local preview
   server (ticket 0012), checked before showing the user.

## Hurdles

- Retry loop bug caught by tests: first attempt logged the not-yet-known
  backoff delay (`%d` on `None`); restructured to index retry delays by
  attempt number.
- `test_api_failure_falls_through_to_jina` became 40s slow (its
  `RuntimeError("429 …")` message now legitimately triggers the retry
  backoff) — stubbed `time.sleep` there; overall suite back to ~7s.
- Committed once with a failing test because `pytest | tail` masked the
  exit code; re-ran, fixed the fake-response bug in the new test, and
  amended practice: check `${PIPESTATUS[0]}` / avoid piping pytest.
- Live checker run confirms the toolchain end-to-end: backoff fires
  twice, then `rate_limited: daxwerner — HTTPError: HTTP Error 429:`
  exit 2. Throttle still active at ~16:20 (3h after the 12:45 build) —
  Phase C (rebuild + real-feed screenshots) blocked until the user
  swaps in a fresh sessionid (Phase B) or the throttle lifts.

## Status

todo (Phase A done; Phase B = user login; Phase C = rebuild + screenshots)
