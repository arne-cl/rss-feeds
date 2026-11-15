"""Tests for the VRT Radio 1 "Duyster" feed builder.

All fixtures are saved live GraphQL responses (VRT MAX program page,
one episode page, one media-resolver response) — no network needed.
"""

import json
import os
from datetime import datetime, timezone
from urllib.parse import quote

import build_vrt_radio1_duyster_feed as builder
import common
from bs4 import BeautifulSoup

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
PROGRAM = os.path.join(FIXTURES, "vrt-radio1-duyster-program.json")
EPISODE = os.path.join(FIXTURES, "vrt-radio1-duyster-episode.json")
MEDIA = os.path.join(FIXTURES, "vrt-radio1-duyster-media.json")
SHOW_URL = builder.SHOW_URL
EPISODE_SLUG = "duyster~11-39811-0"
EPISODE_LINK = f"{SHOW_URL}{EPISODE_SLUG}/"
STREAM_ID = (
    "pbs-pub-b3fba1ef-4b14-4c31-9bfd-359c64461869$"
    "aud-1a326e77-9106-4b26-be83-6d4878e00099"
)


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def parse_program_fixture():
    return builder.parse_program(load_json(PROGRAM))


def by_link(items, slug):
    return [i for i in items if i["link"].endswith(f"/{slug}/")]


class TestJwt:
    def test_header_and_payload_shape(self):
        token = builder.jwt_hs256({"exp": 123.5})
        head, payload, _sig = token.split(".")
        import base64

        def b64json(part):
            return json.loads(base64.urlsafe_b64decode(part + "=="))

        header = b64json(head)
        assert header["alg"] == "HS256"
        assert header["typ"] == "JWT"
        assert header["kid"] == builder.PLAYER_KEY_ID
        assert b64json(payload)["exp"] == 123.5

    def test_token_matches_hmac_signature(self):
        import base64
        import hashlib
        import hmac

        token = builder.jwt_hs256({"a": 1}, key="k")
        head, payload, sig = token.split(".")
        signing_input = f"{head}.{payload}".encode()
        expected = hmac.new(b"k", signing_input, hashlib.sha256).digest()
        assert base64.urlsafe_b64encode(expected).rstrip(b"=").decode() == sig


class TestParseProgram:
    def test_all_tiles_found(self):
        assert len(parse_program_fixture()) == 10

    def test_scheduled_upcoming_tiles_are_excluded(self):
        items = parse_program_fixture()
        # 39812+ are future broadcasts from the "Geplande uitzendingen" tab
        assert all(not i["link"].endswith(f"/duyster~11-398{digit}-0/") for i in items
                   for digit in "23456789")

    def test_item_shape(self):
        for item in parse_program_fixture():
            assert {"id", "title", "link", "description", "published", "image"} <= set(item)
            assert item["title"]
            assert item["published"] is None  # dates come from the episode page
            assert item["link"].startswith(SHOW_URL)

    def test_ids_are_unique_episode_urls(self):
        items = parse_program_fixture()
        ids = [i["id"] for i in items]
        assert len(set(ids)) == len(ids)
        assert ids[0] == items[0]["link"]

    def test_newest_tile(self):
        item = by_link(parse_program_fixture(), EPISODE_SLUG)[0]
        assert item["id"] == EPISODE_LINK
        assert item["link"] == EPISODE_LINK
        assert item["title"] == "DUYSTER."
        assert item["description"] == (
            "Win tickets voor Tortoise in de Arenberg in Antwerpen"
        )
        assert item["image"].startswith("https://images.vrt.be/")

    def test_broken_page_raises(self):
        for broken in ({}, {"data": {}}, {"data": {"page": {}}}):
            try:
                builder.parse_program(broken)
            except ValueError:
                continue
            raise AssertionError(f"no ValueError for {broken}")

    def test_empty_tiles_raise(self):
        data = {"data": {"page": {"menu": {"items": []}}}}
        try:
            builder.parse_program(data)
        except ValueError as exc:
            assert "layout" in str(exc) or "no episode" in str(exc)
        else:
            raise AssertionError("no ValueError for empty tile list")


class TestParseEpisode:
    def test_broadcast_date_is_utc_aware(self):
        parsed = builder.parse_episode(load_json(EPISODE))
        assert parsed["broadcast_start"] == datetime(
            2026, 11, 9, 21, 0, tzinfo=timezone.utc
        )

    def test_stream_id(self):
        assert builder.parse_episode(load_json(EPISODE))["stream_id"] == STREAM_ID

    def test_title_has_full_date_without_site_suffix(self):
        title = builder.parse_episode(load_json(EPISODE))["title"]
        assert title == "DUYSTER. - maandag 9 november 2026 om 22:00"
        assert "VRT MAX" not in title

    def test_description(self):
        parsed = builder.parse_episode(load_json(EPISODE))
        assert parsed["description"] == (
            "Win tickets voor Tortoise in de Arenberg in Antwerpen"
        )

    def test_broken_page_raises(self):
        for broken in ({}, {"data": {}}, {"data": {"page": {}}}):
            try:
                builder.parse_episode(broken)
            except ValueError:
                continue
            raise AssertionError(f"no ValueError for {broken}")

    def test_no_player_modes_raises(self):
        broken = {"data": {"page": {"player": {"modes": []}}}}
        try:
            builder.parse_episode(broken)
        except ValueError:
            return
        raise AssertionError("no ValueError for empty modes")


class TestResolveAudio:
    def test_hls_url_and_type_from_media_response(self):
        audio = builder.resolve_audio(load_json(MEDIA))
        assert audio["type"] == "application/vnd.apple.mpegurl"
        assert audio["url"].startswith("https://ondemand-radio.vrtcdn.be/")
        assert ".ism/.m3u8" in audio["url"]

    def test_no_hls_target_returns_none(self):
        assert builder.resolve_audio({"targetUrls": [{"type": "mpeg_dash", "url": "x"}]}) is None
        assert builder.resolve_audio({}) is None


class TestEnrichItems:
    def test_attaches_date_title_and_enclosure(self, monkeypatch):
        items = parse_program_fixture()
        calls = []

        def fake_episode(link):
            calls.append(link)
            return load_json(EPISODE) if link == EPISODE_LINK else None

        def fake_token():
            return "token"

        def fake_media(stream_id):
            return load_json(MEDIA)

        monkeypatch.setattr(builder, "fetch_episode_json", fake_episode)
        monkeypatch.setattr(builder, "fetch_player_token", fake_token)
        monkeypatch.setattr(builder, "fetch_media_json", fake_media)
        builder.enrich_items(items, {})

        assert calls[0] == EPISODE_LINK  # newest tile is attempted first
        assert len(calls) == 10  # all tiles attempted; only one has saved data
        item = by_link(items, EPISODE_SLUG)[0]
        assert item["published"] == datetime(2026, 11, 9, 21, 0, tzinfo=timezone.utc)
        assert item["title"] == "DUYSTER. - maandag 9 november 2026 om 22:00"
        assert item["description"] == (
            "Win tickets voor Tortoise in de Arenberg in Antwerpen"
        )
        assert item["enclosure"]["type"] == "application/vnd.apple.mpegurl"
        assert ".ism/.m3u8" in item["enclosure"]["url"]
        assert item["enclosure"]["length"] == 0
        # items without episode data stay untouched
        others = [i for i in items if i["link"] != EPISODE_LINK]
        assert all(i["published"] is None for i in others)
        assert all("enclosure" not in i for i in others)

    def test_cached_entries_are_not_refetched(self, monkeypatch):
        items = parse_program_fixture()
        old = by_link(parse_program_fixture(), EPISODE_SLUG)[0]
        old["published"] = datetime(2026, 11, 9, 21, 0, tzinfo=timezone.utc)
        old["title"] = "DUYSTER. - maandag 9 november 2026 om 22:00"
        old["enclosure"] = {
            "url": "https://ondemand-radio.vrtcdn.be/x.m3u8",
            "type": "application/vnd.apple.mpegurl",
            "length": 0,
        }

        def boom(*args, **kwargs):
            raise AssertionError("network fetch attempted for cached item")

        monkeypatch.setattr(builder, "fetch_episode_json", boom)
        monkeypatch.setattr(builder, "fetch_player_token", boom)
        monkeypatch.setattr(builder, "fetch_media_json", boom)
        builder.enrich_items(items, {old["id"]: old})

        item = by_link(items, EPISODE_SLUG)[0]
        assert item["enclosure"] == old["enclosure"]
        assert item["published"] == old["published"]
        assert item["title"] == old["title"]

    def test_episode_without_stream_id_gets_no_enclosure(self, monkeypatch):
        items = parse_program_fixture()
        episode = load_json(EPISODE)
        for mode in episode["data"]["page"]["player"]["modes"]:
            mode["streamId"] = None

        monkeypatch.setattr(builder, "fetch_episode_json", lambda link: episode)
        monkeypatch.setattr(builder, "fetch_player_token", lambda: "token")
        monkeypatch.setattr(builder, "fetch_media_json", lambda sid: {})
        builder.enrich_items(items, {})

        item = by_link(items, EPISODE_SLUG)[0]
        assert item["published"] is not None
        assert "enclosure" not in item


class TestMainOffline:
    def test_end_to_end(self, monkeypatch, tmp_path):
        episodes = tmp_path / "episodes"
        media = tmp_path / "media"
        episodes.mkdir()
        media.mkdir()
        (episodes / f"{EPISODE_SLUG}.json").write_text(read(EPISODE), encoding="utf-8")
        (media / f"{EPISODE_SLUG}.json").write_text(read(MEDIA), encoding="utf-8")
        output = tmp_path / "vrt-radio1-duyster.xml"
        monkeypatch.setenv("VRT_DUYSTER_PROGRAM_JSON", PROGRAM)
        monkeypatch.setenv("VRT_DUYSTER_EPISODES_DIR", str(episodes))
        monkeypatch.setenv("VRT_DUYSTER_MEDIA_DIR", str(media))
        monkeypatch.setattr(builder, "OUTPUT_PATH", str(output))

        assert builder.main() == 0

        xml = output.read_bytes()
        assert b"<itunes:author>VRT Radio 1</itunes:author>" in xml
        assert b"Duyster (VRT Radio 1)" in xml
        soup = BeautifulSoup(xml, "xml")
        items = soup.find_all("item")
        assert len(items) == 10
        newest = items[0]
        assert newest.find("guid").get_text() == EPISODE_LINK
        assert newest.find("title").get_text() == (
            "DUYSTER. - maandag 9 november 2026 om 22:00"
        )
        assert newest.find("pubDate") is not None
        enc = newest.find("enclosure")
        assert ".ism/.m3u8" in enc["url"]
        assert enc["type"] == "application/vnd.apple.mpegurl"
        assert enc["length"] == "0"
        assert newest.find("itunes:image")["href"].startswith("https://images.vrt.be/")


def run_offline(monkeypatch):
    """Point the builder at the fixture copies (no network at all)."""
    monkeypatch.setenv("VRT_DUYSTER_PROGRAM_JSON", PROGRAM)
    monkeypatch.setenv(
        "VRT_DUYSTER_EPISODES_DIR", os.path.dirname(EPISODE)
    )
    monkeypatch.setenv("VRT_DUYSTER_MEDIA_DIR", os.path.dirname(MEDIA))


class TestFailureWarning:
    """Soft failures must end up as an item inside the feed, exit 0."""

    @staticmethod
    def _fail_fetch(monkeypatch, message="graphql exploded"):
        def boom(*args, **kwargs):
            raise RuntimeError(message)

        monkeypatch.setattr(builder, "fetch_program_json", boom)

    def test_fetch_failure_writes_warning_feed_and_exits_zero(
        self, tmp_path, monkeypatch, capsys
    ):
        monkeypatch.delenv("VRT_DUYSTER_PROGRAM_JSON", raising=False)
        self._fail_fetch(monkeypatch)
        output = tmp_path / "vrt-radio1-duyster.xml"
        monkeypatch.setattr(builder, "OUTPUT_PATH", str(output))
        assert builder.main() == 0

        xml = output.read_text(encoding="utf-8")
        assert "<title>Feed build failed</title>" in xml
        assert "graphql exploded" in xml
        assert "Traceback (most recent call last)" in xml
        assert "<pubDate>" in xml
        assert capsys.readouterr().out.count("::warning::") == 1

    def test_broken_page_writes_warning_feed(self, tmp_path, monkeypatch):
        empty = tmp_path / "empty.json"
        empty.write_text("{}", encoding="utf-8")
        monkeypatch.setenv("VRT_DUYSTER_PROGRAM_JSON", str(empty))
        output = tmp_path / "vrt-radio1-duyster.xml"
        monkeypatch.setattr(builder, "OUTPUT_PATH", str(output))
        assert builder.main() == 0

        xml = output.read_text(encoding="utf-8")
        assert "<title>Feed build failed</title>" in xml
        assert xml.count("<item>") == 1

    def test_failure_keeps_previous_items(self, tmp_path, monkeypatch):
        run_offline(monkeypatch)
        output = tmp_path / "vrt-radio1-duyster.xml"
        monkeypatch.setattr(builder, "OUTPUT_PATH", str(output))
        assert builder.main() == 0
        items_before = output.read_text(encoding="utf-8").count("<item>")
        assert items_before > 0

        monkeypatch.delenv("VRT_DUYSTER_PROGRAM_JSON")
        self._fail_fetch(monkeypatch)
        assert builder.main() == 0

        xml = output.read_text(encoding="utf-8")
        assert xml.count("<item>") == items_before + 1
        assert "<title>Feed build failed</title>" in xml

    def test_success_removes_stale_warning(self, tmp_path, monkeypatch):
        real_fetch = builder.fetch_program_json
        monkeypatch.delenv("VRT_DUYSTER_PROGRAM_JSON", raising=False)
        self._fail_fetch(monkeypatch)
        output = tmp_path / "vrt-radio1-duyster.xml"
        monkeypatch.setattr(builder, "OUTPUT_PATH", str(output))
        assert builder.main() == 0

        monkeypatch.setattr(builder, "fetch_program_json", real_fetch)
        run_offline(monkeypatch)
        assert builder.main() == 0

        xml = output.read_text(encoding="utf-8")
        assert "Feed build failed" not in xml
