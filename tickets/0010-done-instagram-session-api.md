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
  `--remote-debugging-port=9222`, rodney `connect`ed) via CDP
  `Storage.getCookies`; write `~/.config/rss-feeds/env` (mode 600).
- Replace the HTML retry with the `web_profile_info` JSON API
  (`/api/v1/users/web_profile_info/?username=…` + `x-ig-app-id` header +
  sessionid cookie): `fetch_api_profile()` + `parse_api()`.
- `parse_api()` tolerates both response shapes: web_profile_info's
  `data.user.edge_owner_to_timeline_media` (GraphAPI: shortcode,
  taken_at_timestamp, edge_media_to_caption, display_url) *and* the app
  GraphQL's `data.xdt_api__v1__feed__user_timeline_graphql_connection`
  (xdt: code, taken_at, caption.text, image_versions2/video_versions).
- API failures (e.g. 429) are soft: fall through to the jina DOM fallback.

## Hurdles

- rodney 0.4.0 wheel is headless-only (`start --show` rejected) → launched
  real Chromium with `--remote-debugging-port` + `rodney connect`.
- CDP websocket handshake 403s with an Origin header →
  `websocket.create_connection(..., suppress_origin=True)`.
- `sessionid` is HttpOnly → `rodney js document.cookie` can't see it;
  needed CDP `Storage.getCookies`.
- `web_profile_info` rate-limits (429) aggressively per IP+account: our
  ~12 probing calls bought a long ban window; raw curl_cffi AND in-browser
  fetch both throttled. Production calls it ≤1×/run so this only bites
  during testing. Gotcha: the endpoint can return HTTP 200 with the *HTML
  shell* — always check the body starts with `{`.
- `/api/v1/feed/user/<user>/username/` serves the SPA shell, not JSON.
- To get *real* media JSON while throttled: sniffed the app's own
  `POST /api/graphql` responses via CDP (attach to page target →
  `Network.enable` **per session** — browser-level enable gets no page
  events → `Page.navigate` → `Network.getResponseBody`). Captured the full
  12-post timeline; trimmed 3 nodes (carousel/video/image) into
  `tests/fixtures/instagram-tiny-ruins-timeline.json` (46 KB).
- xdt nodes: `display_uri` can be empty — resolve media via
  `image_versions2.candidates[0].url`; videos via `video_versions[0].url`.
- `pgrep -f <pattern>` matches the invoking shell's own command line —
  `pkill` then kills the shell itself; use the `-[r]` bracket trick.
- Live `web_profile_info` 200 validation still pending (throttle) — shape
  coverage is via the captured GraphQL data instead; the 4 weekly accounts
  parse anonymously anyway, and a 429 degrades softly to jina/warning.

## Verification

- `.venv/bin/pytest`: 174 passed (13 parse/fallback tests on synthetic
  GraphAPI fixture + 4 on the captured real-shape fixture; full capture
  parses 12/12 posts).
- CDP cookie extraction: saved `INSTAGRAM_SESSIONID` to
  `~/.config/rss-feeds/env` (mode 600), confirmed live (pages differ,
  401→429 class change, browser logged in as user verified).
- Browser session + logged-in Chromium profile deleted after extraction.

## Status

done
