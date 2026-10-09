#!/usr/bin/env python3
"""Health report for the rss-feeds setup, offline by default.

Prints per-feed item counts, embedded build-failure warnings, feed age
and newest-entry age, plus the last "Update feeds" commit and the state
of the systemd update timer. Reads only local state: feeds/*.xml, git
log and systemctl. --check-session adds the live Instagram session
check (scripts/check_instagram_session.py, secrets from
~/.config/rss-feeds/env if present).

Exit codes (monitoring-friendly):

0 healthy
1 failures detected — "Feed build failed" items in any feed, an
  unreadable feed, or --check-session reported a failure
2 update automation not active — the timer unit is disabled or missing;
  if systemctl itself is unreachable the state is "unknown" and does
  not affect the exit code (exit 2 takes precedence over 1)

Usage: .venv/bin/python scripts/status.py [--check-session] [--account NAME]
"""

import argparse
import os
import subprocess
import sys
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common

UNIT = "rss-feeds-update.timer"
ENV_FILE = os.path.join(
    os.path.expanduser("~"), ".config", "rss-feeds", "env"
)
CHECK_SCRIPT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "check_instagram_session.py"
)


def repo_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _run(argv: list) -> tuple:
    proc = subprocess.run(argv, capture_output=True, text=True)
    return proc.returncode, proc.stdout


def feed_summary(path: str) -> dict | None:
    """Item/warning counts and dates from one generated feed file."""
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            soup = BeautifulSoup(f.read(), "xml")
        channel = soup.find("channel")
        if channel is None:
            return None
    except Exception:  # noqa: BLE001
        return None

    def _date(node):
        if node is None:
            return None
        try:
            return parsedate_to_datetime(node.get_text(strip=True))
        except (TypeError, ValueError):
            return None

    items = channel.find_all("item")
    warnings = 0
    dates = []
    for item in items:
        guid = item.find("guid")
        if guid is not None and guid.get_text(strip=True).endswith(
            common.WARNING_ID_SUFFIX
        ):
            warnings += 1
        pub = _date(item.find("pubDate"))
        if pub is not None:
            dates.append(pub)

    return {
        "items": len(items),
        "warnings": warnings,
        "last_build": _date(channel.find("lastBuildDate")),
        "newest": max(dates) if dates else None,
    }


def staleness(now: datetime, dt: datetime | None) -> str:
    """Human-readable age, aware or naive datetimes (naive = UTC)."""
    if dt is None:
        return "never"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    seconds = (now - dt).total_seconds()
    if seconds < 0:
        return "now"
    minutes = int(seconds // 60)
    if minutes < 60:
        return f"{minutes}m ago"
    hours = int(seconds // 3600)
    if hours < 48:
        return f"{hours}h ago"
    return f"{int(seconds // 86400)}d ago"


def last_update_run(run=None) -> dict | None:
    """Most recent 'Update feeds' commit: hash, date, subject."""
    run = run or _run
    argv = [
        "git", "-C", repo_root(), "log", "-1",
        "--grep=^Update feeds", "--format=%h%x00%cI%x00%s",
    ]
    _rc, out = run(argv)
    line = out.strip().split("\n")[0] if out.strip() else ""
    parts = line.split("\x00")
    if len(parts) != 3:
        return None
    date = None
    try:
        date = datetime.fromisoformat(parts[1])
    except ValueError:
        pass
    return {"hash": parts[0], "date": date, "subject": parts[2]}


def timer_state(run=None) -> tuple:
    """(state, next elapse) of the update timer.

    States: "enabled", "inactive" (missing/disabled/masked) or
    "unknown" (no systemctl, no user bus) — "unknown" must not fail
    monitoring on machines without systemd.
    """
    run = run or _run
    try:
        rc, out = run(["systemctl", "--user", "is-enabled", UNIT])
    except OSError:
        return ("unknown", None)
    if not out.strip():
        return ("unknown", None)
    if not (rc == 0 and out.strip() == "enabled"):
        return ("inactive", None)
    _rc, out = run(
        ["systemctl", "--user", "show", UNIT,
         "--property=NextElapseUSecRealtime", "--value"]
    )
    next_elapse = None
    try:
        usec = int(out.strip())
    except ValueError:
        usec = 0
    if usec > 0:
        moment = datetime.fromtimestamp(usec / 1_000_000)
        next_elapse = moment.strftime("%Y-%m-%d %H:%M")
    return ("enabled", next_elapse)


def load_env_file(path: str) -> dict:
    """KEY=value pairs from a systemd EnvironmentFile-style file."""
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return {}
    values = {}
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def run_session_check(account: str) -> tuple:
    """(rc, stdout) of the live Instagram session check."""
    env = dict(os.environ)
    env.update(load_env_file(ENV_FILE))
    try:
        proc = subprocess.run(
            [sys.executable, CHECK_SCRIPT, account],
            capture_output=True, text=True, env=env,
        )
    except OSError as exc:
        return 4, f"error: {exc}"
    return proc.returncode, proc.stdout


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="rss-feeds health report (offline by default)"
    )
    parser.add_argument(
        "--check-session", action="store_true",
        help="also run the live Instagram session check",
    )
    parser.add_argument(
        "--account", default="tiny_ruins",
        help="account for --check-session (default: %(default)s)",
    )
    args = parser.parse_args(argv)

    now = datetime.now(timezone.utc)
    failed_feeds = 0
    session_failed = False

    git_info = last_update_run()
    if git_info:
        when = git_info["date"]
        stamp = (
            when.astimezone().strftime("%Y-%m-%d %H:%M")
            if when else "unknown date"
        )
        print(f"last update commit: {git_info['hash']} {stamp} {git_info['subject']}")
    else:
        print("last update commit: none found")

    state, next_elapse = timer_state()
    suffix = f" (next {next_elapse})" if next_elapse else ""
    print(f"update timer: {state}{suffix}")

    if args.check_session:
        rc, out = run_session_check(args.account)
        kind = out.split(":", 1)[0].strip() if out.strip() else "error"
        print(f"instagram session: {kind}")
        session_failed = rc != 0

    feeds_dir = os.path.join(repo_root(), "feeds")
    names = sorted(
        n for n in os.listdir(feeds_dir) if n.endswith(".xml")
    ) if os.path.isdir(feeds_dir) else []

    header = f"{'feed':<38} {'items':>5} {'warnings':>8}  {'built':<10} {'newest':<10}"
    print(header)
    for name in names:
        summary = feed_summary(os.path.join(feeds_dir, name))
        if summary is None:
            failed_feeds += 1
            print(f"{name:<38} {'unreadable':>5}")
            continue
        if summary["warnings"]:
            failed_feeds += 1
        built = staleness(now, summary["last_build"])
        newest = staleness(now, summary["newest"])
        print(
            f"{name:<38} {summary['items']:>5} {summary['warnings']:>8}"
            f"  {built:<10} {newest:<10}"
        )
    print(f"failed feeds: {failed_feeds}")

    if state == "inactive":
        return 2
    if failed_feeds or session_failed:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
