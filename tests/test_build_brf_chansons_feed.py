"""Tests for the BRF1 "Chansons, Lieder und Folk" feed builder."""

import os
from datetime import datetime
from zoneinfo import ZoneInfo

import build_brf_chansons_feed
import common
from bs4 import BeautifulSoup

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
ARCHIVE = os.path.join(FIXTURES, "brf1-chansons.html")
EPISODE = os.path.join(FIXTURES, "brf-chansons-pages", "1227507.html")
PLAY = os.path.join(FIXTURES, "brf-chansons-play", "5689cb.html")
BRF_TZ = ZoneInfo("Europe/Brussels")


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def parse_archive_fixture():
    return build_brf_chansons_feed.parse_archive(read(ARCHIVE))


def by_id(items, episode_id):
    return [i for i in items if i["id"].endswith(f"/{episode_id}/")]


def parse_episode_fixture():
    return build_brf_chansons_feed.parse_episode(read(EPISODE))


class TestParseEpisode:
    def test_play_hash_found_in_player_script(self):
        assert parse_episode_fixture()["play_hash"] == "5689cb"

    def test_excerpt_is_full_sentence(self):
        excerpt = parse_episode_fixture()["excerpt"]
        assert excerpt.startswith(
            'Katharina Kollmann alias Nichtseattle hat mit "Große Liebe"'
        )
        assert excerpt.endswith("solidarische, prekäre Zwischenräume.")

    def test_content_is_escaped_paragraphs(self):
        content = parse_episode_fixture()["content"]
        assert content.startswith("<p>")
        assert content.endswith("<p>Maaru Will</p>")
        assert "&quot;Nichtseattle&quot;?" in content
        # the &nbsp;-only filler paragraph before the player is dropped
        assert "&nbsp;" not in content
        # no raw HTML from the article may leak into content
        assert "<div" not in content
        assert "<script" not in content

    def test_episode_without_player(self):
        html = (
            "<html><body><p class='excerpt under-title'>Kurzbeschreibung</p>"
            "<section class='classic-content'><article>"
            "<p>Hello world</p></article></section></body></html>"
        )
        result = build_brf_chansons_feed.parse_episode(html)
        assert result["play_hash"] is None
        assert result["content"] == "<p>Hello world</p>"
        assert result["excerpt"] == "Kurzbeschreibung"


class TestResolveAudio:
    def test_mp3_url_and_type_from_play_snippet(self):
        audio = build_brf_chansons_feed.resolve_audio(read(PLAY))
        assert audio == {
            "url": (
                "https://streaming2.brf.be/audio/2026/40/"
                "f3edc82a75e9abb8bb302761597fd249.mp3"
            ),
            "type": "audio/mpeg",
        }

    def test_no_audio_in_snippet(self):
        assert build_brf_chansons_feed.resolve_audio("<html></html>") is None


class TestParseArchive:
    def test_all_cards_found_teaser_and_archive(self):
        # 2 newest in the "Sendungsprofil" teaser + 10 archive cards
        items = parse_archive_fixture()
        assert len(items) == 12

    def test_item_shape(self):
        items = parse_archive_fixture()
        for item in items:
            assert {"id", "title", "link", "description", "published", "image"} <= set(item)
            assert item["title"]
            assert item["description"]
            assert item["link"].startswith("https://1.brf.be/sendungen/chansons/")
            assert item["image"] == "" or item["image"].startswith(
                "https://1.brf.be/wp-content/uploads/"
            )

    def test_non_jpg_png_images_are_dropped(self):
        # feedgen's itunes:image only accepts .jpg/.png; this card has .jpeg
        item = by_id(parse_archive_fixture(), "1221968")[0]
        assert item["image"] == ""

    def test_ids_are_unique_episode_urls(self):
        items = parse_archive_fixture()
        ids = [i["id"] for i in items]
        assert len(set(ids)) == len(ids)
        for item_id in ids:
            assert item_id.startswith("https://1.brf.be/sendungen/chansons/")
            assert item_id.rstrip("/").rsplit("/", 1)[-1].isdigit()

    def test_newest_episode_from_teaser_section(self):
        item = by_id(parse_archive_fixture(), "1227507")[0]
        assert item["id"] == "https://1.brf.be/sendungen/chansons/1227507/"
        assert item["link"] == item["id"]
        assert item["title"] == (
            "Chansons, Lieder und Folk: Nichtseattle "
            "– Liebe als radikale, solidarische Praxis"
        )
        assert item["published"] == datetime(2026, 9, 28, 21, 0, tzinfo=BRF_TZ)
        assert item["description"].startswith(
            "Katharina Kollmann alias Nichtseattle hat mit"
        )
        assert "nichtseattle" in item["image"]

    def test_archive_card_second_newest(self):
        item = by_id(parse_archive_fixture(), "1226713")[0]
        assert item["published"] == datetime(2026, 9, 21, 21, 0, tzinfo=BRF_TZ)
        assert item["title"] == (
            "Chansons, Lieder und Folk: Jake Xerxes Fussell, "
            "Retter der vergessenen Lieder"
        )

    def test_dates_are_timezone_aware(self):
        for item in parse_archive_fixture():
            assert item["published"] is not None
            assert item["published"].tzinfo is not None

    def test_items_are_ordered_newest_first(self):
        items = parse_archive_fixture()
        published = [i["published"] for i in items]
        assert published == sorted(published, reverse=True)


class TestEnrichItems:
    def test_attaches_content_excerpt_and_enclosure(self, monkeypatch):
        items = parse_archive_fixture()

        def fake_episode(link):
            return read(EPISODE) if "1227507" in link else None

        monkeypatch.setattr(
            build_brf_chansons_feed, "fetch_episode_page", fake_episode
        )
        monkeypatch.setattr(
            build_brf_chansons_feed,
            "fetch_play_snippet",
            lambda url: read(PLAY),
        )
        build_brf_chansons_feed.enrich_items(items, {})

        item = by_id(items, "1227507")[0]
        assert item["content"].startswith("<p>")
        assert item["description"].endswith("solidarische, prekäre Zwischenräume.")
        assert item["enclosure"]["url"] == (
            "https://streaming2.brf.be/audio/2026/40/"
            "f3edc82a75e9abb8bb302761597fd249.mp3"
        )
        assert item["enclosure"]["type"] == "audio/mpeg"
        assert item["enclosure"]["length"] == 0  # filled later by HEAD
        # all other episodes had no (fetchable) page in this test
        assert sum(1 for i in items if i.get("enclosure")) == 1

    def test_cached_items_are_not_refetched(self, monkeypatch):
        items = parse_archive_fixture()
        old = {
            "https://1.brf.be/sendungen/chansons/1227507/": {
                "id": "https://1.brf.be/sendungen/chansons/1227507/",
                "title": "cached",
                "link": "https://1.brf.be/sendungen/chansons/1227507/",
                "description": "full cached description",
                "published": None,
                "content": "<p>cached content</p>",
                "enclosure": {
                    "url": "https://streaming2.brf.be/audio/x.mp3",
                    "type": "audio/mpeg",
                    "length": 42,
                },
            }
        }
        calls = []

        def fake_fetch(link):
            calls.append(link)
            return None  # uncached episodes have no fetchable page here

        monkeypatch.setattr(
            build_brf_chansons_feed, "fetch_episode_page", fake_fetch
        )
        monkeypatch.setattr(
            build_brf_chansons_feed, "fetch_play_snippet", fake_fetch
        )
        build_brf_chansons_feed.enrich_items(items, old)

        item = by_id(items, "1227507")[0]
        assert item["content"] == "<p>cached content</p>"
        assert item["enclosure"]["length"] == 42
        assert item["description"] == "full cached description"
        assert not any("1227507" in c for c in calls)

    def test_offline_mode_uses_saved_copies_only(self, monkeypatch, tmp_path):
        pages = tmp_path / "pages"
        play = tmp_path / "play"
        pages.mkdir()
        play.mkdir()
        (pages / "1227507.html").write_text(read(EPISODE), encoding="utf-8")
        (play / "5689cb.html").write_text(read(PLAY), encoding="utf-8")
        monkeypatch.setenv("CHANSONS_PAGES_DIR", str(pages))
        monkeypatch.setenv("CHANSONS_PLAY_DIR", str(play))

        def fail_fetch(url):
            raise AssertionError(f"offline mode must not fetch {url}")

        monkeypatch.setattr(
            build_brf_chansons_feed, "fetch_episode_page", fail_fetch
        )
        monkeypatch.setattr(
            build_brf_chansons_feed, "fetch_play_snippet", fail_fetch
        )
        items = [by_id(parse_archive_fixture(), "1227507")[0]]
        build_brf_chansons_feed.enrich_items(items, {})
        assert items[0]["enclosure"]["url"].endswith(".mp3")

    def test_offline_mode_missing_copy_is_skipped(self, monkeypatch, tmp_path):
        monkeypatch.setenv("CHANSONS_PAGES_DIR", str(tmp_path))
        monkeypatch.setenv("CHANSONS_PLAY_DIR", str(tmp_path))
        monkeypatch.setattr(
            build_brf_chansons_feed,
            "fetch_episode_page",
            lambda url: (_ for _ in ()).throw(AssertionError("no fetch")),
        )
        items = [by_id(parse_archive_fixture(), "1227507")[0]]
        build_brf_chansons_feed.enrich_items(items, {})
        assert "content" not in items[0]
        assert "enclosure" not in items[0]


class TestAttachAudioLengths:
    def test_length_from_head_request(self, monkeypatch):
        class FakeResponse:
            headers = {"Content-Length": "56488879"}

            def raise_for_status(self):
                pass

        monkeypatch.setattr(
            common.creq, "head", lambda *a, **k: FakeResponse()
        )
        items = [
            {
                "id": "x",
                "title": "t",
                "link": "l",
                "description": "",
                "published": None,
                "enclosure": {
                    "url": "https://streaming2.brf.be/audio/a.mp3",
                    "type": "audio/mpeg",
                    "length": 0,
                },
            }
        ]
        build_brf_chansons_feed.attach_audio_lengths(items)
        assert items[0]["enclosure"]["length"] == 56488879

    def test_head_failure_keeps_zero(self, monkeypatch):
        def boom(*a, **k):
            raise OSError("offline")

        monkeypatch.setattr(common.creq, "head", boom)
        items = [
            {
                "id": "x",
                "title": "t",
                "link": "l",
                "description": "",
                "published": None,
                "enclosure": {
                    "url": "https://streaming2.brf.be/audio/a.mp3",
                    "type": "audio/mpeg",
                    "length": 0,
                },
            }
        ]
        build_brf_chansons_feed.attach_audio_lengths(items)
        assert items[0]["enclosure"]["length"] == 0

    def test_known_length_is_kept(self, monkeypatch):
        monkeypatch.setattr(
            common.creq,
            "head",
            lambda *a, **k: (_ for _ in ()).throw(AssertionError("no HEAD")),
        )
        items = [
            {
                "id": "x",
                "title": "t",
                "link": "l",
                "description": "",
                "published": None,
                "enclosure": {
                    "url": "https://streaming2.brf.be/audio/a.mp3",
                    "type": "audio/mpeg",
                    "length": 7,
                },
            }
        ]
        build_brf_chansons_feed.attach_audio_lengths(items)
        assert items[0]["enclosure"]["length"] == 7


class TestMainOffline:
    def test_end_to_end(self, monkeypatch, tmp_path):
        pages = tmp_path / "pages"
        play = tmp_path / "play"
        pages.mkdir()
        play.mkdir()
        (pages / "1227507.html").write_text(read(EPISODE), encoding="utf-8")
        (play / "5689cb.html").write_text(read(PLAY), encoding="utf-8")
        output = tmp_path / "brf1-chansons.xml"
        monkeypatch.setenv("CHANSONS_HTML", ARCHIVE)
        monkeypatch.setenv("CHANSONS_PAGES_DIR", str(pages))
        monkeypatch.setenv("CHANSONS_PLAY_DIR", str(play))
        monkeypatch.setattr(build_brf_chansons_feed, "OUTPUT_PATH", str(output))
        monkeypatch.setattr(
            build_brf_chansons_feed,
            "fetch_content_length",
            lambda url: 1234,
        )

        assert build_brf_chansons_feed.main() == 0

        import common

        xml = output.read_bytes()
        assert b"<itunes:author>BRF1</itunes:author>" in xml
        soup = BeautifulSoup(xml, "xml")
        items = soup.find_all("item")
        assert len(items) == 12
        newest = items[0]
        assert newest.find("guid").get_text() == (
            "https://1.brf.be/sendungen/chansons/1227507/"
        )
        enc = newest.find("enclosure")
        assert enc["url"].endswith(
            "f3edc82a75e9abb8bb302761597fd249.mp3"
        )
        assert enc["type"] == "audio/mpeg"
        assert enc["length"] == "1234"
        assert newest.find("itunes:image")["href"].startswith(
            "https://1.brf.be/wp-content/"
        )

def redirect_output(monkeypatch, tmp_path):
    monkeypatch.setattr(
        build_brf_chansons_feed, "OUTPUT_PATH", str(tmp_path / "brf1-chansons.xml")
    )


def run_offline(monkeypatch):
    """Neutralize the live enrichment fetches (length HEAD requests)."""
    monkeypatch.setenv("CHANSONS_PAGES_DIR", os.path.join(FIXTURES, "brf-chansons-pages"))
    monkeypatch.setenv("CHANSONS_PLAY_DIR", os.path.join(FIXTURES, "brf-chansons-play"))
    monkeypatch.setattr(build_brf_chansons_feed, "fetch_content_length", lambda url: 0)


class TestFailureWarning:
    """Soft failures must end up as an item inside the feed, exit 0."""

    @staticmethod
    def _fail_fetch(monkeypatch, message="direct fetch exploded"):
        def boom(*args, **kwargs):
            raise RuntimeError(message)

        monkeypatch.setattr(build_brf_chansons_feed.common, "fetch_page", boom)

    def test_fetch_failure_writes_warning_feed_and_exits_zero(
        self, tmp_path, monkeypatch, capsys
    ):
        monkeypatch.delenv("CHANSONS_HTML", raising=False)
        self._fail_fetch(monkeypatch)
        redirect_output(monkeypatch, tmp_path)
        assert build_brf_chansons_feed.main() == 0

        xml = (tmp_path / "brf1-chansons.xml").read_text(encoding="utf-8")
        assert "<title>Feed build failed</title>" in xml
        assert "direct fetch exploded" in xml
        assert "Traceback (most recent call last)" in xml
        assert "<pubDate>" in xml
        assert capsys.readouterr().out.count("::warning::") == 1

    def test_broken_archive_writes_warning_feed(self, tmp_path, monkeypatch):
        empty = tmp_path / "empty.html"
        empty.write_text("<html></html>", encoding="utf-8")
        monkeypatch.setenv("CHANSONS_HTML", str(empty))
        redirect_output(monkeypatch, tmp_path)
        assert build_brf_chansons_feed.main() == 0

        xml = (tmp_path / "brf1-chansons.xml").read_text(encoding="utf-8")
        assert "<title>Feed build failed</title>" in xml
        assert xml.count("<item>") == 1

    def test_repeated_failure_replaces_warning_entry(self, tmp_path, monkeypatch):
        monkeypatch.delenv("CHANSONS_HTML", raising=False)
        self._fail_fetch(monkeypatch)
        redirect_output(monkeypatch, tmp_path)
        assert build_brf_chansons_feed.main() == 0
        assert build_brf_chansons_feed.main() == 0

        xml = (tmp_path / "brf1-chansons.xml").read_text(encoding="utf-8")
        assert xml.count("<item>") == 1
        assert xml.count("Feed build failed") == 1

    def test_failure_keeps_previous_items(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CHANSONS_HTML", ARCHIVE)
        run_offline(monkeypatch)
        redirect_output(monkeypatch, tmp_path)
        assert build_brf_chansons_feed.main() == 0
        xml = (tmp_path / "brf1-chansons.xml").read_text(encoding="utf-8")
        items_before = xml.count("<item>")
        assert items_before > 0

        monkeypatch.delenv("CHANSONS_HTML")
        self._fail_fetch(monkeypatch)
        assert build_brf_chansons_feed.main() == 0

        xml = (tmp_path / "brf1-chansons.xml").read_text(encoding="utf-8")
        assert xml.count("<item>") == items_before + 1
        assert "<title>Feed build failed</title>" in xml

    def test_success_removes_stale_warning(self, tmp_path, monkeypatch):
        monkeypatch.delenv("CHANSONS_HTML", raising=False)
        self._fail_fetch(monkeypatch)
        redirect_output(monkeypatch, tmp_path)
        assert build_brf_chansons_feed.main() == 0

        monkeypatch.setenv("CHANSONS_HTML", ARCHIVE)
        run_offline(monkeypatch)
        assert build_brf_chansons_feed.main() == 0

        xml = (tmp_path / "brf1-chansons.xml").read_text(encoding="utf-8")
        assert "Feed build failed" not in xml
