"""Tests for the shared feed-building helpers in scripts/common.py."""

from datetime import datetime, timezone

import pytest

import common


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

    def test_guid_is_used_as_key_and_id(self, tmp_path):
        """Items whose guid differs from the link must keep their real id."""
        path = write_feed(
            tmp_path,
            """<?xml version="1.0" encoding="UTF-8"?>
            <rss version="2.0"><channel>
              <item>
                <title>Anchor item</title>
                <link>https://example.com/news</link>
                <guid isPermaLink="false">https://example.com/news#20260101-anchor-item</guid>
                <description>text</description>
                <pubDate>Thu, 01 Jan 2026 00:00:00 GMT</pubDate>
              </item>
            </channel></rss>""",
        )
        prev = common.load_previous(path)
        assert set(prev) == {"https://example.com/news#20260101-anchor-item"}
        entry = prev["https://example.com/news#20260101-anchor-item"]
        assert entry["id"] == "https://example.com/news#20260101-anchor-item"
        assert entry["link"] == "https://example.com/news"
        assert entry["published"] == datetime(2026, 1, 1, tzinfo=timezone.utc)


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

    @staticmethod
    def prev_item(item_id, title, link, published):
        return {
            "id": item_id,
            "title": title,
            "link": link,
            "description": title,
            "published": published,
        }

    @staticmethod
    def new_item(item_id, title, link, published):
        return {
            "id": item_id,
            "title": title,
            "link": link,
            "description": title,
            "published": published,
        }

    def test_drops_old_guid_entry_with_same_link_and_date(self):
        """Old guid==link entries must not survive next to their anchor twin."""
        old = self.prev_item(
            "https://youtu.be/Vt4nSIlJV6Q",
            "Ich mache Schluß mit Insta.",
            "https://youtu.be/Vt4nSIlJV6Q",
            datetime(2026, 8, 13, tzinfo=timezone.utc),
        )
        new = self.new_item(
            "https://www.klum.com/news#20260813-ich-mache-schlu-mit-insta",
            "Ich mache Schluß mit Insta.",
            "https://youtu.be/Vt4nSIlJV6Q",
            datetime(2026, 8, 13, tzinfo=timezone.utc),
        )
        merged = common.merge_items({"https://youtu.be/Vt4nSIlJV6Q": old}, [new])
        assert list(merged) == ["https://www.klum.com/news#20260813-ich-mache-schlu-mit-insta"]

    def test_drops_old_guid_entry_with_same_title_and_date(self):
        """Catches entries whose link changed between id schemes."""
        old = self.prev_item(
            "https://www.klum.com/news",
            "Der Möchtegernekanzler",
            "https://www.klum.com/news",
            datetime(2026, 9, 21, tzinfo=timezone.utc),
        )
        new = self.new_item(
            "https://www.klum.com/news#20260921-der-mochtegernekanzler",
            "Der Möchtegernekanzler",
            "https://www.klum.com/news",
            datetime(2026, 9, 21, tzinfo=timezone.utc),
        )
        merged = common.merge_items({"https://www.klum.com/news": old}, [new])
        assert list(merged) == ["https://www.klum.com/news#20260921-der-mochtegernekanzler"]

    def test_keeps_genuine_repost_with_same_title_other_date(self):
        old = self.prev_item(
            "https://www.klum.com/news#20251219-ist-die-schweiz-ein-vorbild-fur-uns",
            "Ist die Schweiz ein Vorbild für uns?",
            "https://www.youtube.com/watch?v=IjaLps8PYPM",
            datetime(2025, 12, 19, tzinfo=timezone.utc),
        )
        new = self.new_item(
            "https://www.klum.com/news#20250801-ist-die-schweiz-ein-vorbild-fur-uns",
            "Ist die Schweiz ein Vorbild für uns?",
            "https://www.youtube.com/watch?v=IjaLps8PYPM",
            datetime(2025, 8, 1, tzinfo=timezone.utc),
        )
        merged = common.merge_items(
            {
                "https://www.klum.com/news#20251219-ist-die-schweiz-ein-vorbild-fur-uns": old,
            },
            [new],
        )
        assert len(merged) == 2

    def test_undated_entries_are_never_dropped(self):
        old = self.prev_item(
            "https://example.com/old",
            "Same title",
            "https://example.com/old",
            None,
        )
        new = self.new_item(
            "https://example.com/new",
            "Same title",
            "https://example.com/new",
            None,
        )
        merged = common.merge_items({"https://example.com/old": old}, [new])
        assert len(merged) == 2

    def test_full_cycle_old_feed_format(self, tmp_path):
        """Regression: regenerating over an old guid==link feed yields no dupes."""
        old_xml = """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0"><channel>
          <item>
            <title>Elektrosmog</title>
            <link>https://www.klum.com/empty-pagee3f564cc</link>
            <guid isPermaLink="false">https://www.klum.com/empty-pagee3f564cc</guid>
            <description>Elektrosmog</description>
            <pubDate>Tue, 25 Aug 2026 00:00:00 +0000</pubDate>
          </item>
        </channel></rss>"""
        path = write_feed(tmp_path, old_xml)
        previous = common.load_previous(path)
        new = self.new_item(
            "https://www.klum.com/news#20260825-elektrosmog",
            "Elektrosmog",
            "https://www.klum.com/wupsi-offiziele-anfrage-handy",
            datetime(2026, 8, 25, tzinfo=timezone.utc),
        )
        merged = common.merge_items(previous, [new])
        assert len(merged) == 1
        assert merged[new["id"]]["link"] == new["link"]


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

    def test_preserves_item_order(self):
        """feedgen 1.0.0 prepends entries by default; feed order must survive."""
        items = [
            {
                "id": f"https://example.com/{n}",
                "title": f"item {n}",
                "link": f"https://example.com/{n}",
                "description": "",
                "published": None,
            }
            for n in (1, 2, 3)
        ]
        xml = common.build_feed(
            items,
            feed_id="https://example.com/",
            title="T",
            link="https://example.com/",
            description="d",
            language="en",
        ).decode("utf-8")
        titles = [t.strip() for t in __import__("re").findall(
            r"<title>(item \d)</title>", xml
        )]
        assert titles == ["item 1", "item 2", "item 3"]
