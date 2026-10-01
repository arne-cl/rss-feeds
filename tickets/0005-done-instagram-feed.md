# 0005: Instagram feed for tiny_ruins, configurable per account

## Problem

No RSS feed exists for http://instagram.com/tiny_ruins (Instagram provides
none). The builder must be reusable for other Instagram accounts.

## Approach

1. Probed the anonymous profile page: direct fetch with Chrome TLS
   impersonation returns HTTP 200 with embedded
   `<script type="application/json">` blobs containing
   `polaris_ordered_timeline_connection.edges[].node` media objects
   (12 posts for tiny_ruins).
2. `scripts/build_instagram_feed.py <account>` (account as required arg,
   validated `^[A-Za-z0-9._]{1,30}$`, output `feeds/instagram-<account>.xml`):
   - Strategy 1: walk *all* embedded JSON blobs generically (no hardcoded
     JSON path) for `__isXIGPolarisMedia` nodes. Fields: `code` → post URL,
     `caption.text` → title (first line) / description (full),
     `display_uri` → image enclosure + HTML content, date parsed from
     `accessibility_caption` ("… on September 23, 2026.").
   - Strategy 2 (fallback): r.jina.ai rendered DOM, parse `/p/<code>/` links,
     image alt texts as titles.
   - Profile JSON (`full_name`, `biography`) feeds the feed metadata
     ("Tiny Ruins on Instagram").
   - Reuses `scripts/common.py`, `MAX_ITEMS=100`, offline mode via
     `INSTAGRAM_PROFILE_HTML=<file>`.
3. Fixture `tests/fixtures/instagram-tiny-ruins.html`, tokens scrubbed;
   21 tests in `tests/test_build_instagram_feed.py`, strict red/green.
4. CI builds `tiny_ruins` last and non-fatal (`|| echo ::warning::…`).
5. README: feeds table row + local-dev hint.

## Hurdles

- Anonymous payload has no `taken_at` timestamp; only
  `accessibility_caption` carries a date string. Missing date → `None`
  (merge keeps previously stored dates).
- Fixture scrubbing: the token values appear multiple times in different
  encodings (raw JSON, escaped-in-string `J{\"qeid\":…}` blobs) — the
  `datr` value alone had to be replaced globally (1 context-level + 1
  escaped hit), the `brsid` resource id appeared 96 times. Verified after
  scrubbing: no token leftovers, all 41 embedded JSON blobs still parse,
  12 media nodes intact.
- Initial test expectations had 2 bugs (red phase after implementation):
  the content-HTML test compared against the raw image URL although `&` is
  correctly escaped to `&amp;` in attributes; the DOM-fallback test anchor
  had text, so the "Post <code>" fallback path was never reached. Fixed the
  tests, not the implementation.
- `main()` must skip the jina fallback when `INSTAGRAM_PROFILE_HTML` is set,
  otherwise the offline test would make a live network request.
- Side fix: AGENTS.md and README referenced `venv/bin/*` but the venv is
  `.venv/`; AGENTS.md also pointed at a non-existent `build_feed.py`.

## Verification

- `.venv/bin/pytest`: 95 passed (74 baseline + 21 new).
- Offline end-to-end: `INSTAGRAM_PROFILE_HTML=… build_instagram_feed.py
  tiny_ruins` → `feeds/instagram-tiny_ruins.xml`, 12 items, newest
  "TOTD 67 - Museum" (Wed, 23 Sep 2026), enclosure `image/jpeg`.

## Status

done
