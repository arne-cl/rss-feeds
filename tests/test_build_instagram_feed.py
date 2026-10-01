"""Tests for the Instagram feed builder."""

import html as html_mod
import os
from datetime import datetime, timezone

import pytest

import build_instagram_feed

FIXTURE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "fixtures", "instagram-tiny-ruins.html"
)


def parse_fixture():
    with open(FIXTURE, encoding="utf-8") as f:
        return build_instagram_feed.parse_direct(f.read())


def by_code(items, code):
    return [i for i in items if i["link"].endswith(f"/p/{code}/")]


class TestParseDirect:
    def test_parses_all_twelve_fixture_posts(self):
        assert len(parse_fixture()) == 12

    def test_item_shape(self):
        for item in parse_fixture():
            assert {"id", "title", "link", "description", "published"} <= set(item)
            assert set(item) <= {
                "id", "title", "link", "description", "published",
                "enclosure", "content",
            }
            assert item["title"]
            assert item["link"].startswith("http")

    def test_ids_are_unique_post_urls(self):
        items = parse_fixture()
        ids = [i["id"] for i in items]
        assert len(set(ids)) == len(ids)
        for item in items:
            assert item["id"] == item["link"]
            assert item["link"].startswith("https://www.instagram.com/p/")

    def test_newest_item(self):
        item = by_code(parse_fixture(), "DdoYr2_CY-5")[0]
        assert item["title"] == "TOTD 67 - Museum"
        assert item["published"] == datetime(2026, 9, 23, tzinfo=timezone.utc)
        assert item["description"].startswith("TOTD 67 - Museum")
        assert "youtu.be" in item["description"]
        assert item["enclosure"]["url"].startswith("https://scontent")
        assert item["enclosure"]["type"] == "image/jpeg"
        assert item["enclosure"]["length"] == 0

    def test_content_html_embeds_image_and_caption(self):
        item = by_code(parse_fixture(), "DdoYr2_CY-5")[0]
        assert item["content"].startswith("<img src=")
        assert html_mod.escape(item["enclosure"]["url"], quote=True) in item["content"]
        assert "youtu.be" in item["content"]

    def test_all_fixture_items_have_date_and_enclosure(self):
        for item in parse_fixture():
            assert item["published"] is not None
            assert item["published"].tzinfo == timezone.utc
            assert "enclosure" in item

    def test_older_photo_item(self):
        item = by_code(parse_fixture(), "C0lI6pOrWJH")[0]
        assert item["published"] == datetime(2023, 12, 7, tzinfo=timezone.utc)
        assert item["title"].startswith("Get along to this tomorrow")

    def test_empty_caption_falls_back_to_media_kind(self):
        html = (
            '<script type="application/json">'
            '{"data": {"node": {"__isXIGPolarisMedia": "XIGPolarisImageMedia",'
            ' "code": "AbCdEf1", "media_type": 1, "caption": null}}}'
            "</script>"
        )
        items = build_instagram_feed.parse_direct(html)
        assert [i["title"] for i in items] == ["Photo AbCdEf1"]
        assert items[0]["published"] is None
        assert items[0]["description"] == ""


class TestParseAccessibilityDate:
    def test_photo_caption(self):
        text = "Photo by Tiny Ruins on December 07, 2023."
        assert build_instagram_feed.parse_accessibility_date(text) == datetime(
            2023, 12, 7, tzinfo=timezone.utc
        )

    def test_video_caption_zero_padded_month(self):
        text = "Video by Ally Records on March 06, 2026."
        assert build_instagram_feed.parse_accessibility_date(text) == datetime(
            2026, 3, 6, tzinfo=timezone.utc
        )

    def test_missing_or_garbage(self):
        assert build_instagram_feed.parse_accessibility_date("") is None
        assert build_instagram_feed.parse_accessibility_date("no date here") is None
        assert build_instagram_feed.parse_accessibility_date(None) is None


class TestParseDom:
    def test_parses_post_links_with_alt_titles(self):
        html = """
        <a href="https://www.instagram.com/p/DdoYr2_CY-5/">
            <img alt="TOTD 67 - Museum" src="x.jpg">
        </a>
        <a href="https://www.instagram.com/p/DdoYr2_CY-5/">duplicate</a>
        <a href="https://www.instagram.com/explore/">not a post</a>
        """
        items = build_instagram_feed.parse_dom(html)
        assert len(items) == 1
        assert items[0]["link"] == "https://www.instagram.com/p/DdoYr2_CY-5/"
        assert items[0]["id"] == items[0]["link"]
        assert items[0]["title"] == "TOTD 67 - Museum"
        assert items[0]["published"] is None

    def test_title_fallback_without_alt_or_text(self):
        html = '<a href="https://www.instagram.com/p/AbCdEf1/"></a>'
        items = build_instagram_feed.parse_dom(html)
        assert items[0]["title"] == "Post AbCdEf1"


class TestProfileMetadata:
    def test_extracts_profile_fields(self):
        with open(FIXTURE, encoding="utf-8") as f:
            meta = build_instagram_feed.profile_metadata(f.read())
        assert meta["username"] == "tiny_ruins"
        assert meta["full_name"] == "Tiny Ruins"

    def test_empty_when_absent(self):
        assert build_instagram_feed.profile_metadata("<html></html>") == {}


class TestAccountConfig:
    def test_valid_accounts_normalized(self):
        assert build_instagram_feed.validate_account("tiny_ruins") == "tiny_ruins"
        assert build_instagram_feed.instagram_url("tiny_ruins") == (
            "https://www.instagram.com/tiny_ruins/"
        )

    def test_invalid_accounts_rejected(self):
        for bad in ("", "../etc/passwd", "a b", "x" * 31, None):
            with pytest.raises(ValueError):
                build_instagram_feed.validate_account(bad)

    def test_output_path_derived_from_account(self):
        path = build_instagram_feed.output_path("Tiny_Ruins")
        assert path.endswith(os.path.join("feeds", "instagram-tiny_ruins.xml"))


class TestMain:
    def test_offline_run_writes_feed(self, tmp_path, monkeypatch):
        monkeypatch.setenv("INSTAGRAM_PROFILE_HTML", FIXTURE)
        monkeypatch.setattr(build_instagram_feed, "FEEDS_DIR", str(tmp_path))
        assert build_instagram_feed.main(["tiny_ruins"]) == 0

        out = tmp_path / "instagram-tiny_ruins.xml"
        assert out.exists()
        xml = out.read_text(encoding="utf-8")
        assert xml.count("<item>") == 12
        assert "<title>Tiny Ruins on Instagram</title>" in xml
        assert "https://www.instagram.com/tiny_ruins/" in xml

    def test_invalid_account_fails_cleanly(self, tmp_path, monkeypatch):
        monkeypatch.setattr(build_instagram_feed, "FEEDS_DIR", str(tmp_path))
        assert build_instagram_feed.main(["../evil"]) == 2

    def test_unparseable_page_keeps_previous_feed(self, tmp_path, monkeypatch):
        monkeypatch.setenv("INSTAGRAM_PROFILE_HTML", "<html>login wall</html>")
        monkeypatch.setattr(build_instagram_feed, "FEEDS_DIR", str(tmp_path))
        assert build_instagram_feed.main(["tiny_ruins"]) == 1
