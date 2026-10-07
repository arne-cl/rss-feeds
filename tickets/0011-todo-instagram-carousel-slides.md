# 0011: Instagram carousel posts — embed all slides

## Problem

Posts with multiple "slides" (carousels, `media_type: 8`, e.g.
<https://www.instagram.com/p/Ddbjry0jnuO/>) are rendered with the cover
image only. Both parsers extract exactly one media URL
(`display_uri` / `_api_media_url`). Related bug: standalone video posts
embed `<img src="….mp4">` in `content:encoded`, which renders as nothing
in feed readers.

The direct-fetch strategy can't help: the profile-page JSON carries only
`carousel_media_count`, no child media (verified on the tiny-ruins
fixture). The session API data does carry every slide — but the current
`main()` only calls it as a *fallback* when the direct parse yields zero
items, so richer API data is normally never fetched.

## Approach (decisions)

- **Prefer the session API when `INSTAGRAM_SESSIONID` is set** (and not
  offline): fetch it first, use its items when non-empty. Existing chain
  (no session / API empty or fails → direct HTML → jina DOM) unchanged.
  Costs ~1 authenticated call per account per build (12/day on the daily
  timer); ticket 0010's 429 warning applies — degradation is soft.
- **Slide embedding** in `_api_item`: children from `carousel_media[]`
  (xdt shape) *and* `edge_sidecar_to_children.edges[].node`
  (web_profile_info shape). Content = one `<img>` per slide,
  `accessibility_caption` as `alt` when present. RSS allows one
  enclosure → first slide (video → `video/mp4`).
- **Video content fix**: poster `<img>` first, then
  `<video controls preload="none" src="…">` below — for video slides and
  standalone video posts.
- **Richer-content restore across builds**: a fresh parse with fewer
  `<img>` tags than the stored entry for the same id (e.g. sessionid
  expired → cover-only direct parse) must not overwrite the stored
  multi-slide content/enclosure.
- No permalink fetching (rejected: extra requests, ban risk).

## Hurdles

(tbd during implementation)

## Status

todo
