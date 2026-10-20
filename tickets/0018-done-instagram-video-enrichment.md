# 0018: Instagram video posts stay poster-only (enrichment loses `<video>`)

## Problem

`https://www.instagram.com/p/DeoRWklOA79/` (moritz.huertgen) is a video
post but the feed only shows its still poster image. The same happens on
other video entries (e.g. the "Video by titanic" items).

Live diagnosis (2026-10-20):

- `scripts/check_instagram_session.py moritz.huertgen` → `429`
  after the 10s/30s backoff. So the profile item came from the weaker
  direct/jina parse, which only knows the poster image
  (`XIGPolarisVideoMedia` carries no video URL, ticket 0011).
- A direct permalink fetch **with the session cookie** succeeds (~892 KB)
  and `parse_permalink` yields the full item: 1 poster `<img>`, 1
  `<video controls>` tag, enclosure `video/mp4`, exact `taken_at`
  `2026-10-18 08:40:12+00:00`.

Root cause: both upgrade checks count only `<img>` tags.
`enrich_with_slides` (`build_instagram_feed.py:429`) replaces content only
when `_content_images(rich) > _content_images(item)`. A video post has
exactly one `<img>` in both versions, so the richer permalink content
(poster + video) is discarded. `restore_richer_content` uses the same
count, so a later weaker reparse would also drop a previously stored
video. Secondary effect: `published` is adopted only when missing, so the
date-only midnight timestamp from the direct parse beats the permalink's
exact `taken_at` (all current Instagram items show `00:00:00`).

## Approach

- Introduce a media score that counts `<img>` **and** `<video>` tags.
- Use it in `enrich_with_slides` and `restore_richer_content` so
  richer media wins even when the image count is equal.
- Upgrade a missing or date-only (`00:00:00 UTC`) `published` to the
  permalink's exact timestamp; keep exact dates across weaker reparses.
- No change to fetch caps, spacing, or the 429 behaviour.

## Testability (red/green)

- Synthetic permalink fixture with a video slide (existing
  `permalink_html` helper extended; no network, no real scraped data).
- Enrichment: poster-only + equal image count + video → adds `<video>`
  and `video/mp4` enclosure.
- Enrichment: date-only `published` upgrades to exact `taken_at`.
- Restore: stored poster+video content and exact date survive a
  poster-only reparse.
- Baseline before changes: 257 passed.

## Hurdles

- The session API stayed `429` during the real rebuild, so the fix was
  exercised on the direct-parse → permalink path (the actual failure mode).
- Only **fresh** items are permalink-enriched (cap 12). Two older
  "Video by titanic" entries (`DecKWD1FdcC`, `DeKHAtYAKgs`) no longer
  appear on the profile page, so they stay poster-only. Their permalinks
  do return videos, but repairing all historical items would need a
  separate bounded backfill (out of scope, ban risk).
- Date upgrade also fixed the day-precision `00:00:00` timestamps of all
  freshly enriched moritz items; old non-fresh items keep their stored
  dates.

## Verification

- Baseline 257 passed → final `pytest`: **260 passed**.
- Live permalink check before the fix: `parse_permalink` returned
  `video/mp4`, 1 `<img>`, 1 `<video>`, `2026-10-18 08:40:12+00:00`.
- Real rebuild: `.venv/bin/python scripts/build_instagram_feed.py
  moritz.huertgen` (75s, 17 items). `DeoRWklOA79` now has a
  `<video controls>` tag, enclosure `type="video/mp4"`, and
  `pubDate Sun, 18 Oct 2026 08:40:12 +0000`.

## Status

done
