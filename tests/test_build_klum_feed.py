"""Tests for the klum.com/news feed builder."""

import os
from datetime import datetime, timezone

import pytest

import build_klum_feed

FIXTURE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "fixtures", "klum-news.html"
)
PAGES_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "fixtures", "klum-pages"
)
WUPSI_PAGE = os.path.join(PAGES_DIR, "wupsi-offiziele-anfrage-handy.html")


def parse_fixture():
    with open(FIXTURE, encoding="utf-8") as f:
        return build_klum_feed.parse_klum(f.read())


def by_prefix(items, prefix):
    return [i for i in items if i["title"].lower().startswith(prefix.lower())]


class TestParseKlum:
    def test_item_shape(self):
        items = parse_fixture()
        assert len(items) == 68
        for item in items:
            assert {"id", "title", "link", "description", "published"} <= set(item)
            assert set(item) <= {
                "id", "title", "link", "description", "published", "enclosure",
            }
            assert item["title"]
            assert item["description"] == item["title"]
            assert item["link"].startswith("http")
            if "enclosure" in item:
                assert set(item["enclosure"]) == {"url", "type", "length"}
                assert item["enclosure"]["length"] == 0  # filled later, live

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
        # the signed, expiring CDN mp4 is kept as link AND enclosure now
        assert item["link"].startswith("https://cdn.website-editor.net/")
        assert ".mp4" in item["link"]
        assert item["enclosure"]["url"] == item["link"]
        assert item["enclosure"]["type"] == "video/mp4"
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


class TestCanonicalLinks:
    def test_elektrosmog_uses_canonical_mobile_link(self):
        """Desktop renders this button as the Duda alias /empty-pagee3f564cc,
        the mobile variant as the canonical /wupsi-offiziele-anfrage-handy
        (identical pages) — the canonical URL must win."""
        item = by_prefix(parse_fixture(), "Elektrosmog")[0]
        assert item["link"] == "https://www.klum.com/wupsi-offiziele-anfrage-handy"
        assert item["published"] == datetime(2026, 8, 25, tzinfo=timezone.utc)

    def test_same_day_wording_variants_are_merged(self):
        """The 17.09.2026 Oktoberfest post appears twice with different
        wording (mobile: "Oktoberfest 2026 im Gasthaus ZUM HORN",
        desktop: "Oktoberfest im Gasthaus Zum Horn in Bergisch Gladbach")."""
        items = by_prefix(parse_fixture(), "Oktoberfest")
        assert len(items) == 2  # Helferskirchen + Gasthaus Zum Horn
        horn = [i for i in items if "horn" in i["title"].lower()]
        assert len(horn) == 1
        assert horn[0]["title"] == (
            "Oktoberfest im Gasthaus Zum Horn in Bergisch Gladbach"
        )
        assert horn[0]["link"] == "https://www.klum.com/oktoberfest-2026"
        assert horn[0]["published"] == datetime(2026, 9, 17, tzinfo=timezone.utc)

    def test_distinct_same_day_posts_are_kept(self):
        """Regression guard: unrelated posts on one day must not merge
        even when they share a short phrase ("In München tut ...")."""
        items = parse_fixture()
        assert len(by_prefix(items, "Mit Ansage")) == 1
        assert len(by_prefix(items, "Gibt es durch MFE")) == 1
        # different YouTube videos
        links = {
            by_prefix(items, "Mit Ansage")[0]["link"],
            by_prefix(items, "Gibt es durch MFE")[0]["link"],
        }
        assert len(links) == 2

    def test_empty_page_only_items_keep_their_link(self):
        item = by_prefix(
            parse_fixture(), "Offener Brief an den Bürgermeister von Bergisch"
        )[0]
        assert item["link"] == "https://www.klum.com/empty-pagef219b1ce"


class TestPruneSuperseded:
    @staticmethod
    def entry(item_id, title, link, published):
        return {
            "id": item_id,
            "title": title,
            "link": link,
            "description": title,
            "published": published,
        }

    def test_stale_alias_entry_is_pruned(self):
        """The previous feed can hold an anchor-id entry that the current
        parse merged away (mobile alias wording); it must not survive."""
        from datetime import datetime, timezone

        stale = self.entry(
            "https://www.klum.com/news#20260917-oktoberfest-2026-im-gasthaus-zum-horn",
            'Oktoberfest 2026 im Gasthaus"ZUM HORN"',
            "https://www.klum.com/empty-page2efa0a05",
            datetime(2026, 9, 17, tzinfo=timezone.utc),
        )
        fresh = self.entry(
            "https://www.klum.com/news#20260917-oktoberfest-im-gasthaus-zum-horn-in-bergisch-gladbach",
            "Oktoberfest im Gasthaus Zum Horn in Bergisch Gladbach",
            "https://www.klum.com/oktoberfest-2026",
            datetime(2026, 9, 17, tzinfo=timezone.utc),
        )
        other = self.entry(
            "https://www.klum.com/news#20260919-oktoberfest-in-helferskirchen-mit-susal",
            "Oktoberfest in Helferskirchen mit SUSAL",
            "https://www.klum.com/news",
            datetime(2026, 9, 19, tzinfo=timezone.utc),
        )
        merged = build_klum_feed.prune_superseded(
            {stale["id"]: stale, fresh["id"]: fresh, other["id"]: other},
            [fresh, other],
        )
        assert set(merged) == {fresh["id"], other["id"]}

    def test_genuine_distinct_entries_are_kept(self):
        from datetime import datetime, timezone

        repost = self.entry(
            "https://www.klum.com/news#20251219-ist-die-schweiz-ein-vorbild-fur-uns",
            "Ist die Schweiz ein Vorbild für uns?",
            "https://www.youtube.com/watch?v=IjaLps8PYPM",
            datetime(2025, 12, 19, tzinfo=timezone.utc),
        )
        items = [
            self.entry(
                "https://www.klum.com/news#20250801-ist-die-schweiz-ein-vorbild-fur-uns",
                "Ist die Schweiz ein Vorbild für uns?",
                "https://www.youtube.com/watch?v=IjaLps8PYPM",
                datetime(2025, 8, 1, tzinfo=timezone.utc),
            )
        ]
        merged = build_klum_feed.prune_superseded({repost["id"]: repost}, items)
        assert set(merged) == {repost["id"]}


@pytest.fixture
def wupsi_html():
    with open(WUPSI_PAGE, encoding="utf-8") as f:
        return f.read()


class TestExtractPageContent:
    def test_wupsi_article_paragraphs(self, wupsi_html):
        content = build_klum_feed.extract_page_content(wupsi_html)
        assert content is not None
        assert content.startswith("<p>")
        assert content.endswith("</p>")
        assert "<p>ELEKTROSMOG</p>" in content
        assert "<p>Guten Tag Herr Kretkowski" in content
        # no site chrome (menu/footer) and no builder boilerplate
        assert "DATENSCHUTZ" not in content
        assert "dmNewParagraph" not in content
        # BOM and whitespace junk is normalized
        assert "\ufeff" not in content

    def test_page_without_article_blocks(self):
        content = build_klum_feed.extract_page_content("<html><body>hi</body></html>")
        assert content is None


class TestEmbeddableLinks:
    @pytest.mark.parametrize(
        "link",
        [
            "https://www.klum.com/wupsi-offiziele-anfrage-handy",
            "https://www.klum.com/empty-pagee3f564cc",
            "https://www.klum.com/oktoberfest-2026",
            "https://www.klum.com/news/3976/weihnachtslied-",
            "https://klum.com/leserbrief-an-die-bergische-landeszeitung",
        ],
    )
    def test_internal_article_pages(self, link):
        assert build_klum_feed.is_embeddable_page(link)

    @pytest.mark.parametrize(
        "link",
        [
            "https://www.klum.com/news",
            "https://www.youtube.com/watch?v=PQgeDxl7DQI",
            "https://youtu.be/Vt4nSIlJV6Q",
            "https://www.klum.com/mein-brief-an-den-buergermeister-.pdfx?forced=true",
            "https://example.com/some-page",
            "https://www.klum.com/news",
        ],
    )
    def test_not_embeddable(self, link):
        assert not build_klum_feed.is_embeddable_page(link)


class TestEmbedContent:
    @staticmethod
    def item(item_id, link):
        return {
            "id": item_id,
            "title": "t",
            "link": link,
            "description": "t",
            "published": None,
        }

    def test_embeds_article_from_saved_copy(self, monkeypatch):
        monkeypatch.setenv("KLUM_PAGES_DIR", PAGES_DIR)
        items = [self.item("id-1", "https://www.klum.com/wupsi-offiziele-anfrage-handy")]
        build_klum_feed.embed_content(items, {})
        assert "<p>Guten Tag Herr Kretkowski" in items[0]["content"]

    def test_offline_mode_never_fetches(self, monkeypatch):
        """With KLUM_PAGES_DIR set, a missing saved copy must not hit the net."""
        monkeypatch.setenv("KLUM_PAGES_DIR", PAGES_DIR)
        monkeypatch.setattr(
            build_klum_feed,
            "fetch_article",
            lambda link: pytest.fail("must not fetch in offline mode"),
        )
        items = [self.item("id-1", "https://www.klum.com/oktoberfest-2026")]
        build_klum_feed.embed_content(items, {})
        assert "content" not in items[0]

    def test_reuses_cached_content_without_fetching(self, monkeypatch):
        monkeypatch.setattr(
            build_klum_feed,
            "fetch_article",
            lambda link: pytest.fail("must not fetch when cached"),
        )
        cached = self.item(
            "https://www.klum.com/news#20260825-elektrosmog",
            "https://www.klum.com/wupsi-offiziele-anfrage-handy",
        )
        cached["content"] = "<p>cached</p>"
        items = [
            self.item(
                "https://www.klum.com/news#20260825-elektrosmog",
                "https://www.klum.com/wupsi-offiziele-anfrage-handy",
            )
        ]
        build_klum_feed.embed_content(items, {cached["id"]: cached})
        assert items[0]["content"] == "<p>cached</p>"

    def test_youtube_items_are_untouched(self, monkeypatch):
        monkeypatch.setattr(
            build_klum_feed,
            "fetch_article",
            lambda link: pytest.fail("must not fetch YouTube links"),
        )
        items = [self.item("id-1", "https://www.youtube.com/watch?v=PQgeDxl7DQI")]
        build_klum_feed.embed_content(items, {})
        assert "content" not in items[0]

    def test_fetch_failure_is_tolerated(self, monkeypatch):
        monkeypatch.setattr(
            build_klum_feed,
            "fetch_article",
            lambda link: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        items = [self.item("id-1", "https://www.klum.com/oktoberfest-2026")]
        build_klum_feed.embed_content(items, {})
        assert "content" not in items[0]


class TestMediaTypes:
    @pytest.mark.parametrize(
        "url,mime",
        [
            ("https://cdn.website-editor.net/a/b.mp4?Expires=1", "video/mp4"),
            ("https://cdn.website-editor.net/a/b.pdf", "application/pdf"),
            ("https://cdn.website-editor.net/a/b.jpg", "image/jpeg"),
            ("https://cdn.website-editor.net/a/b.jpeg", "image/jpeg"),
            ("https://cdn.website-editor.net/a/b.png", "image/png"),
            ("https://cdn.website-editor.net/a/b.mp3", "audio/mpeg"),
            ("https://cdn.website-editor.net/a/b", "application/octet-stream"),
        ],
    )
    def test_media_type_from_extension(self, url, mime):
        assert build_klum_feed.media_type(url) == mime


class TestAttachMediaLengths:
    @staticmethod
    def media_item():
        return {
            "id": "x",
            "title": "t",
            "link": "https://cdn.website-editor.net/a/b.mp4",
            "description": "t",
            "published": None,
            "enclosure": {
                "url": "https://cdn.website-editor.net/a/b.mp4",
                "type": "video/mp4",
                "length": 0,
            },
        }

    def test_fills_length_from_head_request(self, monkeypatch):
        monkeypatch.setattr(build_klum_feed, "fetch_content_length", lambda url: 4711)
        items = [self.media_item()]
        build_klum_feed.attach_media_lengths(items)
        assert items[0]["enclosure"]["length"] == 4711

    def test_head_failure_keeps_zero(self, monkeypatch):
        def boom(url):
            raise RuntimeError("offline")

        monkeypatch.setattr(build_klum_feed, "fetch_content_length", boom)
        items = [self.media_item()]
        build_klum_feed.attach_media_lengths(items)
        assert items[0]["enclosure"]["length"] == 0

    def test_items_without_enclosure_untouched(self, monkeypatch):
        monkeypatch.setattr(
            build_klum_feed,
            "fetch_content_length",
            lambda url: pytest.fail("must not fetch without enclosure"),
        )
        items = [{"id": "x", "title": "t", "link": "https://www.youtube.com/watch?v=1",
                  "description": "t", "published": None}]
        build_klum_feed.attach_media_lengths(items)
        assert "enclosure" not in items[0]
