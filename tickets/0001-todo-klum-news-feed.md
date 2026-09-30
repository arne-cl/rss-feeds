# 0001: RSS feed for Günther Klum's news page

Add a second feed for https://klum.com/news as `feeds/klum-news.xml`.

## Approach

- User decision: separate script per feed with a shared `scripts/common.py`
  (fetch, merge, feed assembly). `build_feed.py` is renamed to
  `build_quora_feed.py`.
- User decision: item links use the best available stable URL — the
  "MEHR INFORMATIONEN" button href (YouTube, internal pages) when stable;
  otherwise a synthetic anchor `https://www.klum.com/news#<YYYYMMDD>-<slug>`.
  The synthetic anchor is always the item id (stable merge key).
- TDD with pytest; tests run against a saved page copy
  (`KLUM_NEWS_HTML=<file>` env var, like `QUORA_PROFILE_HTML`).

## Page findings (saved copy of https://klum.com/news)

- Static Duda/1&1 website-builder page, German, ~46 news items fully in the
  HTML; no client-side rendering, no embedded JSON data blobs.
- Item = date (`DD.MM.YYYY` in a heading) + title (heading spans) + optional
  "MEHR INFORMATIONEN" button.
- **Every item appears twice**: mobile row (`hide-for-large hide-for-medium`)
  and desktop row (`hide-for-small`) → must dedupe, prefer desktop.
- Buttons link to: `youtu.be` / `www.yout-ube.com` (deliberately mangled
  domains, even a mangled video id), `youtube-nocookie.com/embed/...`,
  internal relative paths (`/oktoberfest-2026`, `/empty-page...`), one
  **signed, expiring CDN mp4** (`Expires=`/`Signature=`), one item with no
  button at all.
- Some mobile/desktop copies carry different dates
  (20.12.2025 vs 20.12.2024; 06.12.2024 vs 06.12.2025).
- Two items share the date 26.03.2025 → synthetic ids need a slug suffix.

## Hurdles

- `.gitignore` only ignores `.venv/` while AGENTS.md mandates `venv/bin/`
  → add `venv/` to `.gitignore`.
- AGENTS.md requires a `./tickets` dir that did not exist yet → created here.
- Expiring signed CDN mp4 URLs must never become feed links → synthetic
  anchor fallback.
- Repo had no tests at all; pytest is not in requirements.txt → dev-only
  install of pytest in the venv.

## Status

- [ ] ticket draft committed
- [ ] venv + pytest baseline
- [ ] fixture saved
- [ ] common.py extracted (Quora behavior unchanged)
- [ ] klum parser + feed
- [ ] CI + README
