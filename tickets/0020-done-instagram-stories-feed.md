# 0020: Instagram stories feed (24h posts)

## Problem

The user's "reels" request actually meant **stories** — the 24h
disappearing posts. None of the current feeds carry them: stories never
appear in the profile timeline or permalink pipeline.

Live feasibility check (2026-10-22, ~23:00 CEST):

- The story REST endpoints are gated: `/api/v1/feed/user/<pk>/story/`
  returns an HTML shell, `POST /api/v1/feed/reels_media/` needs a CSRF
  pair (403 without, "Invalid reel id list" with a synthetic token).
- Same pattern as ticket 0015 works instead: `GET
  https://www.instagram.com/stories/<acc>/` **with the session cookie**
  embeds a Relay preloader blob:
  `result.data.xdt_api__v1__feed__reels_media.reels_media.items[]` —
  story media nodes with `image_versions2`, `video_versions`,
  `taken_at`, `expiring_at`.
- Selector gotcha: `reels_media.items` exists only when the account has
  an active story; the empty shape nests differently (`reels: {}`), so
  key-walking gives false negatives. Reliable node filter: dict with
  `video_versions`/`image_versions2.candidates` **and** `expiring_at`
  (feed posts have no `expiring_at`).
- Story census right now: martinmaleschka 8, daxwerner 5, susibumms 3,
  waveybobson 3, reinder_wijnveld 3, tiny_ruins 1, moritz.huertgen 1,
  ostmoderne_philokartie 1, betelsfoodfeast 1; tumvlt, jamborjoanna,
  thebeths, sveamaus none. Photos and videos both present.

## Approach (user decisions: separate feed, keep until cap)

- New `scripts/build_instagram_stories_feed.py`: for each followed
  account fetch the stories page with `INSTAGRAM_SESSIONID`, parse story
  items, render like posts (poster `<img>` + `<video controls>`,
  enclosure video/mp4 / image/jpeg) with the account name and expiry in
  the content.
- One combined feed `feeds/instagram-stories.xml`, title "Instagram
  Stories", items from all accounts merged by id via the existing
  `common` helpers; previous items are kept until the 100-item cap
  pushes them out (readers that poll after expiry still see them).
- Accounts fetched sequentially with 2s spacing; per-account soft
  failures skip that account. If *every* account fails, write the
  rolling warning item (tickets 0007/0008 pattern).
- Offline mode via `INSTAGRAM_STORIES_HTML=<file>` (no network) for
  parser rebuilds, mirroring `INSTAGRAM_PROFILE_HTML`.
- Wire into `update_local.sh` after the post-feed stagger.
- No change to the post feeds' fetch caps or the 429 behaviour.

## Testability (red/green)

- Synthetic stories-page fixture (same blob shape as the real Relay
  preloader; no scraped data): video + photo story, decoy feed-post
  node without `expiring_at`, duplicate id.
- Parse: items extracted with correct enclosure types, `<video>` tags,
  `published` from `taken_at`, expiry line in content; decoys and
  duplicates ignored.
- Merge/keep: previous items survive a build where the account has no
  active story; cap at 100 keeps the newest.
- `main()`: offline mode makes no network calls; missing sessionid →
  warning feed; one account failing doesn't drop the others.
- Baseline before changes: 272 passed.

## Hurdles

- The story REST endpoints were dead ends (HTML shell on the GET story
  endpoint; `reels_media` POST needs a CSRF pair and rejects raw user
  pks with "Invalid reel id list"). The page-JSON path won; the first
  selector (`reels_media.reels`) was a false negative — the populated
  shape nests as `reels_media.items`, so the filter is now
  "media node + expiring_at".
- Pre-fix pytest leaked writes into the real `feeds/` dir because
  `OUTPUT_PATH` was computed at import time (patching `FEEDS_DIR` had
  no effect) — junk items landed in the first live feed; deleted and
  rebuilt. The post builder avoids this via an `output_path()` function;
  the stories builder now does the same.
- `merge_items`' supersede filter drops previous entries matching
  (link, date) **or** (title, date). Stories of one account share the
  tray link and can share a minute-stamp (martinmaleschka posted
  several stories in the same minute), so items carry unique deep links
  (`stories/<acc>/<pk>/`) and same-batch title collisions get a
  " (2)" suffix — verified with a regression test and two real builds.
- Live check of who has stories was done twice (~23:00 CEST) with the
  broken selector first (all zeros) and correctly after; census in the
  Problem section is from the correct run.

## Verification

- Baseline 272 passed → final `.venv/bin/pytest`: **287 passed**
  (15 new: 7 parse, 6 main/soft-failure, cap/supersede regressions).
- Live rebuild ×2: 26 story items from 9 accounts (15 video + 11
  photo), stable merge (26 → 26), no duplicate titles/links.
- `update_local.sh` now runs the stories builder after the post-feed
  stagger (single `IG_ACCOUNTS` list for both).

## Status

done
