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

- The old CI warning items were merged into the feeds as items; the first
  successful local build dropped them again automatically (designed
  `#build-status` replacement).
- `kultur_bei_racha_roger` serves a profile shell without embedded media
  even from a residential IP (same as ticket 0007) — stays a soft-failure
  warning feed until an `INSTAGRAM_SESSIONID` is configured in
  `~/.config/rss-feeds/env`.
- First characterisation tests (`session_retry_failure_falls_through_to_jina`,
  `no_cookie_skips_session_retry`) pass before the implementation too — they
  pin behaviour that must survive the retry wiring, not new behaviour.

## Verification

- `.venv/bin/pytest`: 163 passed (157 baseline + 6 new session-cookie tests,
  red→green).
- Live run of `scripts/update_local.sh`: Quora, Klum, BRF + 4/5 Instagram
  feeds rebuilt clean (stale CI warning items removed), committed and pushed
  (`ef3ec01..d401428`).
- Timer not yet installed on this machine — follow README install steps
  (`systemctl --user enable --now rss-feeds-update.timer` + linger).

## Status

done
