"""Tests for the rbb24 "Polen Update" video feed builder."""

import os
from datetime import datetime, timedelta, timezone

import build_rbb24_polen_update_feed
import common
from bs4 import BeautifulSoup

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
OVERVIEW = os.path.join(FIXTURES, "rbb24-polen-update.html")
PAGES = os.path.join(FIXTURES, "rbb24-polen-update-pages")
WISENT = os.path.join(PAGES, "video-polen-update-wisent-vorgarten-.html")
HOTEL = os.path.join(PAGES, "video-polen-update-mega-hotel-ostsee.html")
WISENT_LINK = (
    "https://www.rbb24.de/panorama/av/av24/"
    "video-polen-update-wisent-vorgarten-.html"
)
HOTEL_LINK = (
    "https://www.rbb24.de/panorama/polen-update/av24/"
    "video-polen-update-mega-hotel-ostsee.html"
)
CET = timezone(timedelta(hours=1))
CEST = timezone(timedelta(hours=2))


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def parse_overview_fixture():
    return build_rbb24_polen_update_feed.parse_overview(read(OVERVIEW))


def by_link(items, suffix):
    return [i for i in items if i["link"].endswith(suffix)]


class TestParseOverview:
    def test_all_polen_update_teasers_found(self):
        items = parse_overview_fixture()
        assert len(items) == 30

    def test_item_shape(self):
        for item in parse_overview_fixture():
            assert {"id", "title", "link", "description", "published", "image"} <= set(item)
            assert item["published"] is None
            assert item["title"]
            assert item["id"] == item["link"]
            assert item["link"].startswith("https://www.rbb24.de/")
            assert item["link"].endswith(".html")
            assert item["image"].startswith("https://")

    def test_ids_are_unique_absolute_links(self):
        items = parse_overview_fixture()
        links = [i["link"] for i in items]
        assert len(set(links)) == len(links)

    def test_lead_teaser(self):
        item = by_link(parse_overview_fixture(), "video-polen-update-wisent-vorgarten-.html")[0]
        assert item["title"] == "Plötzlich steht ein Wisent im Vorgarten"
        assert item["description"].startswith(
            "Wisente standen vor 100 Jahren kurz vor der Ausrottung."
        )
        assert item["description"].endswith(
            "an denen man sie nicht erwarten würde."
        )
        assert item["image"].endswith(
            "2026_10_30-PU-Wisent-2_16x9.jpg.jpg/quality=160/size=468x262.jpg"
        )

    def test_teaser_without_description_gets_title_fallback(self):
        item = by_link(parse_overview_fixture(), "video-polen-update-mega-hotel-ostsee.html")[0]
        assert item["title"] == "Mega-Hotel an der polnischen Ostsee"
        assert item["description"] == item["title"]

    def test_teaser_with_topic_roofline_kept(self):
        # roofline "Neue Bahnverbindungen" but polen URL on the series page
        item = by_link(
            parse_overview_fixture(),
            "video-berlin-brandenburg-polen-zuege-mehr-verbindungen.html",
        )
        assert len(item) == 1

    def test_non_polen_teaser_dropped(self):
        html = (
            "<html><body><main>"
            "<article class='teaser'>"
            "<div class='teaser__content-container'>"
            "<a class='teaser__text-container' href='/politik/x.html'>"
            "<span class='teaser__roofline'>Sport</span>"
            "<h2 class='teaser__title'>Fußball</h2></a>"
            "</div></article>"
            "</main></body></html>"
        )
        assert build_rbb24_polen_update_feed.parse_overview(html) == []

    def test_image_href_resolved_from_picture_fallback(self):
        item = by_link(parse_overview_fixture(), "video-polen-update-wisent-vorgarten-.html")[0]
        assert "/content/dam/rbb/" in item["image"]


class TestFeedCover:
    def test_og_image_meta(self):
        cover = build_rbb24_polen_update_feed.feed_cover(read(OVERVIEW))
        assert cover == (
            "https://www.rbb-online.de/content/dam/rbb/rbb/fernsehen/"
            "kowalski_und_schmidt/2020/07_2020/"
            "KOW_KOW-Making-of-Polen-update-uv_47702376__10-00-53-14.jpg.jpg/"
            "size=1280x720.jpg"
        )

    def test_no_cover(self):
        assert build_rbb24_polen_update_feed.feed_cover("<html></html>") is None


class TestParseVideoPage:
    def test_full_parse(self):
        data = build_rbb24_polen_update_feed.parse_video_page(read(WISENT))
        assert data["published"] == datetime(2026, 10, 30, 16, 48, 38, tzinfo=CET)
        assert data["description"].startswith(
            "Wisente standen vor 100 Jahren kurz vor der Ausrottung."
        )
        assert data["enclosure"]["url"] == (
            "https://rbb-progressive.ard-mcdn.de/content/f4/cf/"
            "f4cf5359-a9e2-4968-81ba-ff1be82b21aa/"
            "f4cf5359-a9e2-4968-81ba-ff1be82b21aa_9zu16-sm1280.mp4"
        )
        assert data["enclosure"]["type"] == "video/mp4"
        assert data["enclosure"]["length"] == 0
        assert data["image"].endswith("size=1280x720.jpg")

    def test_summer_time_offset(self):
        data = build_rbb24_polen_update_feed.parse_video_page(read(HOTEL))
        assert data["published"] == datetime(2026, 5, 29, 17, 34, 45, tzinfo=CEST)

    def test_page_without_video_json(self):
        data = build_rbb24_polen_update_feed.parse_video_page("<html></html>")
        assert data["published"] is None
        assert data["description"] == ""
        assert data["enclosure"] is None
        assert data["image"] is None


class TestEnrichItems:
    def test_attaches_data_from_saved_page(self, monkeypatch):
        monkeypatch.setenv("RBB24_POLEN_PAGES_DIR", PAGES)
        items = [
            {
                "id": WISENT_LINK,
                "title": "Plötzlich steht ein Wisent im Vorgarten",
                "link": WISENT_LINK,
                "description": "",
                "published": None,
                "image": "https://www.rbb24.de/x.jpg",
            }
        ]
        build_rbb24_polen_update_feed.enrich_items(items, {})
        assert items[0]["published"] == datetime(2026, 10, 30, 16, 48, 38, tzinfo=CET)
        assert items[0]["description"].startswith("Wisente standen")
        assert items[0]["enclosure"]["type"] == "video/mp4"

    def test_cached_items_are_not_refetched(self, monkeypatch):
        monkeypatch.delenv("RBB24_POLEN_PAGES_DIR", raising=False)
        items = [
            {
                "id": WISENT_LINK,
                "title": "Plötzlich steht ein Wisent im Vorgarten",
                "link": WISENT_LINK,
                "description": "",
                "published": None,
                "image": "https://www.rbb24.de/x.jpg",
            }
        ]
        old = {
            WISENT_LINK: {
                "id": WISENT_LINK,
                "title": "cached",
                "link": WISENT_LINK,
                "description": "cached description",
                "published": datetime(2026, 10, 30, 16, 48, 38, tzinfo=CET),
                "enclosure": {
                    "url": "https://rbb-progressive.ard-mcdn.de/x.mp4",
                    "type": "video/mp4",
                    "length": 42,
                },
            }
        }

        def fail_fetch(url):
            raise AssertionError(f"cached item must not be fetched: {url}")

        monkeypatch.setattr(
            build_rbb24_polen_update_feed, "fetch_video_page", fail_fetch
        )
        build_rbb24_polen_update_feed.enrich_items(items, old)
        assert items[0]["published"] == old[WISENT_LINK]["published"]
        assert items[0]["description"] == "cached description"
        assert items[0]["enclosure"]["length"] == 42

    def test_cached_description_and_image_are_restored(self, monkeypatch):
        monkeypatch.delenv("RBB24_POLEN_PAGES_DIR", raising=False)
        items = [
            {
                "id": WISENT_LINK,
                "title": "Plötzlich steht ein Wisent im Vorgarten",
                "link": WISENT_LINK,
                "description": "Plötzlich steht ein Wisent im Vorgarten",
                "published": None,
                "image": "https://www.rbb24.de/teaser-468x262.jpg",
            }
        ]
        old = {
            WISENT_LINK: {
                "id": WISENT_LINK,
                "title": "cached",
                "link": WISENT_LINK,
                "description": "full cached description",
                "published": datetime(2026, 10, 30, 16, 48, 38, tzinfo=CET),
                "image": "https://www.rbb-online.de/detail-1280x720.jpg",
                "enclosure": {
                    "url": "https://rbb-progressive.ard-mcdn.de/x.mp4",
                    "type": "video/mp4",
                    "length": 42,
                },
            }
        }

        def fail_fetch(url):
            raise AssertionError(f"cached item must not be fetched: {url}")

        monkeypatch.setattr(
            build_rbb24_polen_update_feed, "fetch_video_page", fail_fetch
        )
        build_rbb24_polen_update_feed.enrich_items(items, old)
        assert items[0]["description"] == "full cached description"
        assert items[0]["image"] == "https://www.rbb-online.de/detail-1280x720.jpg"

    def test_incomplete_cache_is_refetched(self, monkeypatch):
        monkeypatch.setenv("RBB24_POLEN_PAGES_DIR", PAGES)
        items = [
            {
                "id": WISENT_LINK,
                "title": "t",
                "link": WISENT_LINK,
                "description": "",
                "published": None,
                "image": "https://www.rbb24.de/x.jpg",
            }
        ]
        old = {
            WISENT_LINK: {
                "id": WISENT_LINK,
                "title": "t",
                "link": WISENT_LINK,
                "description": "",
                "published": None,
            }
        }
        build_rbb24_polen_update_feed.enrich_items(items, old)
        assert items[0]["published"] is not None
        assert items[0]["enclosure"]["url"].endswith(".mp4")

    def test_offline_mode_missing_copy_is_skipped(self, monkeypatch, tmp_path):
        monkeypatch.setenv("RBB24_POLEN_PAGES_DIR", str(tmp_path))

        def fail_fetch(url):
            raise AssertionError(f"offline mode must not fetch {url}")

        monkeypatch.setattr(
            build_rbb24_polen_update_feed, "fetch_video_page", fail_fetch
        )
        items = [
            {
                "id": WISENT_LINK,
                "title": "t",
                "link": WISENT_LINK,
                "description": "",
                "published": None,
                "image": "https://www.rbb24.de/x.jpg",
            }
        ]
        build_rbb24_polen_update_feed.enrich_items(items, {})
        assert items[0]["published"] is None
        assert "enclosure" not in items[0]

    def test_live_fetch_error_is_ignored(self, monkeypatch):
        monkeypatch.delenv("RBB24_POLEN_PAGES_DIR", raising=False)

        def boom(url):
            raise OSError("offline")

        monkeypatch.setattr(
            build_rbb24_polen_update_feed, "fetch_video_page", boom
        )
        items = [
            {
                "id": WISENT_LINK,
                "title": "t",
                "link": WISENT_LINK,
                "description": "",
                "published": None,
                "image": "https://www.rbb24.de/x.jpg",
            }
        ]
        build_rbb24_polen_update_feed.enrich_items(items, {})
        assert items[0]["published"] is None


class TestAttachMediaLengths:
    @staticmethod
    def _item():
        return {
            "id": "x",
            "title": "t",
            "link": "l",
            "description": "",
            "published": None,
            "enclosure": {
                "url": "https://rbb-progressive.ard-mcdn.de/a.mp4",
                "type": "video/mp4",
                "length": 0,
            },
        }

    def test_length_from_head_request(self, monkeypatch):
        class FakeResponse:
            headers = {"Content-Length": "56488879"}

            def raise_for_status(self):
                pass

        monkeypatch.setattr(common.creq, "head", lambda *a, **k: FakeResponse())
        items = [self._item()]
        build_rbb24_polen_update_feed.attach_media_lengths(items)
        assert items[0]["enclosure"]["length"] == 56488879

    def test_head_failure_keeps_zero(self, monkeypatch):
        def boom(*a, **k):
            raise OSError("offline")

        monkeypatch.setattr(common.creq, "head", boom)
        items = [self._item()]
        build_rbb24_polen_update_feed.attach_media_lengths(items)
        assert items[0]["enclosure"]["length"] == 0

    def test_known_length_is_kept(self, monkeypatch):
        monkeypatch.setattr(
            common.creq,
            "head",
            lambda *a, **k: (_ for _ in ()).throw(AssertionError("no HEAD")),
        )
        item = self._item()
        item["enclosure"]["length"] = 7
        build_rbb24_polen_update_feed.attach_media_lengths([item])
        assert item["enclosure"]["length"] == 7


class TestMainOffline:
    def test_end_to_end(self, monkeypatch, tmp_path):
        output = tmp_path / "rbb24-polen-update.xml"
        monkeypatch.setenv("RBB24_POLEN_HTML", OVERVIEW)
        monkeypatch.setenv("RBB24_POLEN_PAGES_DIR", PAGES)
        monkeypatch.setattr(
            build_rbb24_polen_update_feed, "OUTPUT_PATH", str(output)
        )
        monkeypatch.setattr(
            build_rbb24_polen_update_feed,
            "fetch_content_length",
            lambda url: 1234,
        )

        assert build_rbb24_polen_update_feed.main() == 0

        xml = output.read_text(encoding="utf-8")
        soup = BeautifulSoup(xml, "xml")
        assert soup.find("itunes:author").get_text() == "rbb24"
        assert soup.find("itunes:image")["href"].startswith(
            "https://www.rbb-online.de/"
        )
        items = soup.find_all("item")
        assert len(items) == 30
        newest = items[0]
        assert newest.find("guid").get_text() == WISENT_LINK
        assert newest.find("pubDate") is not None
        enc = newest.find("enclosure")
        assert enc["url"].endswith("_9zu16-sm1280.mp4")
        assert enc["type"] == "video/mp4"
        assert enc["length"] == "1234"
        assert newest.find("itunes:image")["href"].endswith("size=1280x720.jpg")

    def test_warning_items_are_dropped_on_success(self, monkeypatch, tmp_path):
        output = tmp_path / "rbb24-polen-update.xml"
        empty = tmp_path / "empty.html"
        empty.write_text("<html></html>", encoding="utf-8")
        monkeypatch.setenv("RBB24_POLEN_HTML", str(empty))
        monkeypatch.setattr(
            build_rbb24_polen_update_feed, "OUTPUT_PATH", str(output)
        )
        assert build_rbb24_polen_update_feed.main() == 0
        xml = output.read_text(encoding="utf-8")
        assert "<title>Feed build failed</title>" in xml

        monkeypatch.setenv("RBB24_POLEN_HTML", OVERVIEW)
        monkeypatch.setenv("RBB24_POLEN_PAGES_DIR", PAGES)
        monkeypatch.setattr(
            build_rbb24_polen_update_feed,
            "fetch_content_length",
            lambda url: 0,
        )
        assert build_rbb24_polen_update_feed.main() == 0
        xml = output.read_text(encoding="utf-8")
        assert "Feed build failed" not in xml


def redirect_output(monkeypatch, tmp_path):
    monkeypatch.setattr(
        build_rbb24_polen_update_feed,
        "OUTPUT_PATH",
        str(tmp_path / "rbb24-polen-update.xml"),
    )


class TestFailureWarning:
    """Soft failures must end up as an item inside the feed, exit 0."""

    @staticmethod
    def _fail_fetch(monkeypatch, message="direct fetch exploded"):
        def boom(*args, **kwargs):
            raise RuntimeError(message)

        monkeypatch.setattr(
            build_rbb24_polen_update_feed.common, "fetch_page", boom
        )

    def test_fetch_failure_writes_warning_feed_and_exits_zero(
        self, tmp_path, monkeypatch, capsys
    ):
        monkeypatch.delenv("RBB24_POLEN_HTML", raising=False)
        self._fail_fetch(monkeypatch)
        redirect_output(monkeypatch, tmp_path)
        assert build_rbb24_polen_update_feed.main() == 0

        xml = (tmp_path / "rbb24-polen-update.xml").read_text(encoding="utf-8")
        assert "<title>Feed build failed</title>" in xml
        assert "direct fetch exploded" in xml
        assert "Traceback (most recent call last)" in xml
        assert "<pubDate>" in xml
        assert capsys.readouterr().out.count("::warning::") == 1

    def test_broken_overview_writes_warning_feed(self, tmp_path, monkeypatch):
        empty = tmp_path / "empty.html"
        empty.write_text("<html></html>", encoding="utf-8")
        monkeypatch.setenv("RBB24_POLEN_HTML", str(empty))
        redirect_output(monkeypatch, tmp_path)
        assert build_rbb24_polen_update_feed.main() == 0

        xml = (tmp_path / "rbb24-polen-update.xml").read_text(encoding="utf-8")
        assert "<title>Feed build failed</title>" in xml
        assert xml.count("<item>") == 1

    def test_repeated_failure_replaces_warning_entry(self, tmp_path, monkeypatch):
        monkeypatch.delenv("RBB24_POLEN_HTML", raising=False)
        self._fail_fetch(monkeypatch)
        redirect_output(monkeypatch, tmp_path)
        assert build_rbb24_polen_update_feed.main() == 0
        assert build_rbb24_polen_update_feed.main() == 0

        xml = (tmp_path / "rbb24-polen-update.xml").read_text(encoding="utf-8")
        assert xml.count("<item>") == 1
        assert xml.count("Feed build failed") == 1

    def test_failure_keeps_previous_items(self, tmp_path, monkeypatch):
        monkeypatch.setenv("RBB24_POLEN_HTML", OVERVIEW)
        monkeypatch.setenv("RBB24_POLEN_PAGES_DIR", PAGES)
        monkeypatch.setattr(
            build_rbb24_polen_update_feed,
            "fetch_content_length",
            lambda url: 0,
        )
        redirect_output(monkeypatch, tmp_path)
        assert build_rbb24_polen_update_feed.main() == 0
        xml = (tmp_path / "rbb24-polen-update.xml").read_text(encoding="utf-8")
        items_before = xml.count("<item>")
        assert items_before > 0

        monkeypatch.delenv("RBB24_POLEN_HTML")
        monkeypatch.delenv("RBB24_POLEN_PAGES_DIR")
        self._fail_fetch(monkeypatch)
        assert build_rbb24_polen_update_feed.main() == 0

        xml = (tmp_path / "rbb24-polen-update.xml").read_text(encoding="utf-8")
        assert xml.count("<item>") == items_before + 1
        assert "<title>Feed build failed</title>" in xml

    def test_success_removes_stale_warning(self, tmp_path, monkeypatch):
        common_mod = build_rbb24_polen_update_feed.common
        real_fetch_page = common_mod.fetch_page
        monkeypatch.delenv("RBB24_POLEN_HTML", raising=False)
        self._fail_fetch(monkeypatch)
        redirect_output(monkeypatch, tmp_path)
        assert build_rbb24_polen_update_feed.main() == 0

        monkeypatch.setattr(common_mod, "fetch_page", real_fetch_page)
        monkeypatch.setenv("RBB24_POLEN_HTML", OVERVIEW)
        monkeypatch.setenv("RBB24_POLEN_PAGES_DIR", PAGES)
        monkeypatch.setattr(
            build_rbb24_polen_update_feed,
            "fetch_content_length",
            lambda url: 0,
        )
        assert build_rbb24_polen_update_feed.main() == 0

        xml = (tmp_path / "rbb24-polen-update.xml").read_text(encoding="utf-8")
        assert "Feed build failed" not in xml
