# rss-feeds

Vibe-coded RSS feeds generated from pages that don't provide one.

## Feeds

| Feed | URL |
|------|-----|
| Alan Kay on Quora | `https://raw.githubusercontent.com/arne-cl/rss-feeds/main/feeds/alankay-quora.xml` |
| Günther Klum News | `https://raw.githubusercontent.com/arne-cl/rss-feeds/main/feeds/klum-news.xml` |

Subscribe with the raw URL above.

## How it works

Shared fetch/merge/RSS-assembly logic lives in `scripts/common.py`; each feed
has its own builder script with the site-specific parsing.

### Alan Kay on Quora (`scripts/build_quora_feed.py`)

Quora blocks plain HTTP clients, so the script:

1. Fetches the profile page directly using Chrome TLS impersonation
   (`curl_cffi`) and extracts the answer objects embedded in the page's JSON
   blobs — this yields the full answer text but no dates.
2. If that fails or yields nothing, falls back to the
   [r.jina.ai](https://jina.ai/reader) reader proxy and parses the rendered
   DOM, which gives excerpts plus the answer dates shown on the profile.
3. Merges new items into `feeds/alankay-quora.xml` (deduped by permalink,
   newest first, capped at 100) so history survives between runs. Known items
   keep their previously stored dates.

### Günther Klum News (`scripts/build_klum_feed.py`)

`klum.com/news` is a static Duda/1&1 website-builder page (German). The
script parses the news rows from the HTML, keeping the desktop variant and
using the mobile variant only to fill in dates the desktop rendering lost
and to catch items missing there. News items are date + text, usually with a
"MEHR INFORMATIONEN" button linking to YouTube or internal pages; expiring
signed CDN links are rejected and the news page URL is used instead. Item
ids are stable synthetic anchors (`.../news#<YYYYMMDD>-<slug>`) because most
items have no permalink of their own. Items are merged into
`feeds/klum-news.xml` (newest first, capped at 100).

Internal article pages (not YouTube, not `.pdfx` viewers) get their text
extracted (`div.dmNewParagraph` blocks) and embedded as `content:encoded`.
The embedded HTML is cached inside the feed itself, so each page is fetched
only once. The desktop rendering sometimes points at Duda page aliases
(`/empty-page<id>`); when the mobile rendering has the canonical slug, that
URL wins. Responsive mobile/desktop variants of the same post are deduped
by date + word overlap.

The feed is refreshed weekly by
[.github/workflows/update.yml](.github/workflows/update.yml) (Mondays 06:17
UTC), which commits the updated XML if anything changed. Trigger it manually
via the Actions tab → "Update feeds" → "Run workflow".

If the jina.ai fallback gets rate-limited on GitHub's shared runner IPs, add a
free [jina.ai API key](https://jina.ai/reader) as the repository secret
`JINA_API_KEY`.

## Local development

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/build_quora_feed.py
.venv/bin/python scripts/build_klum_feed.py
```

Set `QUORA_PROFILE_HTML=<file>` or `KLUM_NEWS_HTML=<file>` to run against a
saved page copy instead of fetching the site. For the Klum builder,
`KLUM_PAGES_DIR=<dir>` enables offline mode for the article pages too
(saved copies named `<slug>.html`; no requests at all). The saved copies
used by the tests live in `tests/fixtures/` (`venv/bin/pytest`).
