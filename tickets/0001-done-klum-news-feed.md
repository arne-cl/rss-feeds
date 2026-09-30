# 0001: RSS feed for Günther Klum's news page

Add a second feed for https://klum.com/news as `feeds/klum-news.xml`.

## Approach

- User decision: separate script per feed with a shared `scripts/common.py`
  (fetch, merge, feed assembly). `build_feed.py` was renamed to
  `build_quora_feed.py`.
- User decision: item links use the best available stable URL — the
  "MEHR INFORMATIONEN" button href (YouTube, internal pages) when stable;
  otherwise the news page URL. Item ids are always stable synthetic anchors
  `https://www.klum.com/news#<YYYYMMDD>-<slug>` (most items have no
  permalink of their own; two items even share a date).
- TDD with pytest; tests run against a saved page copy
  (`KLUM_NEWS_HTML=<file>` env var, like `QUORA_PROFILE_HTML`).

## Page findings (saved copy: tests/fixtures/klum-news.html)

- Static Duda/1&1 website-builder page, German, news items fully in the
  HTML; no client-side rendering, no embedded JSON data blobs.
- Item = date (`DD.MM.YYYY`, sometimes split across spans, sometimes plain
  text, sometimes a whole separate paragraph) + title/body headings
  (h1–h6 with inconsistent font classes) + optional button.
- **Every item appears twice** (mobile row + desktop row), sometimes with
  different wording or dates; the desktop variant of an item can even lose
  its date entirely while the mobile one keeps it.
- Multiple distinct items share one column/row; body text lives in extra
  headings → items are split at date-starting paragraphs.
- Buttons link to: real YouTube links, deliberately mangled hosts
  (`www.yout-ube.com`, `you-tube.com`) and even a mangled 24-char video id
  (kept verbatim — host-normalized only), internal relative paths, one
  **signed, expiring CDN mp4** (rejected → page URL), items without button.
- The page contains a desktop-vs-desktop near-duplicate ("Nikolaus vor 45/46
  Jahren") and shows one post under two dates (14.10./30.08.2024).

## Hurdles

- `.gitignore` only ignored `.venv/` while AGENTS.md mandates `venv/bin/`
  → added `venv/`.
- The `./tickets` dir required by AGENTS.md did not exist → created here.
- **Latent bug found by tests**: `load_previous` searched for a lowercase
  `<pubdate>` tag, but BS4's `xml` parser preserves `<pubDate>` — dates from
  the previous feed were silently never loaded. Fixed.
- **feedgen 1.0.0 reverses entry order**: `add_entry` defaults to
  `order='prepend'`. Both feeds had silently been oldest-first; now
  `order='append'` is used and both feeds are newest-first
  (`feeds/alankay-quora.xml` re-ordered in the process).
- Dedupe heuristics needed three rules to handle the responsive copies
  without killing genuine re-posts with identical titles ("Ist die Schweiz
  ein Vorbild für uns?" 19.12.2025 + 01.08.2025): compare only within the
  same `day.month`, via squashed-title equality, first-4-words prefix, or
  identical link. One unavoidable near-duplicate pair remains (the site
  shows "Meine Meinung zum Kommentar..." under 14.10.2024 and 30.08.2024).
- Mangled YouTube video IDs (24 chars) are kept verbatim — guessing at
  "corrections" seemed worse than linking what the author wrote.

## Status

- [x] ticket draft committed
- [x] venv + pytest baseline
- [x] fixture saved
- [x] common.py extracted (Quora behavior verified identical offline)
- [x] klum parser + feed (69 items from the fixture)
- [x] CI + README
