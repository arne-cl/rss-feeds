#!/usr/bin/env python3
"""Run Instagram feed builders with a reactive 429 stagger.

Unconditional sleeps used to cost ~8 minutes per update run. Here the
default gap between accounts is 2s; only a builder that reports a
permalink 429 (via ``THROTTLE_MARKER``) makes the next gap 45s, then
90s, capped at 180s for the rest of the run.

``web_profile_info`` 429s are intentionally not markers: that endpoint
returns a fake/neutered 429 even with a valid session (tickets 0013 and
0015), while permalink fetches then succeed.

Usage: python scripts/instagram_stagger.py [--builder PATH] <account>...
"""

import argparse
import os
import subprocess
import sys
import time

DEFAULT_DELAY = 2.0
FIRST_THROTTLE_DELAY = 45.0
MAX_DELAY = 180.0
THROTTLE_MARKER = "::instagram-throttled::"

BUILDER = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "build_instagram_feed.py"
)


def next_delay(current: float, throttled: bool) -> float:
    """Gap before the next account: short until a 429, then cautious."""
    if throttled:
        if current < FIRST_THROTTLE_DELAY:
            return FIRST_THROTTLE_DELAY
        return min(current * 2, MAX_DELAY)
    if current >= FIRST_THROTTLE_DELAY:
        return current
    return DEFAULT_DELAY


def run_accounts(accounts, run, sleep, delay: float = DEFAULT_DELAY) -> int:
    """Build accounts in order, backing off when a run reports throttling.

    ``run(account)`` returns ``(returncode, output)`` and ``sleep`` is
    injectable for tests. Output is echoed unchanged; a non-zero builder
    return code stops the run.
    """
    current = delay
    for index, account in enumerate(accounts):
        if index:
            sleep(current)
        returncode, output = run(account)
        if output:
            print(output, end="" if output.endswith("\n") else "\n", flush=True)
        if returncode != 0:
            return returncode
        current = next_delay(current, THROTTLE_MARKER in output)
    return 0


def run_builder(builder: str, account: str) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, builder, account],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return proc.returncode, proc.stdout or ""


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--builder", default=BUILDER)
    parser.add_argument("accounts", nargs="+")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    return run_accounts(
        args.accounts,
        lambda account: run_builder(args.builder, account),
        time.sleep,
    )


if __name__ == "__main__":
    sys.exit(main())
