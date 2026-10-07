# 0009: Move feed builds fully local, drop CI

## Problem

GitHub Actions runners (Azure IPs) are now blocked by Instagram (login wall)
and Quora (403 direct, Cloudflare challenge via r.jina.ai) — see the weekly
`::warning::` spam. Probing from a residential IP shows all sources work
untouched, so the parsers are fine; only the CI fetch location is broken.

Decision (with repo owner): run everything locally, delete CI, keep the repo
public (raw.githubusercontent feed URLs stay valid). Flexible scheduling
instead of cron (machine is used irregularly) via a systemd user timer.

## Approach

- Delete `.github/` (only contains `update.yml`).
- `scripts/update_local.sh`: pull --rebase, build all feeds (quora, klum,
  brf, 5 instagram accounts), commit `feeds/` + push. Secrets via env
  (`JINA_API_KEY`, `INSTAGRAM_SESSIONID`), never committed.
- `systemd/rss-feeds-update.{service,timer}` user units (committed):
  oneshot service + timer with `OnBootSec=5min`, `OnUnitInactiveSec=1d`,
  `Persistent=true` (missed runs fire on next boot; no overlap by design).
  `EnvironmentFile=-%h/.config/rss-feeds/env` for secrets.
- `build_instagram_feed.py`: optional `INSTAGRAM_SESSIONID` fallback —
  if the anonymous direct fetch yields 0 media nodes, retry once with the
  session cookie before the jina fallback (Instagram's anonymous-fetch
  variance, cf. ticket 0007 hurdles).
- README: replace CI description with local setup instructions.

## Hurdles

- TBD

## Status

todo
