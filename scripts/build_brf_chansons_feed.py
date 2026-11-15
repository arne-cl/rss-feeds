#!/usr/bin/env python3
"""Build a podcast feed for BRF1's "Chansons, Lieder und Folk" show.

Thin wrapper around the shared scripts/brf1_show_feed.py, which does all
the work (parsing, audio resolution, feed assembly).

The show (mondays 20-21h, https://1.brf.be/sendungen/chansons/) is not
published as a podcast by BRF.

Usage: python scripts/build_brf_chansons_feed.py
Optional env: CHANSONS_HTML=<file> (parse a saved archive copy offline),
CHANSONS_PAGES_DIR=<dir> (saved episode pages, offline mode),
CHANSONS_PLAY_DIR=<dir> (saved play-endpoint snippets, offline mode).
"""

import os
import os.path
import sys

import brf1_show_feed

CFG = brf1_show_feed.ShowConfig(
    slug="chansons",
    title="Chansons, Lieder und Folk (BRF1)",
    description=(
        "Eine Sendung, die, wenn es sie nicht schon seit über 30 Jahren geben "
        "würde, für Ostbelgien erfunden werden müsste. Am Schnittpunkt der "
        "Kulturen stellt der BRF französische Chansons, deutschsprachige Lieder "
        "und internationale Folk- und Worldmusic vor. Montag, 20 - 21 Uhr."
    ),
    image="https://1.brf.be/wp-content/uploads/sites/2/2015/06/CLF-1420x968.jpg",
    output_path=os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "feeds", "brf1-chansons.xml")
    ),
    env_prefix="CHANSONS",
)

if __name__ == "__main__":
    sys.exit(brf1_show_feed.main(CFG))
