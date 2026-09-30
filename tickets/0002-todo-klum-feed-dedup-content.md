# 0002: Klum feed — fix duplicates, canonical links, embed blog content

User report on `feeds/klum-news.xml`:

1. The feed contains many duplicate entries.
2. The "Elektrosmog" entry links to
   `https://www.klum.com/empty-pagee3f564cc` instead of
   `https://www.klum.com/wupsi-offiziele-anfrage-handy`.
3. Blog-post links (internal klum.com pages, not YouTube) should have their
   content embedded in the feed entry.

## Diagnosis

- **Duplicates**: `load_previous()` keys previous entries by *link*, but the
  parser gives items synthetic anchor ids — old entries (guid = link) are
  never replaced by their new anchor-id counterparts, so ~30 duplicate
  pairs/triplets accumulate on every run.
- **Elektrosmog**: the site's desktop variant links to
  `/empty-pagee3f564cc` (Duda auto-generated alias), the mobile variant to
  the canonical `/wupsi-offiziele-anfrage-handy` (identical content,
  verified). Dedup drops the mobile copy and keeps the desktop alias link.
- **Oktoberfest 17.09.2026 pair**: same post rendered twice with different
  wording ("Oktoberfest 2026 im Gasthaus ZUM HORN" → `/empty-page2efa0a05`
  vs "Oktoberfest im Gasthaus Zum Horn in Bergisch Gladbach" →
  `/oktoberfest-2026`); the first-4-words heuristic doesn't catch it.
- **Embedding**: internal pages are static Duda pages whose article text
  lives in `div.dmNewParagraph` — extractable. YouTube items stay links.

## Decisions (user)

- Merge same-day Oktoberfest wording variants into one entry.
- Embedded content as simple HTML (`content:encoded`); description stays
  the title.
- `.pdfx` links stay link-only (no PDF text extraction).

## Plan (strict red/green, small commits)

1. **Merge dedup** (`scripts/common.py`): key previous entries by guid;
   when merging, drop previous entries duplicating a new item by
   (link, date) or (squashed title, date), new wins. Regenerate feed.
2. **Canonical links** (`scripts/build_klum_feed.py`): when a mobile copy
   is deduped away, inherit its link if the kept link matches
   `empty-page*` and the mobile one doesn't. Plus: same date + shared
   >=3-word run → treat as responsive copies (keep desktop).
3. **Embed content**: for internal HTML links (not YouTube / `.pdfx` /
   `/news`), fetch page, extract `dmNewParagraph` HTML into
   `content:encoded`. Cache content *in the feed* (`load_previous` reads
   `content:encoded`) so weekly CI runs only fetch new pages. Offline
   tests via saved page copies + env var, per repo convention.

## Hurdles

- (to be filled during implementation)

## Status

- [x] ticket draft committed
- [ ] phase 1: merge dedup
- [ ] phase 2: canonical links + variant dedup
- [ ] phase 3: content embedding
- [ ] feed regenerated, README updated, ticket done
