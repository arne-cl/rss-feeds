# 0010: Instagram session-cookie fallback that actually works

## Problem

The `INSTAGRAM_SESSIONID` fallback added in ticket 0009 retries the *HTML*
fetch with the cookie — but probing showed the logged-in profile HTML
contains **no embedded media JSON** (Instagram's logged-in web app is a
shell that hydrates posts via XHR). So that fallback could never parse
anything. Also: `kultur_bei_racha_roger` shows "0 posts" even in a real
logged-in browser — the account is empty, its warning feed is correct.

## Approach

- Extract `sessionid` from a logged-in Chromium (launched with
  `--remote-debugging-port`, rodney `connect`ed) via CDP
  `Storage.getCookies`; write `~/.config/rss-feeds/env` (mode 600).
- Replace the HTML retry with the `web_profile_info` JSON API
  (`/api/v1/users/web_profile_info/?username=…` + `x-ig-app-id` header +
  sessionid cookie): `fetch_api_profile()` + `parse_api()` (tolerates both
  GraphAPI edges and xdt-style nodes, `taken_at*` timestamps, video_url /
  display_url / image_versions2 candidates).
- API failures (e.g. 429 rate limit) are soft: fall through to the jina
  DOM fallback as before.

## Hurdles

- rodney 0.4.0 wheel is headless-only (`start --show` rejected) → launched
  real Chromium with `--remote-debugging-port=9222` and used
  `rodney connect`.
- CDP websocket handshake 403s with an Origin header →
  `websocket.create_connection(..., suppress_origin=True)`.
- `sessionid` is HttpOnly → `rodney js document.cookie` can't see it;
  needed the CDP cookie call.
- `web_profile_info` rate-limits (429) aggressively per IP+account; raw
  curl_cffi AND in-browser fetch both throttled after a handful of calls.
  `/api/v1/feed/user/<user>/username/` serves the SPA HTML shell (mobile-API
  only), not JSON — dead end. Background probe retries every 5 min until a
  real 200 lands; parser validated against it once available.
- Gotcha: fetching an API URL can return HTTP 200 with the *HTML shell* —
  always check the body starts with `{`.

## Status

todo
