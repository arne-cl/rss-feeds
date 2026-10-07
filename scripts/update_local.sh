#!/usr/bin/env bash
# Rebuild all feeds on this machine and push the results.
#
# Intended to run under the systemd user timer (systemd/rss-feeds-update.*);
# can also be run manually. Secrets come from the environment — under
# systemd via EnvironmentFile (usually ~/.config/rss-feeds/env):
#
#   JINA_API_KEY=...        optional, avoids r.jina.ai rate limits
#   INSTAGRAM_SESSIONID=... optional, login-wall fallback for Instagram
set -euo pipefail

cd "$(dirname "$0")/.."

git pull --rebase --autostash origin main

PY=.venv/bin/python
"$PY" scripts/build_quora_feed.py
"$PY" scripts/build_klum_feed.py
"$PY" scripts/build_brf_chansons_feed.py
for account in tiny_ruins kultur_bei_racha_roger martinmaleschka tumvlt jamborjoanna; do
    "$PY" scripts/build_instagram_feed.py "$account"
done

if [[ -n "$(git status --porcelain feeds)" ]]; then
    git add feeds
    git commit -m "Update feeds"
    git push origin main
else
    echo "No changes"
fi
