#!/usr/bin/env python3
"""Preview the generated feeds in a browser via a local HTTP server.

Browsers refuse to apply xml-stylesheet XSLT to file:// documents (see
tickets/0012), so the feeds directory is served over loopback HTTP and
the feed is opened at http://127.0.0.1:<port>/. The stylesheet then
renders every carousel slide and <video> tag (a few lines of JS inject
the content:encoded HTML).

Usage: python scripts/preview_feeds.py [feed.xml] [--port 8321]
"""

import argparse
import functools
import http.server
import os
import sys
import webbrowser

DEFAULT_PORT = 8321


def feeds_dir() -> str:
    return os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "feeds")
    )


def feed_links() -> list[str]:
    directory = feeds_dir()
    return sorted(
        name
        for name in os.listdir(directory)
        if name.endswith(".xml") and os.path.isfile(os.path.join(directory, name))
    )


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "feed", nargs="?", help="feed file to open directly (e.g. instagram-daxwerner.xml)"
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    directory = feeds_dir()
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=directory)
    url = f"http://127.0.0.1:{args.port}/"
    target = url + (args.feed if args.feed else "")
    print(f"serving {directory} at {url}")
    for name in feed_links():
        print(f"  {url}{name}")
    print(f"opening {target}")
    webbrowser.open(target)
    try:
        http.server.ThreadingHTTPServer(("127.0.0.1", args.port), handler).serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
