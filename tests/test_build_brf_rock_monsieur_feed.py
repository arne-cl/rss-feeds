"""Tests for the BRF1 "Rock Monsieur" feed builder.

Exercises the shared brf1_show_feed module through the Rock Monsieur
ShowConfig; the parse/enrich/warning mechanics themselves are covered in
test_build_brf_chansons_feed.py.
"""

import os
from dataclasses import replace
from datetime import datetime
from zoneinfo import ZoneInfo

import brf1_show_feed
import build_brf_rock_monsieur_feed
import common
from bs4 import BeautifulSoup

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
ARCHIVE = os.path.join(FIXTURES, "brf1-rock-monsieur.html")
EPISODE = os.path.join(FIXTURES, "brf-rock-monsieur-pages", "1231559.html")
PLAY = os.path.join(FIXTURES, "brf-rock-monsieur-play", "568fbf.html")
BRF_TZ = ZoneInfo("Europe/Brussels")
CFG = build_brf_rock_monsieur_feed.CFG


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def parse_archive_fixture():
    return brf1_show_feed.parse_archive(CFG, read(ARCHIVE))


def by_id(items, episode_id):
    return [i for i in items if i["id"].endswith(f"/{episode_id}/")]


def parse_episode_fixture():
    return brf1_show_feed.parse_episode(read(EPISODE))


class TestParseEpisode:
    def test_play_hash_found_in_player_script(self):
        assert parse_episode_fixture()["play_hash"] == "568fbf"

    def test_excerpt(self):
        assert parse_episode_fixture()["excerpt"] == "Mit Volker Krings."

    def test_content_is_escaped_paragraphs(self):
        content = parse_episode_fixture()["content"]
        assert content.startswith(
            "<p>Heute mit neuer Musik vom kalifornischen "
            "Psychedelic-Trio Brainstory"
        )
        assert content.endswith("<p>Volker Krings</p>")
        assert "<script" not in content


class TestResolveAudio:
    def test_mp3_url_and_type_from_play_snippet(self):
        audio = brf1_show_feed.resolve_audio(read(PLAY))
        assert audio == {
            "url": (
                "https://streaming2.brf.be/audio/2026/46/"
                "37a8adab704c6401bd0ebbf43e3aeea4.mp3"
            ),
            "type": "audio/mpeg",
        }


class TestParseArchive:
    def test_all_cards_found_teaser_and_archive(self):
        # 2 newest in the "Sendungsprofil" teaser + 10 archive cards
        assert len(parse_archive_fixture()) == 12

    def test_item_shape(self):
        for item in parse_archive_fixture():
            assert {"id", "title", "link", "description", "published", "image"} <= set(item)
            assert item["title"]
            assert item["description"]
            assert item["link"].startswith("https://1.brf.be/sendungen/rock-monsieur/")
            assert item["image"] == "" or item["image"].startswith(
                "https://1.brf.be/wp-content/uploads/"
            )

    def test_ids_are_unique_episode_urls(self):
        items = parse_archive_fixture()
        ids = [i["id"] for i in items]
        assert len(set(ids)) == len(ids)
        for item_id in ids:
            assert item_id.startswith("https://1.brf.be/sendungen/rock-monsieur/")
            assert item_id.rstrip("/").rsplit("/", 1)[-1].isdigit()

    def test_newest_episode_from_teaser_section(self):
        item = by_id(parse_archive_fixture(), "1231559")[0]
        assert item["id"] == "https://1.brf.be/sendungen/rock-monsieur/1231559/"
        assert item["link"] == item["id"]
        assert item["title"] == "Rock Monsieur - 12. November"
        assert item["published"] == datetime(2026, 11, 12, 21, 0, tzinfo=BRF_TZ)
        assert item["description"] == "Mit Volker Krings."
        assert item["image"].endswith("radio-free-alice-1imogene-barron-600x400.jpg")

    def test_archive_card_second_newest(self):
        item = by_id(parse_archive_fixture(), "1231217")[0]
        assert item["published"] == datetime(2026, 11, 5, 21, 0, tzinfo=BRF_TZ)
        assert item["title"] == "Rock Monsieur - 5. November"

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
            return read(EPISODE) if "1231559" in link else None

        monkeypatch.setattr(
            brf1_show_feed, "fetch_episode_page", fake_episode
        )
        monkeypatch.setattr(
            brf1_show_feed,
            "fetch_play_snippet",
            lambda url: read(PLAY),
        )
        brf1_show_feed.enrich_items(CFG, items, {})

        item = by_id(items, "1231559")[0]
        assert item["content"].startswith("<p>")
        assert item["description"] == "Mit Volker Krings."
        assert item["enclosure"]["url"] == (
            "https://streaming2.brf.be/audio/2026/46/"
            "37a8adab704c6401bd0ebbf43e3aeea4.mp3"
        )
        assert item["enclosure"]["type"] == "audio/mpeg"
        assert item["enclosure"]["length"] == 0  # filled later by HEAD
        assert sum(1 for i in items if i.get("enclosure")) == 1


class TestMainOffline:
    def test_end_to_end(self, monkeypatch, tmp_path):
        pages = tmp_path / "pages"
        play = tmp_path / "play"
        pages.mkdir()
        play.mkdir()
        (pages / "1231559.html").write_text(read(EPISODE), encoding="utf-8")
        (play / "568fbf.html").write_text(read(PLAY), encoding="utf-8")
        output = tmp_path / "brf1-rock-monsieur.xml"
        monkeypatch.setenv("ROCK_MONSIEUR_HTML", ARCHIVE)
        monkeypatch.setenv("ROCK_MONSIEUR_PAGES_DIR", str(pages))
        monkeypatch.setenv("ROCK_MONSIEUR_PLAY_DIR", str(play))
        monkeypatch.setattr(
            brf1_show_feed, "fetch_content_length", lambda url: 1234
        )

        assert brf1_show_feed.main(replace(CFG, output_path=str(output))) == 0

        xml = output.read_bytes()
        assert b"<itunes:author>BRF1</itunes:author>" in xml
        assert b"Rock Monsieur (BRF1)" in xml
        soup = BeautifulSoup(xml, "xml")
        items = soup.find_all("item")
        assert len(items) == 12
        newest = items[0]
        assert newest.find("guid").get_text() == (
            "https://1.brf.be/sendungen/rock-monsieur/1231559/"
        )
        enc = newest.find("enclosure")
        assert enc["url"].endswith(
            "37a8adab704c6401bd0ebbf43e3aeea4.mp3"
        )
        assert enc["type"] == "audio/mpeg"
        assert enc["length"] == "1234"
        assert newest.find("itunes:image")["href"].startswith(
            "https://1.brf.be/wp-content/"
        )


def output_cfg(tmp_path):
    """ShowConfig redirected to a tmp output file (offline-safe)."""
    return replace(CFG, output_path=str(tmp_path / "brf1-rock-monsieur.xml"))


def run_offline(monkeypatch):
    """Neutralize the live enrichment fetches (length HEAD requests)."""
    monkeypatch.setenv(
        "ROCK_MONSIEUR_PAGES_DIR", os.path.join(FIXTURES, "brf-rock-monsieur-pages")
    )
    monkeypatch.setenv(
        "ROCK_MONSIEUR_PLAY_DIR", os.path.join(FIXTURES, "brf-rock-monsieur-play")
    )
    monkeypatch.setattr(brf1_show_feed, "fetch_content_length", lambda url: 0)


class TestFailureWarning:
    """Soft failures must end up as an item inside the feed, exit 0."""

    @staticmethod
    def _fail_fetch(monkeypatch, message="direct fetch exploded"):
        def boom(*args, **kwargs):
            raise RuntimeError(message)

        monkeypatch.setattr(brf1_show_feed.common, "fetch_page", boom)

    def test_fetch_failure_writes_warning_feed_and_exits_zero(
        self, tmp_path, monkeypatch, capsys
    ):
        monkeypatch.delenv("ROCK_MONSIEUR_HTML", raising=False)
        self._fail_fetch(monkeypatch)
        cfg = output_cfg(tmp_path)
        assert brf1_show_feed.main(cfg) == 0

        xml = (tmp_path / "brf1-rock-monsieur.xml").read_text(encoding="utf-8")
        assert "<title>Feed build failed</title>" in xml
        assert "direct fetch exploded" in xml
        assert "Traceback (most recent call last)" in xml
        assert "<pubDate>" in xml
        assert capsys.readouterr().out.count("::warning::") == 1

    def test_broken_archive_writes_warning_feed(self, tmp_path, monkeypatch):
        empty = tmp_path / "empty.html"
        empty.write_text("<html></html>", encoding="utf-8")
        monkeypatch.setenv("ROCK_MONSIEUR_HTML", str(empty))
        assert brf1_show_feed.main(output_cfg(tmp_path)) == 0

        xml = (tmp_path / "brf1-rock-monsieur.xml").read_text(encoding="utf-8")
        assert "<title>Feed build failed</title>" in xml
        assert xml.count("<item>") == 1

    def test_failure_keeps_previous_items(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ROCK_MONSIEUR_HTML", ARCHIVE)
        run_offline(monkeypatch)
        cfg = output_cfg(tmp_path)
        assert brf1_show_feed.main(cfg) == 0
        xml = (tmp_path / "brf1-rock-monsieur.xml").read_text(encoding="utf-8")
        items_before = xml.count("<item>")
        assert items_before > 0

        monkeypatch.delenv("ROCK_MONSIEUR_HTML")
        self._fail_fetch(monkeypatch)
        assert brf1_show_feed.main(cfg) == 0

        xml = (tmp_path / "brf1-rock-monsieur.xml").read_text(encoding="utf-8")
        assert xml.count("<item>") == items_before + 1
        assert "<title>Feed build failed</title>" in xml

    def test_success_removes_stale_warning(self, tmp_path, monkeypatch):
        real_fetch_page = common.fetch_page
        monkeypatch.delenv("ROCK_MONSIEUR_HTML", raising=False)
        self._fail_fetch(monkeypatch)
        cfg = output_cfg(tmp_path)
        assert brf1_show_feed.main(cfg) == 0

        monkeypatch.setattr(common, "fetch_page", real_fetch_page)
        monkeypatch.setenv("ROCK_MONSIEUR_HTML", ARCHIVE)
        run_offline(monkeypatch)
        assert brf1_show_feed.main(cfg) == 0

        xml = (tmp_path / "brf1-rock-monsieur.xml").read_text(encoding="utf-8")
        assert "Feed build failed" not in xml
