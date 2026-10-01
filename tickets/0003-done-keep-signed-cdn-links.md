# 0003: Keep signed CDN media links (and expose them as enclosures)

User objection to ticket 0001's "expiring signed CDN links are rejected"
behavior (scripts/build_klum_feed.py `_best_link`): it deliberately
discards valuable information. Currently exactly one item ("Der
Möchtegernekanzler", 21.09.2026) links to a signed, expiring WhatsApp
video mp4 on `cdn.website-editor.net`; it was reduced to the news page
URL.

## Context

- Signed CDN URLs carry `Expires=`/`Signature=` and die when they lapse.
- Weekly CI rebuilds fetch the news page anew, which serves a *fresh*
  signature — the stored URL stays live as long as the item is listed.
  It only rots after the item scrolls off the page.

## Decision (user)

Keep signed CDN media URLs **both** as the item `<link>` **and** as an
RSS `<enclosure>` (belt and suspenders; podcast-style apps can play the
enclosure directly).

## Plan (strict red/green, small commits)

1. `scripts/common.py`: `build_feed` writes `<enclosure url length type>`
   for items carrying `enclosure`; `load_previous` reads `<enclosure>`
   back; `merge_items` carries an old enclosure when the new item lacks
   one (fresh wins when present).
2. `scripts/build_klum_feed.py`: `_best_link` no longer rejects
   `cdn.website-editor.net` / `le-cdn.website-editor.net` (signed or
   not) — such hrefs become the item link and an `enclosure`
   (MIME from extension; `fetch_content_length` via HEAD, fallback 0,
   stubbed in tests). Update `test_newest_item` and the docstring.
3. README rewrite of the "rejected" sentence; live rebuild to verify.

## Hurdles

- The feedgen `<enclosure>` attribute order is fixed (url, length, type);
  the round-trip test asserts the exact serialized form.
- Bare `href="https://cdn.website-editor.net"` links exist in the page's
  `<head>` boilerplate — outside `dmRespCol` columns, so the parser never
  sees them; media detection additionally requires a non-root path.
- `Content-Length` came back fine from a live HEAD request (27,029,278
  bytes for the mp4); failure paths fall back to length 0 (tests stubbed).

## Result

- "Der Möchtegernekanzler" (21.09.2026): `<link>` is the signed mp4 URL,
  plus `<enclosure type="video/mp4" length="27029278">`; a fresh signature
  is stored on every weekly rebuild while the item remains listed.
- 68 items, 14 embedded articles, 1 enclosure — no regressions (74 tests).

## Status

- [x] ticket draft committed
- [x] phase 1: enclosure round-trip in common.py
- [x] phase 2: keep CDN links + enclosures in klum parser
- [x] rebuild, README, ticket done
