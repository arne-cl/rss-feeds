# 0002: Klum feed — fix duplicates, canonical links, embed blog content

User report on `feeds/klum-news.xml`:

1. The feed contains many duplicate entries.
2. The "Elektrosmog" entry links to
   `https://www.klum.com/empty-pagee3f564cc` instead of
   `https://www.klum.com/wupsi-offiziele-anfrage-handy`.
3. Blog-post links (internal klum.com pages, not YouTube) should have their
   content embedded in the feed entry.

## Diagnosis

- **Duplicates**: `load_previous()` keyed previous entries by *link*, but the
  parser gives items synthetic anchor ids — old entries (guid = link) were
  never replaced by their new anchor-id counterparts, so ~30 duplicate
  pairs/triplets accumulated on every run.
- **Elektrosmog**: the site's desktop variant links to
  `/empty-pagee3f564cc` (Duda auto-generated alias), the mobile variant to
  the canonical `/wupsi-offiziele-anfrage-handy` (identical content,
  verified). Dedup dropped the mobile copy and kept the desktop alias link.
- **Oktoberfest 17.09.2026 pair**: same post rendered twice with different
  wording ("Oktoberfest 2026 im Gasthaus ZUM HORN" → `/empty-page2efa0a05`
  vs "Oktoberfest im Gasthaus Zum Horn in Bergisch Gladbach" →
  `/oktoberfest-2026`); the first-4-words heuristic didn't catch it.
- **Embedding**: internal pages are static Duda pages whose article text
  lives in `div.dmNewParagraph` — extractable. YouTube items stay links.

## Decisions (user)

- Merge same-day Oktoberfest wording variants into one entry.
- Embedded content as simple HTML (`content:encoded`); description stays
  the title.
- `.pdfx` links stay link-only (no PDF text extraction).

## Implementation

1. **Merge dedup** (`scripts/common.py`): `load_previous` keys by guid
   (falls back to link); `merge_items` drops previous entries duplicating a
   new item by (link, date) or (normalized title, date), new wins; content
   is carried over across id schemes.
2. **Canonical links** (`scripts/build_klum_feed.py`): when a mobile copy
   is deduped away, its link replaces a kept `/empty-page*` alias link.
   Plus: same date + word-set Jaccard >= 0.5 → responsive copies (keep
   desktop). `prune_superseded` drops previously stored entries the current
   parse merged away (e.g. the old mobile alias anchor).
3. **Embed content**: `is_embeddable_page` (internal HTML, not `/news`,
   not `.pdfx`) → fetch → `extract_page_content` (`dmNewParagraph` p/h
   blocks → escaped `<p>` HTML) → `content:encoded` via feedgen
   (`fe.content(..., type="html")`). Content is cached *in the feed*
   (`load_previous` reads `content:encoded`), so each page is fetched
   exactly once; `KLUM_PAGES_DIR` gives fully offline runs.

## Hurdles

- A naive shared-3-word-phrase heuristic for the Oktoberfest pair wrongly
  merged two *distinct* posts from 19.10.2023 that both contain "In München
  tut" → used word-set Jaccard >= 0.5 instead (Oktoberfest pair: 0.67,
  2023 pair: 0.23).
- feedgen 1.0.0 emits `content:encoded` XML-escaped (`&lt;p&gt;…`) — that
  is correct serialization (readers unescape), but a naive `in` string
  test on the serialized XML fails; tests parse the XML instead.
- After the merge fix the feed still held one stale entry (the old mobile
  alias anchor `news#20260917-oktoberfest-2026-im-gasthaus-zum-horn`):
  its id vanished from the fresh parse, so id-merge never saw it. Added
  `prune_superseded` (reuses the copy heuristics against previous entries).
- `merge_items` date/content carry-over by id alone misses migrated ids;
  content now also carries by link target (safe — it belongs to the page).

## Result

- 100 → 68 items; only genuine re-posts (same title, other date) remain.
- Elektrosmog links to `https://www.klum.com/wupsi-offiziele-anfrage-handy`
  with the full letter embedded as `content:encoded`.
- 14 internal article pages embedded; second run re-fetches nothing
  (feed-internal cache).

## Status

- [x] ticket draft committed
- [x] phase 1: merge dedup
- [x] phase 2: canonical links + variant dedup (+ prune_superseded)
- [x] phase 3: content embedding
- [x] feed regenerated, README updated, ticket done
