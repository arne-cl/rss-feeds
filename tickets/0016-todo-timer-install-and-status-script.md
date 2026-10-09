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

(to be filled during implementation)

## Verification

(to be filled: session check result, list-timers output, journal
excerpt, pytest count, example status output)

## Status

todo
