#!/usr/bin/env bash
# Rebuild all feeds on this machine and push the results.
#
# Intended to run under the systemd user timer (systemd/rss-feeds-update.*);
# can also be run manually. Secrets come from the environment — under
# systemd via EnvironmentFile (usually ~/.config/rss-feeds/env):
#
#   JINA_API_KEY=...        optional, avoids r.jina.ai rate limits
#   INSTAGRAM_SESSIONID=... optional, login-wall fallback for Instagram
#                           (kept fresh by scripts/instagram_login.py refresh)
set -euo pipefail

cd "$(dirname "$0")/.."

git pull --rebase --autostash origin main

PY=.venv/bin/python
"$PY" scripts/build_quora_feed.py
"$PY" scripts/build_klum_feed.py
"$PY" scripts/build_brf_chansons_feed.py
# Touch the persistent Instagram browser profile so the sessionid keeps
# rolling; rewrites the env file only when a verified-new cookie shows up.
# Never fatal — a dead session just means the builds fall back to the
# weaker parses (see scripts/instagram_login.py).
"$PY" scripts/instagram_login.py refresh || echo "warning: session refresh failed, continuing"

# Short gap by default; the runner waits 45s/90s/180s only after a
# permalink fetch actually reports a 429.
IG_ACCOUNTS=(
    tiny_ruins martinmaleschka tumvlt jamborjoanna daxwerner thebeths
    susibumms waveybobson moritz.huertgen reinder_wijnveld
    ostmoderne_philokartie sveamaus betelsfoodfeast
)
"$PY" scripts/instagram_stagger.py "${IG_ACCOUNTS[@]}"
"$PY" scripts/build_instagram_stories_feed.py "${IG_ACCOUNTS[@]}"

if [[ -n "$(git status --porcelain feeds)" ]]; then
    git add feeds
    git commit -m "Update feeds"
    git push origin main
else
    echo "No changes"
fi
