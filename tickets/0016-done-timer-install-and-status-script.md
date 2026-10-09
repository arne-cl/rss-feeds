# 0016: Install the update timer, add a status script

## Problem

The automated daily rebuild was silently down. Ticket 0009 shipped
`systemd/rss-feeds-update.{service,timer}` but its verification section
already noted "Timer not yet installed on this machine" — that step was
never done. `~/.config/systemd/user/` was empty, `Linger=no`, no journal
entries; builds since Oct 7 were manual runs. Nothing on the machine
answers "when did this last run, how many new entries, any failed feeds?".

Also found: two ~11MB PostScript junk files (`argparse`, `os`) in the repo
root (accidental print output, Oct 7) — removed untracked, no repo change.

## Approach

### Fix: install + verify the timer

1. Per AGENTS.md verify the secret actually works first:
   `.venv/bin/python scripts/check_instagram_session.py tiny_ruins`
   (record exit code below).
2. Install per README:
   `cp systemd/rss-feeds-update.{service,timer} ~/.config/systemd/user/`,
   `systemctl --user daemon-reload`,
   `systemctl --user enable --now rss-feeds-update.timer`,
   `loginctl enable-linger "$USER"`.
3. Verify `systemctl --user list-timers` shows the unit with a next
   elapse and `Linger=yes`. Because `OnBootSec=5min` is already in the
   past after today's boot, enabling the timer fires the first run
   immediately — that run is the end-to-end proof (fetch all feeds,
   commit+push if changed). Check `journalctl --user -u
   rss-feeds-update.service` afterwards.

### Status script: `scripts/status.py`

Offline by default (no fetches): reads `feeds/*.xml`, git log and the
systemd timer state; `--check-session` adds the live Instagram session
check. One line per feed (items, build-failure warnings, feed age,
newest entry age) plus last `Update feeds` commit and timer state.

Exit codes (monitoring-friendly):

- `0` — healthy
- `1` — failures detected: "Feed build failed" warning items in any
  feed, or `--check-session` returned non-zero
- `2` — update automation not active (timer unit missing or not
  enabled); only when systemd is reachable — if systemctl itself is
  unavailable the state is "unknown" and does not affect the exit code

TDD: tests in `tests/test_status.py` first (red), then implement
(green). Reuse `common.load_previous` and `common.WARNING_ID_SUFFIX`.

## Hurdles

- **Push credentials**: the HTTPS credential cache (helper `cache`,
  10h timeout) had expired and nothing else could push non-interactively
  — no gh CLI, no other helpers; an existing `~/.config/systemd/user`
  empty setup. Decision (repo owner): **GUI askpass + credential cache**
  — `scripts/askpass_gui.sh` (zenity password dialog, 180s timeout,
  clean failure without a graphical session) wired via repo-local
  `git config core.askPass`; the owner answers the popup with their
  existing `ghp_*` token after each boot (cache is gone on reboot).
  Unattended boots while away still skip the push; a later successful
  run pushes then.
- github.com was missing from `~/.ssh/known_hosts` (added via
  ssh-keyscan); the existing ed25519 key is *not* registered on GitHub
  (`Permission denied (publickey)`) — SSH considered, rejected for now.
- Two ~11MB PostScript junk files (`argparse`, `os`) sat untracked in
  the repo root (accidental print output) — removed.
- Session check (`check_instagram_session.py tiny_ruins`) during the
  concurrent first timer run: `rate_limited` (429, web_profile_info) —
  inconclusive, the run itself was using the rate budget; re-check
  after the run.
- The timer fired immediately on `enable --now`: `OnBootSec=5min` was
  already in the past after today's boot, so systemd elapsed it at
  once — convenient: the first run doubled as the end-to-end test.
- First run: all 14 feeds built and committed (`5277d6e`), but the
  askpass dialog timed out (owner AFK) and a transient DNS failure
  ("Could not resolve host: github.com", self-healed in ~1 min) cost
  two failed push attempts before a manual `git push` succeeded once
  the owner answered the dialog. Builds were never affected; the
  commit sat safely local between attempts.
- Session check post-run (21:47, ~5 min after the last Instagram
  build): still `rate_limited` — web_profile_info stays throttled
  well after a run. The cookie itself is fine: permalink fetches with
  the same cookie succeeded throughout the run. Practical upshot:
  run `check_instagram_session.py` *before* a build or much later
  after one, not right after.

## Verification

- `.venv/bin/pytest`: 230 passed (baseline) → **257 passed** (27 new
  `tests/test_status.py` tests, red→green).
- Timer: `systemctl --user list-timers` →
  `Sat 2026-10-10 21:42:05 CEST, 23h left` (OnUnitInactiveSec=1d);
  `Linger=yes`.
- End-to-end first run 21:16:05→21:39:03 CEST under the real service:
  Quora, Klum, BRF + 11 Instagram accounts rebuilt, 14 files changed,
  committed `5277d6e` and pushed to origin after askpass auth
  (`a7033a5..5277d6e`).
- `scripts/status.py` live: last update commit + per-feed table + 
  `failed feeds: 0`, exit 0; `--check-session` reports
  `rate_limited` post-run as expected (exit 1 path verified by tests).
- New entries visible in the report after the run (daxwerner 12→13,
  jamborjoanna 12→14, waveybobson 12→13).

## Status

done
