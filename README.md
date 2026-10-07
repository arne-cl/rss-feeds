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
`Persistent=true` will catch missed runs on the next boot). Install with:

```sh
mkdir -p ~/.config/systemd/user ~/.config/rss-feeds
cp systemd/rss-feeds-update.* ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now rss-feeds-update.timer
loginctl enable-linger "$USER"
```

Optional secrets go into `~/.config/rss-feeds/env` (not committed):
`JINA_API_KEY` avoids r.jina.ai rate limits; `INSTAGRAM_SESSIONID` lets the
Instagram builders prefer the session API, which provides exact dates and
every slide of carousel posts (fallback: anonymous scrape).

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

## Previewing feeds in Firefox

Every feed carries an `xml-stylesheet` PI pointing at `feeds/feed-preview.xsl`,
so opening a `feeds/*.xml` file locally in Firefox renders a readable page —
including every carousel slide and `<video>` tag (via a few lines of inline
JS). Without JS you get the cover image and plain text. Feed readers ignore
the PI, and raw.githubusercontent.com serves the XML as `text/plain`, so
subscribers are unaffected. Note that Instagram CDN links expire after ~2
weeks; older slides may then show alt text only.
