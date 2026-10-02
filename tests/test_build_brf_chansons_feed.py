"""Tests for the BRF1 "Chansons, Lieder und Folk" feed builder."""

import os
from datetime import datetime
from zoneinfo import ZoneInfo

import build_brf_chansons_feed

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
            assert item["image"].startswith("https://1.brf.be/wp-content/uploads/")

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
