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

Each feed has its own builder script with the site-specific parsing. Shared
fetch/merge/RSS-assembly logic lives in `scripts/common.py`.

Builds run on a local machine because GitHub's runner IPs are blocked
by Instagram and Quora). They are triggered by a systemd user timer (5 minutes
after boot, then again 24h after each completed run). 
`Persistent=true` will catch missed runs on the next boot. Install with:

```sh
mkdir -p ~/.config/systemd/user ~/.config/rss-feeds
cp systemd/rss-feeds-update.* ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now rss-feeds-update.timer
loginctl enable-linger "$USER"
```

Optional secrets go into `~/.config/rss-feeds/env`.
`JINA_API_KEY` avoids r.jina.ai rate limits. `INSTAGRAM_SESSIONID` is required
for real data. Instagram no longer serves media JSON on profile pages and has
neutered the `web_profile_info` API, so the builders enrich each post from its
**permalink page** (fetched with the session cookie). This is the only
remaining source for exact dates and carousel slides. You can verify if the
session id still works by running `scripts/check_instagram_session.py` (exit 0 = works).

To run everything by hand: `scripts/update_local.sh` (pull, build, commit,
push) or the individual builder commands under "Local development" below.

## Local development

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/build_quora_feed.py
.venv/bin/python scripts/build_klum_feed.py
.venv/bin/python scripts/build_brf_chansons_feed.py
.venv/bin/python scripts/build_instagram_feed.py tiny_ruins
```

All build scripts can be tested against local HTML files (for details see the
respective module docstrings) and `tests/fixtures/`.

## Previewing feeds in a browser

Every feed links to an `xml-stylesheet` at `feeds/feed-preview.xsl`,
which renders a readable page (including carousel slides and `<video>`
tag). Feed readers simply ignore the stylesheet.

Current Firefox/Chromium refuse to apply XSLT to `file://` documents, so
serve the feeds over loopback HTTP first:

```sh
.venv/bin/python scripts/preview_feeds.py # lists all feeds
.venv/bin/python scripts/preview_feeds.py instagram-daxwerner.xml
```

This serves `feeds/` on <http://127.0.0.1:8321/> and opens the browser.
Note that Instagram CDN links expire after ~2 weeks.
