# rss-feeds

Vibe-coded RSS feeds generated from pages that don't provide one.

## Feeds

| Feed | URL |
|------|-----|
| Alan Kay on Quora | `https://raw.githubusercontent.com/arne-cl/rss-feeds/main/feeds/alankay-quora.xml` |
| Günther Klum News | `https://raw.githubusercontent.com/arne-cl/rss-feeds/main/feeds/klum-news.xml` |
| Tiny Ruins on Instagram | `https://raw.githubusercontent.com/arne-cl/rss-feeds/main/feeds/instagram-tiny_ruins.xml` |
| Chansons, Lieder und Folk (BRF1) | `https://raw.githubusercontent.com/arne-cl/rss-feeds/main/feeds/brf1-chansons.xml` |

Subscribe with the raw URL above.

## How it works

Shared fetch/merge/RSS-assembly logic lives in `scripts/common.py`; each feed
has its own builder script with the site-specific parsing.

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
.venv/bin/python scripts/build_brf_chansons_feed.py
.venv/bin/python scripts/build_instagram_feed.py tiny_ruins
```

Set `QUORA_PROFILE_HTML=<file>` or `KLUM_NEWS_HTML=<file>` to run against a
saved page copy instead of fetching the site. For the Klum builder,
`KLUM_PAGES_DIR=<dir>` enables offline mode for the article pages too
(saved copies named `<slug>.html`; no requests at all). For the Instagram
builder, pass the account as the only argument (e.g. `tiny_ruins` above) and
set `INSTAGRAM_PROFILE_HTML=<file>` to run offline. For the BRF builder,
`CHANSONS_HTML=<file>` replaces the archive page, `CHANSONS_PAGES_DIR=<dir>`
(saved copies named `<episode-id>.html`) and `CHANSONS_PLAY_DIR=<dir>`
(named `<play-hash>.html`) enable offline mode for episodes and audio
resolution. The saved copies
used by the tests live in `tests/fixtures/` (`.venv/bin/pytest`).
