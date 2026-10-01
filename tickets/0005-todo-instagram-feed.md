# 0005: Instagram feed for tiny_ruins, configurable per account

## Problem

No RSS feed exists for http://instagram.com/tiny_ruins (Instagram provides
none). The builder must be reusable for other Instagram accounts.

## Approach

1. Probe the anonymous profile page: verified that a direct fetch with
   Chrome TLS impersonation returns HTTP 200 with embedded
   `<script type="application/json">` blobs containing
   `polaris_ordered_timeline_connection.edges[].node` media objects
   (12 posts for tiny_ruins).
2. New script `scripts/build_instagram_feed.py <account>`:
   - Strategy 1: parse media nodes out of all embedded JSON blobs
     (walk generically, no hardcoded JSON path). Fields: `code` → post URL,
     `caption.text` → title/description, `display_uri` → image enclosure,
     date parsed from `accessibility_caption` ("… on September 23, 2026.").
   - Strategy 2 (fallback): r.jina.ai rendered DOM, parse `/p/<code>/` links
     like the other builders.
   - Reuse `scripts/common.py` (fetch_page / merge_items / write_feed),
     `MAX_ITEMS=100`, output `feeds/instagram-<account>.xml`.
   - Offline mode via `INSTAGRAM_PROFILE_HTML=<file>` (same pattern as Quora).
3. Fixture `tests/fixtures/instagram-tiny-ruins.html`, scrub session/device
   tokens (ticket 0004 precedent). Tests in `tests/test_build_instagram_feed.py`,
   strict red/green.
4. CI: build `tiny_ruins` feed in update.yml, last position, non-fatal
   (`|| echo ::warning::…`) so Instagram flakiness can't block the other feeds.
5. README: feeds table row + local-dev hint.

## Known hurdles

- Anonymous payload has no `taken_at` timestamp; only
  `accessibility_caption` carries a date string. Missing date → `None`
  (merge keeps previously stored dates).
- Instagram is the flakiest source of the three; CI handles it as
  non-fatal for that reason.

## Status

todo
