#!/usr/bin/env python3
"""Check whether INSTAGRAM_SESSIONID is set and actually works.

Makes a single web_profile_info API call for an account and classifies
the outcome. Never prints the cookie value. Exit codes:

0 ok — session works, N posts parsed
2 rate_limited — 429, throttle; retry later
3 auth_failed — 401/403, sessionid expired or invalid
4 error — anything else
5 no session — INSTAGRAM_SESSIONID not set

Usage: python scripts/check_instagram_session.py [account]
"""

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_instagram_feed as b

OK = 0
RATE_LIMITED = 2
AUTH_FAILED = 3
ERROR = 4
NO_SESSION = 5


def classify(status: int) -> str:
    if 200 <= status < 300:
        return "ok"
    if status == 429:
        return "rate_limited"
    if status in (401, 403):
        return "auth_failed"
    return "error"


def status_of(exc: Exception) -> int | None:
    response = getattr(exc, "response", None)
    code = getattr(response, "status_code", None)
    if code:
        return int(code)
    m = re.search(r"\b(\d{3})\b", str(exc))
    return int(m.group(1)) if m else None


def count_posts(text: str) -> int:
    return len(b.parse_api(text))


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("account", nargs="?", default="tiny_ruins")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    if not os.environ.get("INSTAGRAM_SESSIONID"):
        print("no_session: INSTAGRAM_SESSIONID not set")
        return NO_SESSION
    try:
        b.validate_account(args.account)
    except ValueError as exc:
        print(f"error: {exc}")
        return ERROR
    try:
        text = b.fetch_api_profile(args.account)
    except Exception as exc:  # noqa: BLE001
        kind = classify(status_of(exc) or 0)
        detail = " ".join(str(exc).split())[:120]
        print(f"{kind}: {args.account} — {type(exc).__name__}: {detail}")
        return {"rate_limited": RATE_LIMITED, "auth_failed": AUTH_FAILED}.get(
            kind, ERROR
        )
    if text is None:
        print("no_session: INSTAGRAM_SESSIONID not set")
        return NO_SESSION
    print(f"ok: {args.account} — {count_posts(text)} post(s) parsed")
    return OK


if __name__ == "__main__":
    sys.exit(main())
