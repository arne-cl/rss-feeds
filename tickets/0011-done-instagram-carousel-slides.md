# 0011: Instagram carousel posts — embed all slides

## Problem

Posts with multiple "slides" (carousels, `media_type: 8`, e.g.
<https://www.instagram.com/p/Ddbjry0jnuO/> — tracked as `daxwerner`) were
rendered with the cover image only. Both parsers extracted exactly one
media URL (`display_uri` / `_api_media_url`). Related bug: standalone
video posts embedded `<img src="….mp4">` in `content:encoded`, which
renders as nothing in feed readers.

The direct-fetch strategy can't help: the profile-page JSON carries only
`carousel_media_count`, no child media (verified on the tiny-ruins
fixture). The session API data carries every slide — but the old `main()`
only called it as a *fallback* when the direct parse yielded zero items,
so richer API data was normally never fetched.

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
- **Richer-content restore across builds**: `restore_richer_content()`
  keeps the stored content/enclosure when a fresh parse for the same id
  has fewer `<img>` tags (e.g. sessionid expired → cover-only direct
  parse); `merge_items` would otherwise let the weaker reparse win.
- No permalink fetching (rejected: extra requests, ban risk).

## Hurdles

- Direct-shape video nodes (`XIGPolarisVideoMedia` on the profile page)
  carry no video URL at all — only the poster `display_uri`. So the
  poster-only `<img>` is the best the direct path can do; `<video>` tags
  require API data.
- First synthetic carousel test assumed a parent cover distinct from
  slide 1; real data always has cover == first slide, so the enclosure
  rule became "first slide, parent media as fallback" in both parsers.
- feedgen HTML-escapes `content:encoded`, so XML-level tests must count
  `&lt;img ` occurrences, not `<img`.
- API items now also flow through `profile_metadata(page)` unchanged —
  metadata still comes from the (possibly login-walled) direct HTML page,
  falling back to the previous feed's channel title/description.
- Sanity-checked offline: a real production entry (`Ddbjry0jnuO` in
  `instagram-daxwerner.xml`) will gain its slides on the next scheduled
  build, since fresh (richer) content wins the merge.

## Verification

- `.venv/bin/pytest`: 190 passed (14 new: 8 slide/video-tag tests on the
  real timeline fixture + synthetic sidecar/xdt/direct shapes, 2 strategy
  guards, 4 richer-content-restore tests incl. an end-to-end
  rich→weak-reparse run through `main()`).
- Red/green followed per phase; offline builds with the saved page copy
  still produce 12 items.
- README + module docstring updated to the new strategy order.

## Status

done
