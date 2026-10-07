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

- The `__a=1&__d=dis` "200" detour: that response is a media-free shell
  page (416 KB, zero media keys) — recorded here so nobody retries it.
- First permalink blob-walk searched for `edge_sidecar_to_children` /
  `__isXIGPolarisMedia` (web_profile_info shapes) and found nothing —
  permalink pages embed the *app-API* node shape (`carousel_media`,
  `image_versions2`, `caption.text`, `taken_at`), which `_api_item`
  already handles.
- Enrichment made four pre-existing session-flow tests hit the network
  (real permalink fetches, 86s suite) — they now stub
  `enrich_with_slides` (or `time.sleep` where the fake fetch path is
  the point); suite back to 8s, offline.
- Real daxwerner rebuild: 12 items, four carousel entries regained
  slides (3/3/10/2 imgs), exact `taken_at` dates (e.g. Ddbjry0jnuO →
  Fri, 18 Sep 2026). Verified rendered in headless Chromium + Firefox
  via the preview server (screenshots `/tmp/opencode/dax-slides-*`).
- Full staggered rebuild of all 12 accounts (45s apart, ~19 min):
  **719 slides total** (was 131 cover-only images), carousels e.g.
  martinmaleschka 11 items ≤20 slides, tumvlt 9, waveybobson 8,
  ostmoderne 12. Only `kultur_bei_racha_roger` still broken
  (pre-existing jina 403, zero previous items — separate issue).
- Acceptance evidence: `/tmp/opencode/dax-carousel-final-ff.png`
  (Firefox: full "Heute mit mehreren Slides" entry with all 3 slides,
  exact date, caption, permalink) and
  `/tmp/opencode/dax-slides-chromium.png` (Chromium, full page,
  10-slide entry rendering incl. `<video>` players). Both verified
  before showing the user. Live: `http://127.0.0.1:8399/…` while the
  preview server runs.

## Status

done
