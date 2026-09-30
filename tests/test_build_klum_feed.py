"""Tests for the klum.com/news feed builder."""

import os
from datetime import datetime, timezone

import build_klum_feed

FIXTURE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "fixtures", "klum-news.html"
)


def parse_fixture():
    with open(FIXTURE, encoding="utf-8") as f:
        return build_klum_feed.parse_klum(f.read())


def by_prefix(items, prefix):
    return [i for i in items if i["title"].lower().startswith(prefix.lower())]


class TestParseKlum:
    def test_item_shape(self):
        items = parse_fixture()
        assert len(items) == 69
        for item in items:
            assert set(item) == {"id", "title", "link", "description", "published"}
            assert item["title"]
            assert item["description"] == item["title"]
            assert item["link"].startswith("http")

    def test_ids_are_unique_synthetic_anchors(self):
        items = parse_fixture()
        ids = [i["id"] for i in items]
        assert len(set(ids)) == len(ids)
        for item_id in ids:
            assert item_id.startswith("https://www.klum.com/news#")

    def test_dates_are_utc(self):
        items = parse_fixture()
        for item in items:
            if item["published"] is not None:
                assert item["published"].tzinfo == timezone.utc

    def test_newest_item(self):
        item = by_prefix(parse_fixture(), "Der Möchtegernekanzler")[0]
        assert item["published"] == datetime(2026, 9, 21, tzinfo=timezone.utc)
        # only button is an expiring signed CDN mp4 -> page link fallback
        assert item["link"] == "https://www.klum.com/news"
        assert item["id"] == "https://www.klum.com/news#20260921-der-mochtegernekanzler"

    def test_date_spanning_multiple_elements_is_parsed(self):
        # HTML renders this date as "21." + "09.2026" in separate spans
        items = by_prefix(parse_fixture(), "Der Möchtegernekanzler")
        assert items[0]["published"].year == 2026

    def test_expiring_and_relative_links(self):
        items = parse_fixture()
        weihnachtslied = by_prefix(items, "Weihnachtslied")[0]
        assert weihnachtslied["published"] == datetime(
            2024, 12, 20, tzinfo=timezone.utc
        )
        # mangled www.yout-ube.com host is normalized
        assert weihnachtslied["link"] == "https://www.youtube.com/watch?v=0qEfXyiJbaA"

        offener = by_prefix(items, "Offener Brief an den Bürgermeister von Bergisch")[
            0
        ]
        assert offener["link"] == "https://www.klum.com/empty-pagef219b1ce"

    def test_item_without_button_links_to_page(self):
        item = by_prefix(parse_fixture(), "Das Manifest der SPD")[0]
        assert item["link"] == "https://www.klum.com/news"
        assert item["published"] == datetime(2025, 6, 13, tzinfo=timezone.utc)

    def test_mobile_fallback_supplies_missing_date(self):
        # the desktop rendering of this item lost its date; the mobile
        # variant still has it (26.03.2025)
        item = by_prefix(parse_fixture(), "Sondervermögen = Schulden")[0]
        assert item["published"] == datetime(2025, 3, 26, tzinfo=timezone.utc)

    def test_item_without_date_is_kept(self):
        item = by_prefix(parse_fixture(), "Eine Beichte mit Handbremse")[0]
        assert item["published"] is None

    def test_same_title_different_dates_are_distinct_items(self):
        items = by_prefix(parse_fixture(), "Ist die Schweiz ein Vorbild")
        assert {i["published"].date().isoformat() for i in items} == {
            "2025-12-19",
            "2025-08-01",
        }
        assert all(
            i["link"] == "https://www.youtube.com/watch?v=IjaLps8PYPM" for i in items
        )

    def test_mobile_desktop_copies_are_deduplicated(self):
        items = parse_fixture()
        assert len(by_prefix(items, "So sah der Nikolaus vor")) == 1
        assert len(by_prefix(items, "Ist die Schweiz ein Vorbild")) == 2
        assert len(by_prefix(items, "Spende")) == 1
        assert len(by_prefix(items, "Wer hat den Plan B für KI")) == 1
        assert not by_prefix(items, "Meine Meinung zu KI")

    def test_inline_date_in_sentence_is_not_stripped(self):
        item = by_prefix(parse_fixture(), "Ab dem 01.08.2023")[0]
        assert item["published"] == datetime(2023, 6, 9, tzinfo=timezone.utc)
        assert item["title"] == (
            "Ab dem 01.08.2023 ist das Gasthaus Zum Horn neu verpachtet"
        )
