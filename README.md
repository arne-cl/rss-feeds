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

Builds run on a home machine (GitHub's runner IPs are blocked by Instagram
and Quora), driven by a systemd user timer: it fires 5 minutes after boot and
then at most once per day (`Persistent=true`, so a missed run happens on the
next boot). Install with:

```sh
mkdir -p ~/.config/systemd/user ~/.config/rss-feeds
cp systemd/rss-feeds-update.* ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now rss-feeds-update.timer
loginctl enable-linger "$USER"
```

Optional secrets go into `~/.config/rss-feeds/env` (not committed):
`JINA_API_KEY` avoids r.jina.ai rate limits; `INSTAGRAM_SESSIONID` is used as
a login-wall fallback for the Instagram builders.

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
