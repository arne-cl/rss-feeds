"""Tests for the Instagram feed builder."""

import html as html_mod
import json
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


API_FIXTURE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "fixtures",
    "instagram-tiny-ruins-api.json",
)
TIMELINE_FIXTURE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "fixtures",
    "instagram-tiny-ruins-timeline.json",
)


class TestParseApi:
    """web_profile_info JSON (INSTAGRAM_SESSIONID fallback channel)."""

    @staticmethod
    def parse_api_fixture():
        with open(API_FIXTURE, encoding="utf-8") as f:
            return build_instagram_feed.parse_api(f.read())

    def test_items_from_edge_nodes(self):
        items = self.parse_api_fixture()
        assert [i["link"] for i in items] == [
            "https://www.instagram.com/p/DdoYr2_CY-5/",
            "https://www.instagram.com/p/C0lI6pOrWJH/",
            "https://www.instagram.com/p/EmptyCap1/",
        ]
        assert all(i["id"] == i["link"] for i in items)

    def test_caption_title_description_date(self):
        item = self.parse_api_fixture()[0]
        assert item["title"] == "TOTD 67 - Museum"
        assert item["published"] == datetime(2026, 9, 23, 5, 0, tzinfo=timezone.utc)
        assert item["description"].startswith("TOTD 67 - Museum")
        assert "Bella Union" in item["description"]

    def test_image_enclosure(self):
        item = self.parse_api_fixture()[0]
        assert item["enclosure"]["url"].endswith("fixtures_image_654x654.jpg")
        assert item["enclosure"]["type"] == "image/jpeg"
        assert '<img src="https://scontent' in item["content"]

    def test_video_prefers_video_url(self):
        item = self.parse_api_fixture()[1]
        assert item["enclosure"]["url"].endswith("fixtures_video.mp4")
        assert item["enclosure"]["type"] == "video/mp4"

    def test_empty_caption_falls_back_to_media_kind(self):
        item = self.parse_api_fixture()[2]
        assert item["title"] == "Post EmptyCap1"
        assert item["published"] == datetime(2023, 11, 3, 8, 26, 40, tzinfo=timezone.utc)

    def test_tolerates_xdt_node_shape(self):
        raw = json.dumps(
            {
                "data": {
                    "user": {
                        "edge_owner_to_timeline_media": {
                            "edges": [
                                {
                                    "node": {
                                        "code": "XdtCoDe123",
                                        "taken_at": 1758601200,
                                        "caption": {"text": "xdt style caption"},
                                        "image_versions2": {
                                            "candidates": [{"url": "https://cdn/x.jpg"}]
                                        },
                                    }
                                }
                            ]
                        }
                    }
                }
            }
        )
        items = build_instagram_feed.parse_api(raw)
        assert len(items) == 1
        assert items[0]["link"] == "https://www.instagram.com/p/XdtCoDe123/"
        assert items[0]["title"] == "xdt style caption"
        assert items[0]["enclosure"]["url"] == "https://cdn/x.jpg"

    def test_garbage_and_empty(self):
        assert build_instagram_feed.parse_api("<html>rate limited</html>") == []
        assert build_instagram_feed.parse_api('{"data": {"user": null}}') == []
        assert build_instagram_feed.parse_api("{}") == []


class TestParseTimeline:
    """Real captured /api/graphql timeline shape (xdt nodes)."""

    @staticmethod
    def parse_timeline_fixture():
        with open(TIMELINE_FIXTURE, encoding="utf-8") as f:
            return build_instagram_feed.parse_api(f.read())

    def test_three_posts_from_timeline_connection(self):
        items = self.parse_timeline_fixture()
        assert [i["link"] for i in items] == [
            "https://www.instagram.com/p/CrktkZ_rqou/",
            "https://www.instagram.com/p/DVjUvmekdgi/",
            "https://www.instagram.com/p/DE7NBK1yhhx/",
        ]

    def test_carousel_item(self):
        item = self.parse_timeline_fixture()[0]
        assert item["title"].startswith("\u2018Ceremony\u2019 - she\u2019s here!")
        assert item["enclosure"]["type"] == "image/jpeg"
        assert item["enclosure"]["url"].startswith("https://scontent")

    def test_video_item_uses_video_version(self):
        item = self.parse_timeline_fixture()[1]
        assert item["enclosure"]["type"] == "video/mp4"
        assert "video" in item["enclosure"]["url"] or "scontent" in item["enclosure"]["url"]

    def test_dates_are_taken_at_utc(self):
        items = self.parse_timeline_fixture()
        assert items[0]["published"] == datetime(2023, 4, 28, 8, 46, 16, tzinfo=timezone.utc)
        assert all(i["published"] is not None for i in items)


class TestCarouselSlides:
    """Carousel posts (media_type 8) must embed every slide, not just the cover."""

    @staticmethod
    def timeline_item(code):
        with open(TIMELINE_FIXTURE, encoding="utf-8") as f:
            items = build_instagram_feed.parse_api(f.read())
        return next(i for i in items if i["link"].endswith(f"/p/{code}/"))

    @staticmethod
    def api_json(node):
        return json.dumps(
            {"data": {"user": {"edge_owner_to_timeline_media": {"edges": [{"node": node}]}}}}
        )

    def test_carousel_embeds_all_slides(self):
        item = self.timeline_item("CrktkZ_rqou")
        assert item["content"].count("<img ") == 2
        assert "661088717_18178614697382086_4411761568083933789" in item["content"]
        assert "650715470_18035675546783978_3577839567541904417" in item["content"]

    def test_carousel_enclosure_is_first_slide(self):
        item = self.timeline_item("CrktkZ_rqou")
        assert "661088717_18178614697382086_4411761568083933789" in item["enclosure"]["url"]
        assert item["enclosure"]["type"] == "image/jpeg"

    def test_sidecar_children_embedded(self):
        raw = self.api_json(
            {
                "shortcode": "SideCar12",
                "taken_at_timestamp": 1700000000,
                "caption": {"text": "sidecar post"},
                "edge_sidecar_to_children": {
                    "edges": [
                        {
                            "node": {
                                "display_url": "https://cdn/slide1.jpg",
                                "accessibility_caption": "first slide",
                            }
                        },
                        {"node": {"display_url": "https://cdn/slide2.jpg"}},
                    ]
                },
            }
        )
        (item,) = build_instagram_feed.parse_api(raw)
        assert item["content"].count("<img ") == 2
        assert 'alt="first slide"' in item["content"]
        assert '<img src="https://cdn/slide1.jpg"' in item["content"]
        assert '<img src="https://cdn/slide2.jpg"' in item["content"]
        assert item["enclosure"]["url"] == "https://cdn/slide1.jpg"

    def test_sidecar_video_slide_poster_then_video(self):
        raw = self.api_json(
            {
                "shortcode": "CarViDeo1",
                "taken_at_timestamp": 1700000000,
                "caption": {"text": "mixed media"},
                "edge_sidecar_to_children": {
                    "edges": [
                        {
                            "node": {
                                "display_url": "https://cdn/poster.jpg",
                                "video_url": "https://cdn/clip.mp4",
                            }
                        },
                        {"node": {"display_url": "https://cdn/slide2.jpg"}},
                    ]
                },
            }
        )
        (item,) = build_instagram_feed.parse_api(raw)
        content = item["content"]
        assert '<img src="https://cdn/poster.jpg"' in content
        assert '<video controls preload="none" src="https://cdn/clip.mp4">' in content
        assert content.index("<img ") < content.index("<video ")
        assert content.index("<video ") < content.index("slide2.jpg")
        assert item["enclosure"]["url"] == "https://cdn/clip.mp4"
        assert item["enclosure"]["type"] == "video/mp4"

    def test_video_post_embeds_poster_then_video_tag(self):
        item = self.timeline_item("DVjUvmekdgi")
        content = item["content"]
        assert content.startswith("<img ")
        assert "626277993_1338277208336461_" in content
        assert '<video controls preload="none" src="https://scontent' in content
        assert item["enclosure"]["type"] == "video/mp4"

    def test_video_slide_via_xdt_carousel_media(self):
        raw = self.api_json(
            {
                "code": "XdtCarVid1",
                "taken_at": 1700000000,
                "caption": {"text": "xdt mixed carousel"},
                "carousel_media": [
                    {
                        "media_type": 2,
                        "video_versions": [{"url": "https://cdn/clip2.mp4"}],
                        "image_versions2": {"candidates": [{"url": "https://cdn/poster2.jpg"}]},
                    },
                    {
                        "media_type": 1,
                        "image_versions2": {"candidates": [{"url": "https://cdn/slideB.jpg"}]},
                    },
                ],
            }
        )
        (item,) = build_instagram_feed.parse_api(raw)
        content = item["content"]
        assert content.count("<img ") == 2
        assert '<video controls preload="none" src="https://cdn/clip2.mp4">' in content
        assert item["enclosure"]["url"] == "https://cdn/clip2.mp4"

    def test_direct_parse_video_post_keeps_poster_image(self):
        with open(FIXTURE, encoding="utf-8") as f:
            items = build_instagram_feed.parse_direct(f.read())
        (item,) = [i for i in items if i["link"].endswith("/p/DBfhEU2uKqN/")]
        assert item["content"].startswith("<img ")
        assert "<video" not in item["content"]

    def test_direct_parse_embeds_children_when_present(self):
        html = (
            '<script type="application/json">'
            '{"data": {"node": {"__isXIGPolarisMedia": "XIGPolarisCarouselMedia",'
            ' "code": "DirCar123", "media_type": 8, "display_uri": "https://cdn/cover.jpg",'
            ' "carousel_media": ['
            '{"display_uri": "https://cdn/s1.jpg", "accessibility_caption": "one"},'
            '{"display_uri": "https://cdn/s2.jpg"}]}}}'
            "</script>"
        )
        (item,) = build_instagram_feed.parse_direct(html)
        assert item["content"].count("<img ") == 2
        assert '<img src="https://cdn/s1.jpg" alt="one" />' in item["content"]
        assert '<img src="https://cdn/s2.jpg"' in item["content"]
        assert item["enclosure"]["url"] == "https://cdn/s1.jpg"


class TestSessionApiFallback:
    """INSTAGRAM_SESSIONID retry via the web_profile_info API."""

    JINA_HTML = '<a href="https://www.instagram.com/p/AbCdEf123/">fallback</a>'

    @staticmethod
    def _login_wall_fetch(monkeypatch):
        monkeypatch.setattr(
            build_instagram_feed.common,
            "fetch_page",
            lambda *a, **k: ("<html>login wall</html>", "direct"),
        )

    @staticmethod
    def _mock_creq_get(monkeypatch, captured=None):
        def fake_get(url, **kwargs):
            if captured is not None:
                captured.update(url=url, **kwargs)
            if kwargs.get("cookies", {}).get("sessionid"):
                with open(API_FIXTURE, encoding="utf-8") as f:
                    return _FakeResponse(f.read())
            raise AssertionError("unexpected anonymous direct fetch")

        monkeypatch.setattr(build_instagram_feed.common.creq, "get", fake_get)

    def test_fetch_api_profile_passes_cookie_and_header(self, monkeypatch):
        captured = {}
        self._mock_creq_get(monkeypatch, captured)
        monkeypatch.setenv("INSTAGRAM_SESSIONID", "s3cret")

        text = build_instagram_feed.fetch_api_profile("tiny_ruins")
        assert "TOTD 67 - Museum" in text
        assert (
            captured["url"]
            == "https://www.instagram.com/api/v1/users/web_profile_info/"
            "?username=tiny_ruins"
        )
        assert captured["cookies"] == {"sessionid": "s3cret"}
        assert captured["headers"]["x-ig-app-id"]

    def test_fetch_api_profile_none_without_env(self, monkeypatch):
        monkeypatch.delenv("INSTAGRAM_SESSIONID", raising=False)

        def boom(url, **kwargs):
            raise AssertionError("must not fetch without a session id")

        monkeypatch.setattr(build_instagram_feed.common.creq, "get", boom)
        assert build_instagram_feed.fetch_api_profile("tiny_ruins") is None

    def test_login_wall_retries_with_session_api(self, tmp_path, monkeypatch):
        monkeypatch.delenv("INSTAGRAM_PROFILE_HTML", raising=False)
        self._login_wall_fetch(monkeypatch)
        self._mock_creq_get(monkeypatch)
        monkeypatch.setenv("INSTAGRAM_SESSIONID", "s3cret")
        monkeypatch.setattr(build_instagram_feed, "FEEDS_DIR", str(tmp_path))

        assert build_instagram_feed.main(["tiny_ruins"]) == 0

        xml = (tmp_path / "instagram-tiny_ruins.xml").read_text(encoding="utf-8")
        assert xml.count("<item>") == 3
        assert "Feed build failed" not in xml
        assert "<title>tiny_ruins on Instagram</title>" in xml

    def test_api_failure_falls_through_to_jina(self, tmp_path, monkeypatch):
        monkeypatch.delenv("INSTAGRAM_PROFILE_HTML", raising=False)
        self._login_wall_fetch(monkeypatch)

        def boom(url, **kwargs):
            raise RuntimeError("429 too many requests")

        monkeypatch.setattr(build_instagram_feed.common.creq, "get", boom)
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

        def boom(url, **kwargs):
            raise AssertionError("must not retry anonymously")

        monkeypatch.setattr(build_instagram_feed.common.creq, "get", boom)
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
