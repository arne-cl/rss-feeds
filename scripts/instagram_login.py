#!/usr/bin/env python3
"""Instagram session helper: interactive login + unattended refresh.

Two subcommands sharing one persistent browser profile
(~/.config/rss-feeds/ig-profile) — a live session in that profile is
what keeps the cookie rolling:

  login    headful; opens instagram.com, you log in once (incl. 2FA),
           the fresh sessionid is verified via one web_profile_info
           call and only then written to the env file
  refresh  headless; touches instagram.com so Instagram rolls the
           session cookie, verifies a changed cookie before adopting
           it, and rewrites the env file. Called from
           update_local.sh before the Instagram builds; never fatal.

The cookie value is never printed. Exit codes: 0 ok, 3 session
expired (manual `login` needed), 4 error.
"""

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import build_instagram_feed as b
from check_instagram_session import classify
from common import status_of

CHROMIUM = "/usr/bin/chromium"
ENV_PATH = os.path.expanduser("~/.config/rss-feeds/env")
PROFILE_DIR = os.path.expanduser("~/.config/rss-feeds/ig-profile")
IG_URL = "https://www.instagram.com/"
LOGIN_TIMEOUT_SEC = 300
POLL_SEC = 2
TOUCH_SETTLE_SEC = 5

OK = 0
EXPIRED = 3
ERROR = 4


# --------------------------------------------------------------------------
# Pure helpers (offline-tested)
# --------------------------------------------------------------------------

def read_env_value(path: str, key: str = "INSTAGRAM_SESSIONID") -> str | None:
    """Value of key in a systemd EnvironmentFile, or None."""
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.startswith(key + "="):
                    return line.strip().split("=", 1)[1] or None
    except FileNotFoundError:
        pass
    return None


def update_env_file(path: str, value: str, key: str = "INSTAGRAM_SESSIONID") -> None:
    """Atomically set key=value in a systemd EnvironmentFile.

    Replaces the existing key line or appends; preserves everything
    else; chmod 600; writes via a same-directory temp file + rename.
    """
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
    except FileNotFoundError:
        lines = []
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    new_line = f"{key}={value}\n"
    for i, line in enumerate(lines):
        if line.startswith(key + "="):
            lines[i] = new_line
            break
    else:
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        lines.append(new_line)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.writelines(lines)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def pick_cookie(cookies: list[dict], name: str = "sessionid") -> str | None:
    """Cookie value by name for any *.instagram.com domain, or None."""
    for cookie in cookies:
        if (
            cookie.get("name") == name
            and "instagram.com" in (cookie.get("domain") or "")
        ):
            return cookie.get("value") or None
    return None


def verify_sessionid(value: str, account: str = "tiny_ruins") -> tuple[str, int]:
    """(kind, posts) for a candidate cookie via one web_profile_info call.

    kind is check_instagram_session's classification: ok, rate_limited
    (cookie authenticated but throttled), auth_failed, error.
    """
    try:
        text = b.fetch_api_profile(account, session_id=value)
    except Exception as exc:  # noqa: BLE001
        return classify(status_of(exc) or 0), 0
    return "ok", len(b.parse_api(text))


def refresh_policy(
    stored: str | None,
    candidate: str | None,
    stored_kind: str | None,
    candidate_kind: str | None,
) -> tuple[str, str | None]:
    """Decide what to do after a refresh touch.

    Returns (action, value) with action:
      noop    keep the stored cookie (nothing written)
      adopt   write the candidate cookie to the env file
      expired no usable session anywhere — manual login needed
    """
    if candidate is None:
        if stored is None or stored_kind == "auth_failed":
            return "expired", None
        return "noop", stored
    if candidate == stored:
        return "noop", stored
    if candidate_kind == "ok":
        return "adopt", candidate
    if candidate_kind == "rate_limited":
        if stored_kind in ("auth_failed", None):
            return "adopt", candidate
        return "noop", stored
    if candidate_kind == "auth_failed":
        if stored is None or stored_kind == "auth_failed":
            return "expired", None
        return "noop", stored
    return "noop", stored


def wait_for_sessionid(cookies_fn, timeout: float, poll: float) -> str | None:
    """Poll cookies_fn() until a sessionid shows up, or None on timeout."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = pick_cookie(cookies_fn())
        if value:
            return value
        time.sleep(min(poll, max(0.0, deadline - time.monotonic())))
    return None


# --------------------------------------------------------------------------
# Browser plumbing
# --------------------------------------------------------------------------

def launch_context(playwright, *, headless: bool):
    """Persistent Chromium context sharing the ig-profile directory."""
    os.makedirs(PROFILE_DIR, mode=0o700, exist_ok=True)
    return playwright.chromium.launch_persistent_context(
        PROFILE_DIR,
        executable_path=CHROMIUM,
        headless=headless,
        args=["--no-first-run", "--no-default-browser-check"],
    )


def touch_and_extract() -> str | None:
    """Headless instagram.com visit; the (possibly rotated) sessionid."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        context = launch_context(p, headless=True)
        try:
            page = context.new_page()
            page.goto(IG_URL, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(TOUCH_SETTLE_SEC * 1000)
            return pick_cookie(context.cookies())
        finally:
            context.close()


def cmd_login(args) -> int:
    from playwright.sync_api import sync_playwright

    print(f"log in to instagram.com in the window that opens "
          f"(profile: {PROFILE_DIR}); do NOT click logout afterwards")
    with sync_playwright() as p:
        context = launch_context(p, headless=False)
        try:
            page = context.new_page()
            page.goto(IG_URL, timeout=60000, wait_until="domcontentloaded")
            value = wait_for_sessionid(
                context.cookies, LOGIN_TIMEOUT_SEC, POLL_SEC
            )
            if not value:
                print(f"error: no sessionid within {LOGIN_TIMEOUT_SEC}s")
                return ERROR
            kind, posts = verify_sessionid(value, account=args.account)
            if kind == "ok":
                update_env_file(ENV_PATH, value)
                print(f"ok: fresh session verified ({posts} post(s) parsed) "
                      f"-> {ENV_PATH}")
                return OK
            print(f"warning: cookie classified {kind} (not stored)")
            if kind == "rate_limited":
                # 429 = authenticated but throttled (ticket 0013); storing
                # is usually fine — it just needs the throttle to clear.
                if args.store_throttled:
                    update_env_file(ENV_PATH, value)
                    print(f"ok: stored unverified (throttled) -> {ENV_PATH}")
                    return OK
                if sys.stdin.isatty():
                    answer = input("store it anyway? [y/N] ").strip().lower()
                    if answer == "y":
                        update_env_file(ENV_PATH, value)
                        print(f"ok: stored unverified (throttled) -> {ENV_PATH}")
                        return OK
                else:
                    print("stdin is not interactive — re-run "
                          "`login --store-throttled` to store it anyway")
            return ERROR
        finally:
            context.close()


def cmd_refresh(args) -> int:
    stored = read_env_value(ENV_PATH)
    try:
        candidate = touch_and_extract()
    except Exception as exc:  # noqa: BLE001
        print(f"error: browser touch failed: {exc}")
        return ERROR

    candidate_kind: str | None = None
    stored_kind: str | None = None
    if candidate is not None and candidate != stored:
        candidate_kind = verify_sessionid(candidate, account=args.account)[0]
    if candidate is None or candidate_kind in ("auth_failed", "rate_limited"):
        if stored:
            stored_kind = verify_sessionid(stored, account=args.account)[0]

    action, value = refresh_policy(stored, candidate, stored_kind, candidate_kind)
    if action == "adopt":
        update_env_file(ENV_PATH, value)
        print("ok: adopted fresh session cookie (verified)")
        return OK
    if action == "expired":
        print("session expired: run scripts/instagram_login.py login")
        return EXPIRED
    if candidate is not None and candidate != stored:
        print(f"ok: kept stored session (candidate {candidate_kind})")
    else:
        print("ok: session unchanged" if candidate is not None
              else "ok: no browser session, stored cookie still works")
    return OK


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("login", "refresh"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--account", default="tiny_ruins",
                         help="account for the verification API call")
    sub.choices["login"].add_argument(
        "--store-throttled", action="store_true",
        help="store the cookie even if verification is only 429-throttled "
             "(instead of asking on the terminal)",
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    if args.command == "login":
        return cmd_login(args)
    return cmd_refresh(args)


if __name__ == "__main__":
    sys.exit(main())
