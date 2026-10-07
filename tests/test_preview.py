"""Tests for the local feed preview server in scripts/preview_feeds.py."""

import os

import preview_feeds


class TestFeedsDir:
    def test_points_at_repo_feeds_dir(self):
        expected = os.path.normpath(
            os.path.join(os.path.dirname(preview_feeds.__file__), "..", "feeds")
        )
        assert preview_feeds.feeds_dir() == expected

    def test_dir_exists(self):
        assert os.path.isdir(preview_feeds.feeds_dir())


class TestFeedLinks:
    def test_lists_all_generated_feeds(self):
        import glob

        links = preview_feeds.feed_links()
        on_disk = sorted(
            os.path.basename(p) for p in glob.glob(f"{preview_feeds.feeds_dir()}/*.xml")
        )
        assert links == on_disk

    def test_excludes_stylesheets(self):
        assert all(link.endswith(".xml") for link in preview_feeds.feed_links())


class TestParseArgs:
    def test_defaults(self):
        args = preview_feeds.parse_args([])
        assert args.port == preview_feeds.DEFAULT_PORT
        assert args.feed is None

    def test_feed_and_port(self):
        args = preview_feeds.parse_args(["instagram-daxwerner.xml", "--port", "9999"])
        assert args.feed == "instagram-daxwerner.xml"
        assert args.port == 9999
