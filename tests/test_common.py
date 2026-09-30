"""Tests for the shared feed-building helpers in scripts/common.py."""

from datetime import datetime, timezone

import pytest

from scripts import common


def write_feed(tmp_path, xml):
    path = tmp_path / "prev.xml"
    path.write_text(xml, encoding="utf-8")
    return str(path)


class TestLoadPrevious:
    def test_loads_items_with_metadata(self, tmp_path):
        path = write_feed(
            tmp_path,
            """<?xml version="1.0" encoding="UTF-8"?>
            <rss version="2.0"><channel>
              <item>
                <title>First post</title>
                <link>https://example.com/a</link>
                <description>Hello</description>
                <pubDate>Mon, 01 Sep 2025 10:00:00 GMT</pubDate>
              </item>
              <item>
                <title>Second post</title>
                <link>https://example.com/b</link>
                <description/>
              </item>
            </channel></rss>""",
        )
        prev = common.load_previous(path)
        assert set(prev) == {"https://example.com/a", "https://example.com/b"}
        a = prev["https://example.com/a"]
        assert a["title"] == "First post"
        assert a["description"] == "Hello"
        assert a["published"] == datetime(2025, 9, 1, 10, 0, tzinfo=timezone.utc)
        b = prev["https://example.com/b"]
        assert b["published"] is None

    def test_missing_file(self, tmp_path):
        assert common.load_previous(str(tmp_path / "nope.xml")) == {}

    def test_unparseable_file(self, tmp_path):
        path = write_feed(tmp_path, "this is not xml at all")
        assert common.load_previous(path) == {}

    def test_item_without_link_is_skipped(self, tmp_path):
        path = write_feed(
            tmp_path,
            """<?xml version="1.0" encoding="UTF-8"?>
            <rss version="2.0"><channel>
              <item><title>no link</title><description>x</description></item>
            </channel></rss>""",
        )
        assert common.load_previous(path) == {}


class TestSortKey:
    def test_none_sorts_oldest(self):
        none_key = common.sort_key({"published": None})
        dated_key = common.sort_key(
            {"published": datetime(2020, 1, 1, tzinfo=timezone.utc)}
        )
        assert none_key < dated_key

    def test_naive_datetime_treated_as_utc(self):
        naive = common.sort_key({"published": datetime(2020, 1, 1)})
        aware = common.sort_key(
            {"published": datetime(2020, 1, 1, tzinfo=timezone.utc)}
        )
        assert naive == aware

    def test_ordering(self):
        items = [
            {"published": datetime(2021, 1, 1, tzinfo=timezone.utc)},
            {"published": None},
            {"published": datetime(2022, 1, 1, tzinfo=timezone.utc)},
        ]
        ordered = sorted(items, key=common.sort_key, reverse=True)
        assert ordered[0]["published"].year == 2022
        assert ordered[1]["published"].year == 2021
        assert ordered[2]["published"] is None


class TestMergeItems:
    def test_merges_and_preserves_dates(self):
        prev = {
            "https://example.com/a": {
                "id": "https://example.com/a",
                "title": "old title",
                "link": "https://example.com/a",
                "description": "old desc",
                "published": datetime(2025, 1, 1, tzinfo=timezone.utc),
            }
        }
        new = {
            "id": "https://example.com/a",
            "title": "new title",
            "link": "https://example.com/a",
            "description": "new desc",
            "published": None,
        }
        merged = common.merge_items(prev, [new])
        assert merged["https://example.com/a"]["title"] == "new title"
        assert merged["https://example.com/a"]["published"] == datetime(
            2025, 1, 1, tzinfo=timezone.utc
        )

    def test_new_item_added(self):
        new = {
            "id": "https://example.com/x",
            "title": "x",
            "link": "https://example.com/x",
            "description": "",
            "published": datetime(2026, 9, 30, tzinfo=timezone.utc),
        }
        merged = common.merge_items({}, [new])
        assert merged == {"https://example.com/x": new}


class TestBuildFeed:
    def test_feed_metadata_and_entries(self):
        items = [
            {
                "id": "https://example.com/a",
                "title": "An entry",
                "link": "https://example.com/a",
                "description": "text",
                "published": datetime(2025, 9, 1, 10, 0, tzinfo=timezone.utc),
            },
            {
                "id": "https://example.com/b",
                "title": "No date",
                "link": "https://example.com/b",
                "description": "",
                "published": None,
            },
        ]
        xml = common.build_feed(
            items,
            feed_id="https://example.com/news",
            title="Example News",
            link="https://example.com/news",
            description="News from example.com",
            language="de",
        ).decode("utf-8")
        assert "<title>Example News</title>" in xml
        assert "News from example.com" in xml
        assert "<language>de</language>" in xml
        assert xml.count("<item>") == 2
        assert "<title>An entry</title>" in xml
        assert (
            "<pubDate>Mon, 01 Sep 2025 10:00:00 +0000</pubDate>" in xml
        )  # published date present

    def test_requires_all_metadata(self):
        items = []
        with pytest.raises(TypeError):
            common.build_feed(items)
