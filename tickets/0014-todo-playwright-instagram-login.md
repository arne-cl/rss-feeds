# 0014: Playwright-based Instagram login helper

## Problem

Rotating `INSTAGRAM_SESSIONID` (ticket 0013) is manual fiddling: log in,
hunt for the HttpOnly `sessionid` cookie in DevTools, paste it into
`~/.config/rss-feeds/env`, verify by hand. A helper should reduce this to
"run one script, log in once in the browser window that opens".

## Approach (plan)

- New `scripts/instagram_login.py`, dependency: `playwright` (added to
  `requirements.txt`). Launch the **system Chromium** via
  `executable_path="/usr/bin/chromium"` so playwright does NOT download
  its own ~160 MB browser build. If playwright refuses system chromium,
  fall back to `channel="chromium"` download or raw CDP via
  `websocket-client` (decision recorded here when known).
- Flow:
  1. Launch persistent context with a throwaway `--user-data-dir`
     (NOT the user's real profile), headful, open instagram.com.
  2. Poll `context.cookies()` every ~2s (timeout ~5 min) until a
     `sessionid` cookie for instagram.com appears — the user just logs
     in (incl. 2FA) in the window.
  3. Grab `sessionid`; close the browser (never click logout — that
     invalidates the session).
  4. **Verify before write**: one `web_profile_info` API call with the
     fresh cookie (reuse `common.fetch_direct` + ticket 0013's
     classifier). Only a verified-working cookie is stored; on 429 warn
     loudly (valid but throttled) and let the user decide.
  5. Rewrite `~/.config/rss-feeds/env`: replace the existing
     `INSTAGRAM_SESSIONID=` line or append; `chmod 600`; never print or
     log the cookie value.
- Output: `ok: fresh session verified (N posts parsed)` and a reminder
  to run `scripts/check_instagram_session.py` / `update_local.sh`.

## Testability (red/green)

- Pure functions offline-tested: `update_env_file(path, value)` (replace
  / append / preserve other lines / perms) and `verify_sessionid(value)`
  with mocked `common.fetch_direct` (ok / 429 / 401 paths).
- Browser polling part isolated in `wait_for_sessionid(context,
  timeout)`; tested only for its timeout math, not with a real browser.

## Hurdles

- (to be filled during implementation)

## Status

todo
