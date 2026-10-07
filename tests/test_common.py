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

    def test_content_encoded_is_read_back(self, tmp_path):
        """Embedded article HTML must survive round-trips (content cache)."""
        path = write_feed(
            tmp_path,
            """<?xml version="1.0" encoding="UTF-8"?>
            <rss xmlns:content="http://purl.org/rss/1.0/modules/content/"
                 version="2.0"><channel>
              <item>
                <title>With content</title>
                <link>https://example.com/a</link>
                <description>short</description>
                <content:encoded><![CDATA[<p>full text</p>]]></content:encoded>
              </item>
            </channel></rss>""",
        )
        prev = common.load_previous(path)
        assert prev["https://example.com/a"]["content"] == "<p>full text</p>"

    def test_without_content_encoded_key_is_absent(self, tmp_path):
        path = write_feed(
            tmp_path,
            """<?xml version="1.0" encoding="UTF-8"?>
            <rss version="2.0"><channel>
              <item>
                <title>Plain</title>
                <link>https://example.com/b</link>
                <description>x</description>
              </item>
            </channel></rss>""",
        )
        prev = common.load_previous(path)
        assert "content" not in prev["https://example.com/b"]

    def test_enclosure_is_read_back(self, tmp_path):
        path = write_feed(
            tmp_path,
            """<?xml version="1.0" encoding="UTF-8"?>
            <rss version="2.0"><channel>
              <item>
                <title>With media</title>
                <link>https://example.com/news</link>
                <description>x</description>
                <enclosure url="https://cdn.example.com/video.mp4"
                           length="12345" type="video/mp4"/>
              </item>
            </channel></rss>""",
        )
        prev = common.load_previous(path)
        assert prev["https://example.com/news"]["enclosure"] == {
            "url": "https://cdn.example.com/video.mp4",
            "length": 12345,
            "type": "video/mp4",
        }

    def test_without_enclosure_key_is_absent(self, tmp_path):
        path = write_feed(
            tmp_path,
            """<?xml version="1.0" encoding="UTF-8"?>
            <rss version="2.0"><channel>
              <item>
                <title>Plain</title>
                <link>https://example.com/b</link>
                <description>x</description>
              </item>
            </channel></rss>""",
        )
        prev = common.load_previous(path)
        assert "enclosure" not in prev["https://example.com/b"]

    def test_feed_with_xml_stylesheet_pi_round_trips(self, tmp_path):
        """The preview PI must not confuse feed parsing/merging."""
        path = write_feed(
            tmp_path,
            """<?xml version="1.0" encoding="UTF-8"?>
            <?xml-stylesheet type='text/xsl' href='feed-preview.xsl'?>
            <rss version="2.0"><channel>
              <item>
                <title>Styled</title>
                <link>https://example.com/a</link>
                <description>x</description>
              </item>
            </channel></rss>""",
        )
        prev = common.load_previous(path)
        assert set(prev) == {"https://example.com/a"}
        assert prev["https://example.com/a"]["title"] == "Styled"


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

    def test_cached_content_carries_over_to_new_item(self):
        old = self.prev_item(
            "https://example.com/old",
            "Same post",
            "https://example.com/page",
            datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        old["content"] = "<p>cached article</p>"
        new = self.new_item(
            "https://example.com/news#20260101-same-post",
            "Same post",
            "https://example.com/page",
            datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        merged = common.merge_items({"https://example.com/old": old}, [new])
        assert merged[new["id"]]["content"] == "<p>cached article</p>"

    def test_fresh_content_wins_over_cache(self):
        old = self.prev_item(
            "https://example.com/news#20260101-same-post",
            "Same post",
            "https://example.com/page",
            datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        old["content"] = "<p>cached</p>"
        new = self.new_item(
            "https://example.com/news#20260101-same-post",
            "Same post",
            "https://example.com/page",
            datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        new["content"] = "<p>fresh</p>"
        merged = common.merge_items({"https://example.com/news#20260101-same-post": old}, [new])
        assert merged[new["id"]]["content"] == "<p>fresh</p>"

    def test_stale_enclosure_carries_over_to_new_item(self):
        old = self.prev_item(
            "https://example.com/news#20260921-der-mochtegernekanzler",
            "Der Möchtegernekanzler",
            "https://cdn.example.com/old-signed-video.mp4?Expires=1",
            datetime(2026, 9, 21, tzinfo=timezone.utc),
        )
        old["enclosure"] = {
            "url": "https://cdn.example.com/old-signed-video.mp4?Expires=1",
            "length": 0,
            "type": "video/mp4",
        }
        new = self.new_item(
            "https://example.com/news#20260921-der-mochtegernekanzler",
            "Der Möchtegernekanzler",
            "https://www.klum.com/news",
            datetime(2026, 9, 21, tzinfo=timezone.utc),
        )
        merged = common.merge_items(
            {"https://example.com/news#20260921-der-mochtegernekanzler": old}, [new]
        )
        assert merged[new["id"]]["enclosure"]["url"] == old["enclosure"]["url"]

    def test_fresh_enclosure_wins_over_stale(self):
        item_id = "https://example.com/news#20260921-der-mochtegernekanzler"
        old = self.prev_item(
            item_id,
            "Der Möchtegernekanzler",
            "https://cdn.example.com/old.mp4?Expires=1",
            datetime(2026, 9, 21, tzinfo=timezone.utc),
        )
        old["enclosure"] = {
            "url": "https://cdn.example.com/old.mp4?Expires=1",
            "length": 0,
            "type": "video/mp4",
        }
        new = self.new_item(
            item_id,
            "Der Möchtegernekanzler",
            "https://cdn.example.com/fresh.mp4?Expires=2",
            datetime(2026, 9, 21, tzinfo=timezone.utc),
        )
        new["enclosure"] = {
            "url": "https://cdn.example.com/fresh.mp4?Expires=2",
            "length": 99,
            "type": "video/mp4",
        }
        merged = common.merge_items({item_id: old}, [new])
        assert merged[item_id]["enclosure"]["url"] == new["enclosure"]["url"]


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

    def test_xml_stylesheet_pi_directly_after_xml_declaration(self):
        """Firefox applies the XSLT preview to locally opened feed files."""
        xml = common.build_feed(
            [],
            feed_id="https://example.com/",
            title="T",
            link="https://example.com/",
            description="d",
            language="en",
        ).decode("utf-8")
        lines = xml.splitlines()
        assert lines[0].startswith("<?xml")
        assert lines[1] == (
            "<?xml-stylesheet type='text/xsl' href='feed-preview.xsl'?>"
        )

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

    def test_writes_content_encoded(self):
        items = [
            {
                "id": "https://example.com/a",
                "title": "With content",
                "link": "https://example.com/a",
                "description": "short",
                "published": datetime(2026, 1, 1, tzinfo=timezone.utc),
                "content": "<p>full text</p>",
            },
            {
                "id": "https://example.com/b",
                "title": "Without content",
                "link": "https://example.com/b",
                "description": "",
                "published": None,
            },
        ]
        xml = common.build_feed(
            items,
            feed_id="https://example.com/",
            title="T",
            link="https://example.com/",
            description="d",
            language="en",
        ).decode("utf-8")
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(xml, "xml")
        encoded = soup.find_all("content:encoded")
        assert len(encoded) == 1
        # readers unescape the XML and render the value as HTML
        assert encoded[0].get_text() == "<p>full text</p>"

    def test_writes_enclosure(self):
        items = [
            {
                "id": "https://example.com/a",
                "title": "With media",
                "link": "https://example.com/a",
                "description": "",
                "published": datetime(2026, 9, 21, tzinfo=timezone.utc),
                "enclosure": {
                    "url": "https://cdn.example.com/video.mp4?Expires=1",
                    "length": 12345,
                    "type": "video/mp4",
                },
            },
            {
                "id": "https://example.com/b",
                "title": "Without media",
                "link": "https://example.com/b",
                "description": "",
                "published": None,
            },
        ]
        xml = common.build_feed(
            items,
            feed_id="https://example.com/",
            title="T",
            link="https://example.com/",
            description="d",
            language="en",
        ).decode("utf-8")
        assert (
            '<enclosure url="https://cdn.example.com/video.mp4?Expires=1" '
            'length="12345" type="video/mp4"/>'
        ) in xml
        assert xml.count("<enclosure") == 1


class TestBuildFeedItunes:
    def items(self, image=None):
        return [
            {
                "id": "https://example.com/a",
                "title": "An entry",
                "link": "https://example.com/a",
                "description": "text",
                "published": datetime(2025, 9, 1, 10, 0, tzinfo=timezone.utc),
                "image": image,
            }
        ]

    def test_itunes_channel_tags(self):
        xml = common.build_feed(
            self.items(),
            feed_id="https://example.com/",
            title="T",
            link="https://example.com/",
            description="d",
            language="de",
            itunes_author="BRF1",
            itunes_summary="Show summary",
            itunes_image="https://example.com/cover.jpg",
            itunes_category="Music",
            itunes_explicit="no",
        ).decode("utf-8")
        assert "<itunes:author>BRF1</itunes:author>" in xml
        assert "<itunes:summary>Show summary</itunes:summary>" in xml
        assert (
            '<itunes:image href="https://example.com/cover.jpg"/>' in xml
        )
        assert '<itunes:category text="Music"/>' in xml
        assert "<itunes:explicit>no</itunes:explicit>" in xml

    def test_itunes_entry_image(self):
        xml = common.build_feed(
            self.items(image="https://example.com/ep.jpg"),
            feed_id="https://example.com/",
            title="T",
            link="https://example.com/",
            description="d",
            language="de",
        ).decode("utf-8")
        assert '<itunes:image href="https://example.com/ep.jpg"/>' in xml

    def test_without_itunes_metadata_no_itunes_namespace(self):
        xml = common.build_feed(
            self.items(),
            feed_id="https://example.com/",
            title="T",
            link="https://example.com/",
            description="d",
            language="de",
        ).decode("utf-8")
        assert "itunes:" not in xml

    def test_item_without_image_key_is_accepted(self):
        xml = common.build_feed(
            [
                {
                    "id": "https://example.com/a",
                    "title": "An entry",
                    "link": "https://example.com/a",
                    "description": "text",
                    "published": None,
                }
            ],
            feed_id="https://example.com/",
            title="T",
            link="https://example.com/",
            description="d",
            language="de",
        ).decode("utf-8")
        assert "<item>" in xml


class TestBuildWarningItem:
    def test_item_fields(self):
        try:
            raise RuntimeError("boom")
        except RuntimeError as exc:
            item = common.build_warning_item("https://example.com/source/", exc)
        assert item["id"] == "https://example.com/source/#build-status"
        assert item["title"] == "Feed build failed"
        assert item["link"] == "https://example.com/source/"
        assert item["description"] == "boom"
        assert item["published"].tzinfo is not None

    def test_content_contains_traceback(self):
        try:
            raise RuntimeError("boom")
        except RuntimeError as exc:
            item = common.build_warning_item("https://example.com/s/", exc)
        assert "Traceback (most recent call last)" in item["content"]
        assert "RuntimeError: boom" in item["content"]

    def test_content_escapes_html(self):
        try:
            raise RuntimeError("<script>alert(1)</script>")
        except RuntimeError as exc:
            item = common.build_warning_item("https://example.com/s/", exc)
        assert "<script>" not in item["content"]
        assert "&lt;script&gt;" in item["content"]

    def test_works_outside_except_block(self):
        exc = ValueError("no active handler")
        item = common.build_warning_item("https://example.com/s/", exc)
        assert item["description"] == "no active handler"
        assert "ValueError" in item["content"]


class TestWithoutWarning:
    def test_drops_build_status_entries(self):
        previous = {
            "https://example.com/a": {"id": "https://example.com/a"},
            "https://example.com/a#build-status": {
                "id": "https://example.com/a#build-status"
            },
        }
        assert set(common.without_warning(previous)) == {"https://example.com/a"}

    def test_keeps_link_containing_hash(self):
        previous = {
            "https://example.com/a#build": {"id": "https://example.com/a#build"},
        }
        assert set(common.without_warning(previous)) == {"https://example.com/a#build"}


class TestWriteWarningFeed:
    def kwargs(self):
        return dict(
            feed_id="https://example.com/source/",
            title="Example feed",
            link="https://example.com/source/",
            description="An example feed",
            language="en",
        )

    def test_writes_previous_items_plus_warning_and_returns_zero(self, tmp_path, capsys):
        out = str(tmp_path / "feed.xml")
        previous_path = write_feed(
            tmp_path,
            """<?xml version="1.0" encoding="UTF-8"?>
            <rss version="2.0"><channel>
              <item>
                <title>Old post</title>
                <link>https://example.com/a</link>
                <description>hi</description>
                <pubDate>Mon, 01 Sep 2025 10:00:00 GMT</pubDate>
              </item>
            </channel></rss>""",
        )
        previous = common.load_previous(previous_path)
        common.write_feed(
            list(previous.values()), out, 100, **self.kwargs()
        )
        common.write_warning_feed(
            out, 100, "https://example.com/source/", RuntimeError("boom"), **self.kwargs()
        )
        assert capsys.readouterr().out.count("::warning::") == 1
        items = common.load_previous(out)
        assert set(items) == {
            "https://example.com/a",
            "https://example.com/source/#build-status",
        }
        warning = items["https://example.com/source/#build-status"]
        assert warning["title"] == "Feed build failed"
        assert warning["description"] == "boom"

    def test_works_without_previous_feed(self, tmp_path):
        out = str(tmp_path / "fresh.xml")
        rc = common.write_warning_feed(
            out, 100, "https://example.com/source/", RuntimeError("boom"), **self.kwargs()
        )
        assert rc == 0
        items = common.load_previous(out)
        assert set(items) == {"https://example.com/source/#build-status"}

    def test_annotation_is_single_line(self, tmp_path, capsys):
        out = str(tmp_path / "feed.xml")
        common.write_warning_feed(
            out, 100, "https://example.com/source/",
            RuntimeError("line one\nline two"), **self.kwargs(),
        )
        out_text = capsys.readouterr().out
        warning_line = next(l for l in out_text.splitlines() if "::warning::" in l)
        assert "line one line two" in warning_line

    def test_repeated_failure_keeps_single_warning(self, tmp_path):
        out = str(tmp_path / "feed.xml")
        common.write_warning_feed(
            out, 100, "https://example.com/source/", RuntimeError("first"), **self.kwargs()
        )
        common.write_warning_feed(
            out, 100, "https://example.com/source/", RuntimeError("second"), **self.kwargs()
        )
        items = common.load_previous(out)
        assert set(items) == {"https://example.com/source/#build-status"}
        assert items["https://example.com/source/#build-status"]["description"] == "second"
