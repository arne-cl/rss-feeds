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

## Verification

(partial, to be completed)

- `.venv/bin/pytest` baseline: 230 passed.
- `systemctl --user list-timers rss-feeds-update.timer`: timer enabled,
  first run started 2026-10-09 21:16:05 CEST right after enable; builds
  ran clean (Quora, Klum, BRF, Instagram accounts in progress);
  `loginctl show-user arne -p Linger` → `Linger=yes`.

## Status

todo
