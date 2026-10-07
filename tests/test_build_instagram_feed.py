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


class TestFailureWarning:
    """Soft failures must end up as an item inside the feed, exit 0."""

    @staticmethod
    def _fail_fetch(monkeypatch, message="direct fetch exploded"):
        def boom(*args, **kwargs):
            raise RuntimeError(message)

        monkeypatch.setattr(build_instagram_feed.common, "fetch_page", boom)

    def test_fetch_failure_writes_warning_feed_and_exits_zero(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.delenv("INSTAGRAM_PROFILE_HTML", raising=False)
        self._fail_fetch(monkeypatch)
        monkeypatch.setattr(build_instagram_feed, "FEEDS_DIR", str(tmp_path))
        assert build_instagram_feed.main(["tiny_ruins"]) == 0

        xml = (tmp_path / "instagram-tiny_ruins.xml").read_text(encoding="utf-8")
        assert "<title>Feed build failed</title>" in xml
        assert "direct fetch exploded" in xml
        assert "Traceback (most recent call last)" in xml
        assert "<pubDate>" in xml

    def test_jina_fallback_failure_writes_warning_feed(self, tmp_path, monkeypatch):
        monkeypatch.delenv("INSTAGRAM_PROFILE_HTML", raising=False)
        monkeypatch.setattr(
            build_instagram_feed.common,
            "fetch_page",
            lambda *a, **k: ("<html>login wall</html>", "direct"),
        )

        def boom(url):
            raise RuntimeError("jina exploded")

        monkeypatch.setattr(build_instagram_feed.common, "fetch_jina", boom)
        monkeypatch.setattr(build_instagram_feed, "FEEDS_DIR", str(tmp_path))
        assert build_instagram_feed.main(["tiny_ruins"]) == 0

        xml = (tmp_path / "instagram-tiny_ruins.xml").read_text(encoding="utf-8")
        assert "<title>Feed build failed</title>" in xml
        assert "jina exploded" in xml

    def test_repeated_failure_replaces_warning_entry(self, tmp_path, monkeypatch):
        monkeypatch.delenv("INSTAGRAM_PROFILE_HTML", raising=False)
        self._fail_fetch(monkeypatch)
        monkeypatch.setattr(build_instagram_feed, "FEEDS_DIR", str(tmp_path))
        assert build_instagram_feed.main(["tiny_ruins"]) == 0
        assert build_instagram_feed.main(["tiny_ruins"]) == 0

        xml = (tmp_path / "instagram-tiny_ruins.xml").read_text(encoding="utf-8")
        assert xml.count("<item>") == 1
        assert xml.count("Feed build failed") == 1

    def test_failure_keeps_previous_items(self, tmp_path, monkeypatch):
        monkeypatch.setenv("INSTAGRAM_PROFILE_HTML", FIXTURE)
        monkeypatch.setattr(build_instagram_feed, "FEEDS_DIR", str(tmp_path))
        assert build_instagram_feed.main(["tiny_ruins"]) == 0

        monkeypatch.delenv("INSTAGRAM_PROFILE_HTML")
        self._fail_fetch(monkeypatch)
        assert build_instagram_feed.main(["tiny_ruins"]) == 0

        xml = (tmp_path / "instagram-tiny_ruins.xml").read_text(encoding="utf-8")
        assert xml.count("<item>") == 13
        assert "<title>Feed build failed</title>" in xml

    def test_success_removes_stale_warning(self, tmp_path, monkeypatch):
        common_mod = build_instagram_feed.common
        real_fetch_page = common_mod.fetch_page
        monkeypatch.delenv("INSTAGRAM_PROFILE_HTML", raising=False)
        self._fail_fetch(monkeypatch)
        monkeypatch.setattr(build_instagram_feed, "FEEDS_DIR", str(tmp_path))
        assert build_instagram_feed.main(["tiny_ruins"]) == 0

        monkeypatch.setattr(common_mod, "fetch_page", real_fetch_page)
        monkeypatch.setenv("INSTAGRAM_PROFILE_HTML", FIXTURE)
        assert build_instagram_feed.main(["tiny_ruins"]) == 0

        xml = (tmp_path / "instagram-tiny_ruins.xml").read_text(encoding="utf-8")
        assert xml.count("<item>") == 12
        assert "Feed build failed" not in xml

    def test_unparseable_page_writes_warning_feed(self, tmp_path, monkeypatch):
        monkeypatch.setenv("INSTAGRAM_PROFILE_HTML", "<html>login wall</html>")
        monkeypatch.setattr(build_instagram_feed, "FEEDS_DIR", str(tmp_path))
        assert build_instagram_feed.main(["tiny_ruins"]) == 0

        xml = (tmp_path / "instagram-tiny_ruins.xml").read_text(encoding="utf-8")
        assert "<title>Feed build failed</title>" in xml
        assert xml.count("<item>") == 1

    def test_warning_feed_keeps_previous_metadata(self, tmp_path, monkeypatch):
        monkeypatch.setenv("INSTAGRAM_PROFILE_HTML", FIXTURE)
        monkeypatch.setattr(build_instagram_feed, "FEEDS_DIR", str(tmp_path))
        assert build_instagram_feed.main(["tiny_ruins"]) == 0

        monkeypatch.delenv("INSTAGRAM_PROFILE_HTML")
        self._fail_fetch(monkeypatch)
        assert build_instagram_feed.main(["tiny_ruins"]) == 0

        xml = (tmp_path / "instagram-tiny_ruins.xml").read_text(encoding="utf-8")
        assert "<title>Tiny Ruins on Instagram</title>" in xml


class _FakeResponse:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        pass


class TestSessionCookieFallback:
    """INSTAGRAM_SESSIONID retry when the anonymous fetch hits a login wall."""

    JINA_HTML = '<a href="https://www.instagram.com/p/AbCdEf123/">fallback</a>'

    @staticmethod
    def _login_wall_fetch(monkeypatch):
        monkeypatch.setattr(
            build_instagram_feed.common,
            "fetch_page",
            lambda *a, **k: ("<html>login wall</html>", "direct"),
        )

    @staticmethod
    def _mock_creq_get(monkeypatch, cookie_html, anonymous_ok=False):
        """creq.get returns cookie_html when a sessionid cookie is present."""

        def fake_get(url, **kwargs):
            if kwargs.get("cookies", {}).get("sessionid"):
                return _FakeResponse(cookie_html)
            assert anonymous_ok, "unexpected anonymous direct fetch"
            return _FakeResponse("<html>login wall</html>")

        monkeypatch.setattr(build_instagram_feed.common.creq, "get", fake_get)

    def test_fetch_with_session_passes_cookie(self, monkeypatch):
        captured = {}

        def fake_get(url, **kwargs):
            captured.update(kwargs)
            return _FakeResponse("session page")

        monkeypatch.setattr(build_instagram_feed.common.creq, "get", fake_get)
        monkeypatch.setenv("INSTAGRAM_SESSIONID", "s3cret")

        url = build_instagram_feed.instagram_url("tiny_ruins")
        assert build_instagram_feed.fetch_with_session(url) == "session page"
        assert captured["cookies"] == {"sessionid": "s3cret"}

    def test_fetch_with_session_none_without_env(self, monkeypatch):
        monkeypatch.delenv("INSTAGRAM_SESSIONID", raising=False)

        def boom(url, **kwargs):
            raise AssertionError("must not fetch without a session id")

        monkeypatch.setattr(build_instagram_feed.common.creq, "get", boom)
        assert build_instagram_feed.fetch_with_session("https://x/") is None

    def test_login_wall_retries_with_session_cookie(self, tmp_path, monkeypatch):
        monkeypatch.delenv("INSTAGRAM_PROFILE_HTML", raising=False)
        self._login_wall_fetch(monkeypatch)
        with open(FIXTURE, encoding="utf-8") as f:
            self._mock_creq_get(monkeypatch, f.read())
        monkeypatch.setenv("INSTAGRAM_SESSIONID", "s3cret")
        monkeypatch.setattr(build_instagram_feed, "FEEDS_DIR", str(tmp_path))

        assert build_instagram_feed.main(["tiny_ruins"]) == 0

        xml = (tmp_path / "instagram-tiny_ruins.xml").read_text(encoding="utf-8")
        assert xml.count("<item>") == 12
        assert "Feed build failed" not in xml

    def test_session_retry_failure_falls_through_to_jina(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.delenv("INSTAGRAM_PROFILE_HTML", raising=False)
        self._login_wall_fetch(monkeypatch)
        self._mock_creq_get(monkeypatch, "<html>still login wall</html>")
        monkeypatch.setenv("INSTAGRAM_SESSIONID", "s3cret")
        monkeypatch.setattr(
            build_instagram_feed.common,
            "fetch_jina",
            lambda url: self.JINA_HTML,
        )
        monkeypatch.setattr(build_instagram_feed, "FEEDS_DIR", str(tmp_path))

        assert build_instagram_feed.main(["tiny_ruins"]) == 0

        xml = (tmp_path / "instagram-tiny_ruins.xml").read_text(encoding="utf-8")
        assert xml.count("<item>") == 1
        assert "Feed build failed" not in xml

    def test_no_cookie_skips_session_retry(self, tmp_path, monkeypatch):
        monkeypatch.delenv("INSTAGRAM_PROFILE_HTML", raising=False)
        monkeypatch.delenv("INSTAGRAM_SESSIONID", raising=False)
        self._login_wall_fetch(monkeypatch)
        self._mock_creq_get(monkeypatch, "<html>unused</html>", anonymous_ok=False)
        monkeypatch.setattr(
            build_instagram_feed.common,
            "fetch_jina",
            lambda url: self.JINA_HTML,
        )
        monkeypatch.setattr(build_instagram_feed, "FEEDS_DIR", str(tmp_path))

        assert build_instagram_feed.main(["tiny_ruins"]) == 0

        xml = (tmp_path / "instagram-tiny_ruins.xml").read_text(encoding="utf-8")
        assert xml.count("<item>") == 1

    def test_offline_run_skips_session_retry(self, tmp_path, monkeypatch):
        monkeypatch.setenv("INSTAGRAM_PROFILE_HTML", "<html>login wall</html>")
        monkeypatch.setenv("INSTAGRAM_SESSIONID", "s3cret")

        def boom(url, **kwargs):
            raise AssertionError("offline mode must not fetch")

        monkeypatch.setattr(build_instagram_feed.common.creq, "get", boom)
        monkeypatch.setattr(build_instagram_feed, "FEEDS_DIR", str(tmp_path))
        assert build_instagram_feed.main(["tiny_ruins"]) == 0

        xml = (tmp_path / "instagram-tiny_ruins.xml").read_text(encoding="utf-8")
        assert "<title>Feed build failed</title>" in xml
