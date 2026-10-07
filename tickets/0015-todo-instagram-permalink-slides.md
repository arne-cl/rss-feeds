# 0015: Carousel slides via post permalink enrichment

## Problem

Slides never materialized (ticket 0013 investigated): Instagram has
neutered every previous data path:

- `web_profile_info` API without `&__a=1&__d=dis` + XHR headers: fake
  `429` + HTML "Page Not Found" (logged-in) — looks like throttling but
  isn't; with those params it returns a 200 HTML *shell page without
  any media JSON* (verified on daxwerner, 416 KB, zero media keys).
- Profile page (anonymous *and* logged-in): no embedded media JSON at
  all anymore (`__isXIGPolarisMedia` count 0) — the fixture-era
  `parse_direct` path is dead for fresh data; today's covers come from
  the jina DOM fallback.
- The fresh `INSTAGRAM_SESSIONID` (user rotated it) is **valid**:
  garbage/absent cookie → 401, real cookie → 200/429 variants.

What still works: **post permalink pages fetched with the session
cookie** embed the full app-API media node —
`xdt_api__v1__media__shortcode__web_info.items[]` with `carousel_media`
children, `image_versions2`, `taken_at`, `caption` — inside
`<script type="application/json" data-sjs>` blobs. `_api_item` parses
that shape as-is (verified offline on the real daxwerner carousel
`Ddbjry0jnuO`: 3 slides, exact timestamp).

## Decision change

Ticket 0011 rejected permalink fetching ("extra requests, ban risk")
while the session API delivered slides. With the API path neutered,
permalinks are the only remaining slide source. Mitigations: fetch only
for fresh items of a build (cap 12), 2s spacing, session cookie only,
soft failure per post (item keeps its cover-only content).

## Approach

- `parse_permalink(html)`: walk `application/json` blobs, extract
  `xdt_api__v1__media__shortcode__web_info.items[]` → `_api_item`.
- `enrich_with_slides(items, fetch_html, max_fetches=12, delay=2)`:
  for each fresh item, fetch `instagram.com/p/<code>/` with the session
  cookie, parse, and adopt content/enclosure when strictly richer (more
  `<img>`); adopt `published`/`title` only when missing. Single posts
  upgrade too (jina items carry no content at all). Failures and empty
  parses keep the item unchanged; fetches are capped and spaced.
- Wired into `main()` after the parse chain, before
  `restore_richer_content`/merge; skipped in offline mode.
- Module docstring strategy list updated.

## Testability (red/green)

- Synthetic permalink fixture (ScheduledServerJS blob, app-API node
  with 3-slide `carousel_media`) — no real scraped data committed
  (ticket 0004 practice).
- `parse_permalink`: slides/date/id; garbage and empty → `[]`.
- `enrich_with_slides`: richer-wins, upgrade of content-less jina
  items, fetch failure tolerated, fetch cap, inter-fetch spacing.
- `main()` wiring: enrichment applied with session, skipped offline;
  end-to-end jina→permalink feed write.

## Hurdles

- (to be filled during implementation)

## Status

todo
