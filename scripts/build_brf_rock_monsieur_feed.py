#!/usr/bin/env python3
"""Build a podcast feed for BRF1's "Rock Monsieur" show.

Thin wrapper around the shared scripts/brf1_show_feed.py, which does all
the work (parsing, audio resolution, feed assembly).

The show (thursdays 20-21h, https://1.brf.be/sendungen/rock-monsieur/) is
not published as a podcast by BRF.

Usage: python scripts/build_brf_rock_monsieur_feed.py
Optional env: ROCK_MONSIEUR_HTML=<file> (parse a saved archive copy
offline), ROCK_MONSIEUR_PAGES_DIR=<dir> (saved episode pages, offline
mode), ROCK_MONSIEUR_PLAY_DIR=<dir> (saved play-endpoint snippets,
offline mode).
"""

import os
import os.path
import sys

import brf1_show_feed

CFG = brf1_show_feed.ShowConfig(
    slug="rock-monsieur",
    title="Rock Monsieur (BRF1)",
    description=(
        "Rock Monsieur präsentiert Musik vom Tellerrand: schräg gebürstet "
        "oder melancholisch offen getragen, düster treibend oder gepflegt "
        "verzweifelnd, geschüttelt und gerührt. Jede Woche neue Alben, alter "
        "Kram und andere potentielle Ohrschmeichler. Der BRF1-Grenzpendler "
        "zwischen Alternative, Post, Indie, Experimental und allem, was ihm "
        "sonst noch so über den Weg läuft. Immer mit wachsamem Blick auf die "
        "belgische Musikszene. Moderation: Volker Krings, Roger Pint. "
        "Donnerstag, 20 - 21 Uhr."
    ),
    image=(
        "https://1.brf.be/wp-content/uploads/sites/2/2021/05/"
        "rockmonsieur_motiv-1420x968.jpg"
    ),
    output_path=os.path.normpath(
        os.path.join(
            os.path.dirname(__file__), "..", "feeds", "brf1-rock-monsieur.xml"
        )
    ),
    env_prefix="ROCK_MONSIEUR",
)

if __name__ == "__main__":
    sys.exit(brf1_show_feed.main(CFG))
