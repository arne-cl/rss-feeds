# 0014: Playwright-based Instagram session helper (login + auto-refresh)

## Problem

Rotating `INSTAGRAM_SESSIONID` (ticket 0013) is manual fiddling: log in,
hunt for the HttpOnly `sessionid` cookie in DevTools, paste it into
`~/.config/rss-feeds/env`, verify by hand. Worse, the cookie dies every
few weeks and the daily feed build degrades to cover-only posts until
someone notices.

Goal: run one script, log in once in the browser window that opens —
and after that, keep the session rolling automatically.

## Approach (revised 2026-10-22: option 2 — helper + auto-refresh)

One script `scripts/instagram_login.py` with two subcommands, sharing
all cookie/verify/env code. Dependency: `playwright` (requirements.txt).
Launches the **system Chromium** via `executable_path="/usr/bin/chromium"`
so playwright does NOT download its own ~160 MB browser build. If
playwright refuses system chromium (protocol mismatch), fall back to
`channel="chromium"` download or raw CDP via `websocket-client`
(decision recorded here when known).

Persistent browser profile: `~/.config/rss-feeds/ig-profile` (chmod 700,
never in the repo). The Instagram session lives in this profile; both
subcommands reuse it.

### `login` (manual, headful, run from the GUI session)

1. Launch persistent context with the ig-profile dir, headful, open
   instagram.com.
2. Poll `context.cookies()` every ~2s (timeout ~5 min) until a
   `sessionid` cookie for instagram.com appears — the user just logs
   in (incl. 2FA) in the window.
3. **Verify before write**: one `web_profile_info` API call with the
   fresh cookie (reuse `common.fetch_direct` + ticket 0013's
   classifier via a `session_id=` param on
   `build_instagram_feed.fetch_api_profile`). Only a verified-working
   cookie is stored; on 429 warn loudly (valid but throttled) and let
   the user decide.
4. Rewrite `~/.config/rss-feeds/env`: replace the existing
   `INSTAGRAM_SESSIONID=` line or append; `chmod 600`; atomic write;
   never print or log the cookie value.
5. Close the browser (never click logout — that invalidates the
   session). Output: `ok: fresh session verified (N posts parsed)`.

### `refresh` (unattended, headless, called from update_local.sh)

1. Headless: load instagram.com in the persistent profile, extract the
   (possibly rotated) `sessionid` via `pick_cookie(context.cookies())`.
2. `refresh_policy(stored_status, candidate, candidate_status)` — pure
   decision function:
   - candidate == stored → nothing to do;
   - candidate differs and verifies OK → rewrite env (verified-new);
   - candidate differs, 429 → adopt only if the stored cookie
     auth-fails, else keep stored;
   - no sessionid in profile (login wall / session died) → exit 3 with
     `run: scripts/instagram_login.py login`, keep stored.
3. Exit codes: 0 ok/updated · 3 session expired (manual login needed)
   · 4 error. Never fatal for the caller.

### Automation hook

`scripts/update_local.sh` calls `instagram_login.py refresh` right
before `instagram_stagger.py` (freshest cookie for the builds). Non-
fatal (`|| true`), journal-visible. No new systemd units — the existing
daily timer runs update_local.sh. Regular *use* of the profile session
is what keeps it alive; the touch happens daily.

## Testability (red/green)

Pure functions offline-tested (no browser, no network):

- `update_env_file(path, value)` — replace / append / preserve other
  lines / perms 600 / atomic.
- `verify_sessionid(value)` with mocked `fetch_direct` (ok / 429 /
  401 paths).
- `pick_cookie(cookies)` — playwright cookie list shape.
- `refresh_policy(...)` — all decision branches.
- `wait_for_sessionid(context, timeout)` — timeout math only.

## Hurdles

- Playwright 1.64.0 + system `/usr/bin/chromium`: `executable_path`
  works out of the box, headless and headful — no fallback needed, no
  browser download.
- Pre-work session check: `check_instagram_session.py` → 429 (with the
  10s/30s backoff), garbage cookie → 401, stored cookie → 429 ⇒ cookie
  **valid but throttled** (0013's classifier methodology). Authed
  permalink fetch with the same cookie: 200, item parses. Session was
  fine; only web_profile_info was hot.
- `verify_sessionid` inherits `fetch_api_profile`'s bounded 429
  backoff (10s+30s) — a refresh on a throttled API costs ~40s before
  deciding. Acceptable for the daily unattended run (it happens before
  the builds anyway); not fixed.
- First live `login` run: the window + login + cookie grab all worked,
  but the 429-store decision hit an interactive `input()` from a
  non-TTY → EOFError traceback, cookie not stored. Fix: `--store-throttled`
  flag to pre-answer, `isatty()` guard with a clean message instead of
  the prompt, flag tested via `parse_args`.
- Second `login --store-throttled` run: found the existing session in
  the persistent profile instantly (no second login), stored the cookie.
- `refresh` fast path verified: headless touch finds the same sessionid
  → "ok: session unchanged", **zero** API calls on the common path.
- Test-side own goals: a bytes fixture split across lines without
  parentheses (second literal silently became a no-op expression →
  JSON parse failed), and `Path.write_text(mode=)` doesn't exist.
  `update_env_file` gained `makedirs` for the missing-parent case.
- Output interleaving made it look like verification ran before the
  browser window opened — logging (stderr, unbuffered) vs print
  (stdout, line-buffered on tty but block-buffered when piped); cosmetic.

## Verification

- `.venv/bin/pytest`: 287 baseline → 325 passed (38 new
  `tests/test_instagram_login.py`, red→green per phase).
- Live: `refresh` with empty profile → kept stored cookie (exit 0);
  `login` → user logged in incl. 2FA; `login --store-throttled` →
  fresh cookie stored, exit 0; `refresh` again → "session unchanged",
  exit 0; `check_instagram_session.py` → rate_limited (throttle, see
  hurdles); authed permalink fetch with the new cookie → 200 +
  parse_permalink finds the item.
- `~/.config/rss-feeds/env`: still 600, `JINA_API_KEY` preserved,
  cookie never printed anywhere.

## Status

done
