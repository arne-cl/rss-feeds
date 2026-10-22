"""Tests for the combined Instagram stories feed builder."""

import json

import pytest

import build_instagram_stories_feed as stories


def story_node(
    node_id="300111_1795769118",
    media_type=2,
    taken_at=1735689600,
    expires_in=86400,
    video=True,
    username="thebeths",
):
    node = {
        "id": node_id,
        "pk": node_id.split("_")[0],
        "media_type": media_type,
        "taken_at": taken_at,
        "expiring_at": taken_at + expires_in,
        "image_versions2": {
            "candidates": [{"url": f"https://cdn.example.com/{node_id}.jpg"}]
        },
        "user": {"pk": "1795769118", "username": username, "full_name": "The Beths"},
    }
    if video:
        node["video_versions"] = [
            {"url": f"https://cdn.example.com/{node_id}.mp4"}
        ]
    return node


def stories_page(items):
    """Stories page fixture: Relay preloader blob with reels_media.items."""
    payload = {
        "require": [
            [
                "ScheduledServerJS",
                "handle",
                None,
                [
                    {
                        "__bbox": {
                            "require": [
                                {
                                    "__bbox": {
                                        "result": {
                                            "data": {
                                                "xdt_api__v1__feed__reels_media": {
                                                    "reels_media": {"items": items}
                                                }
                                            }
                                        }
                                    }
                                }
                            ]
                        }
                    }
                ],
            ]
        ]
    }
    blob = json.dumps(payload, separators=(",", ":"))
    return f'<html><script type="application/json" data-sjs>{blob}</script></html>'


@pytest.fixture
def feed_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(stories, "FEEDS_DIR", str(tmp_path))
    return tmp_path


class TestParseStoriesPage:
    def test_video_story_becomes_item_with_player(self):
        items = stories.parse_stories_page(
            stories_page([story_node()]), "thebeths"
        )
        assert len(items) == 1
        item = items[0]
        assert item["id"] == "300111_1795769118"
        assert item["link"] == "https://www.instagram.com/stories/thebeths/300111/"
        assert item["title"].startswith("Story by The Beths · 2025-01-01 00:00")
        assert "<video controls" in item["content"]
        assert "https://cdn.example.com/300111_1795769118.mp4" in item["content"]
        assert item["enclosure"]["type"] == "video/mp4"
        assert item["enclosure"]["url"] == "https://cdn.example.com/300111_1795769118.mp4"
        assert item["published"].strftime("%Y-%m-%d %H:%M") == "2025-01-01 00:00"

    def test_photo_story_has_poster_only(self):
        items = stories.parse_stories_page(
            stories_page([story_node(video=False)]), "thebeths"
        )
        item = items[0]
        assert "<video" not in item["content"]
        assert '<img src="https://cdn.example.com/300111_1795769118.jpg"' in item["content"]
        assert item["enclosure"]["type"] == "image/jpeg"

    def test_account_name_and_expiry_in_content(self):
        items = stories.parse_stories_page(
            stories_page([story_node()]), "thebeths"
        )
        content = items[0]["content"]
        assert "The Beths" in content
        assert "expires" in content
        assert 'href="https://www.instagram.com/stories/thebeths/"' in content

    def test_ignores_feed_post_nodes_without_expiry(self):
        decoy = story_node()
        del decoy["expiring_at"]
        items = stories.parse_stories_page(
            stories_page([decoy, story_node(node_id="300222_1795769118")]), "thebeths"
        )
        assert [i["id"] for i in items] == ["300222_1795769118"]

    def test_dedupes_repeated_ids_across_blobs(self):
        page = stories_page([story_node()]) + stories_page([story_node()])
        items = stories.parse_stories_page(page, "thebeths")
        assert len(items) == 1

    def test_empty_page_yields_no_items(self):
        assert stories.parse_stories_page("<html></html>", "thebeths") == []

    def test_same_minute_stories_get_distinct_titles(self):
        taken = 1735689600
        items = stories.parse_stories_page(
            stories_page(
                [
                    story_node(node_id="300666_1", taken_at=taken),
                    story_node(node_id="300667_1", taken_at=taken),
                ]
            ),
            "thebeths",
        )
        titles = [i["title"] for i in items]
        assert len(set(titles)) == 2
        assert titles[0].endswith("2025-01-01 00:00")
        assert titles[1] == titles[0] + " (2)"


class TestKeepUntilCap:
    def test_same_day_stories_of_one_account_are_not_superseded(
        self, tmp_path, monkeypatch
    ):
        """Regression: merge_items' supersede filter matches on (link, date)
        and (title, date); unique deep links + timestamped titles must keep
        an older same-day story alive."""
        import common

        html_path = tmp_path / "stories.html"
        html_path.write_text(
            stories_page([story_node(node_id="300555_1", taken_at=1735603200 + 7200)]),
            encoding="utf-8",
        )
        monkeypatch.setattr(stories, "FEEDS_DIR", str(tmp_path))
        monkeypatch.setenv("INSTAGRAM_STORIES_HTML", str(html_path))
        monkeypatch.setattr(stories.time, "sleep", lambda s: None)
        older = stories.parse_stories_page(
            stories_page([story_node(node_id="300444_1", taken_at=1735603200 + 3600)]),
            "thebeths",
        )[0]
        out = tmp_path / "instagram-stories.xml"
        common.write_feed([older], str(out), 100, **stories.feed_metadata(["thebeths"]))
        assert stories.main(["thebeths"]) == 0
        xml = out.read_text(encoding="utf-8")
        assert "300444" in xml
        assert "300555" in xml


class TestMain:
    OFFLINE = {"INSTAGRAM_STORIES_HTML": None}

    def _offline(self, monkeypatch, html):
        path = self._write_html(monkeypatch, html)
        monkeypatch.setenv("INSTAGRAM_STORIES_HTML", str(path))

    def _write_html(self, monkeypatch, html):
        import tempfile, os
        fd, path = tempfile.mkstemp(suffix=".html")
        with os.fdopen(fd, "w") as f:
            f.write(html)
        monkeypatch.setattr(stories.time, "sleep", lambda s: None)
        return path

    def test_offline_build_writes_items_without_network(self, feed_dir, monkeypatch):
        self._offline(
            monkeypatch, stories_page([story_node(node_id="300333_1", username="tumvlt")])
        )

        def boom(url, **kwargs):
            raise AssertionError("offline mode must not fetch")

        monkeypatch.setattr(stories.common.creq, "get", boom)
        assert stories.main(["tumvlt"]) == 0
        xml = (feed_dir / "instagram-stories.xml").read_text(encoding="utf-8")
        assert "<title>Instagram Stories</title>" in xml
        assert "300333_1" in xml

    def test_missing_sessionid_writes_warning_feed(self, feed_dir, monkeypatch):
        monkeypatch.delenv("INSTAGRAM_STORIES_HTML", raising=False)
        monkeypatch.delenv("INSTAGRAM_SESSIONID", raising=False)

        def boom(url, **kwargs):
            raise AssertionError("must not fetch without a session")

        monkeypatch.setattr(stories.common.creq, "get", boom)
        assert stories.main(["thebeths"]) == 0
        xml = (feed_dir / "instagram-stories.xml").read_text(encoding="utf-8")
        assert "Feed build failed" in xml

    def test_fetches_story_pages_with_session_cookie(self, feed_dir, monkeypatch):
        monkeypatch.delenv("INSTAGRAM_STORIES_HTML", raising=False)
        monkeypatch.setenv("INSTAGRAM_SESSIONID", "s3cret")
        seen = {}

        def fake_fetch_direct(url, cookies=None, headers=None):
            seen["url"] = url
            seen["cookies"] = cookies
            return stories_page([story_node()])

        monkeypatch.setattr(stories.common, "fetch_direct", fake_fetch_direct)
        assert stories.main(["thebeths"]) == 0
        assert seen["url"] == "https://www.instagram.com/stories/thebeths/"
        assert seen["cookies"] == {"sessionid": "s3cret"}

    def test_one_account_failing_keeps_other_items(self, feed_dir, monkeypatch):
        monkeypatch.delenv("INSTAGRAM_STORIES_HTML", raising=False)
        monkeypatch.setenv("INSTAGRAM_SESSIONID", "s3cret")

        def fake_fetch(url, cookies=None, headers=None):
            if "deadaccount" in url:
                raise RuntimeError("HTTP Error 404: ")
            return stories_page([story_node(node_id="300444_2")])

        monkeypatch.setattr(stories, "fetch_story_page", fake_fetch)
        assert stories.main(["deadaccount", "thebeths"]) == 0
        xml = (feed_dir / "instagram-stories.xml").read_text(encoding="utf-8")
        assert "300444_2" in xml
        assert "Feed build failed" not in xml

    def test_all_accounts_failing_writes_warning_feed(self, feed_dir, monkeypatch):
        monkeypatch.delenv("INSTAGRAM_STORIES_HTML", raising=False)
        monkeypatch.setenv("INSTAGRAM_SESSIONID", "s3cret")

        def fake_fetch(url, cookies=None, headers=None):
            raise RuntimeError("HTTP Error 500: ")

        monkeypatch.setattr(stories, "fetch_story_page", fake_fetch)
        assert stories.main(["a", "b"]) == 0
        xml = (feed_dir / "instagram-stories.xml").read_text(encoding="utf-8")
        assert "Feed build failed" in xml

    def test_previous_items_survive_storyless_build(self, feed_dir, monkeypatch):
        self._offline(monkeypatch, stories_page([]))
        (feed_dir / "instagram-stories.xml").write_text(
            "<?xml version='1.0'?><rss version='2.0'><channel>"
            "<title>Instagram Stories</title><link>https://www.instagram.com/</link>"
            "<description>d</description><item><title>Story by old</title>"
            "<link>https://www.instagram.com/stories/thebeths/</link>"
            "<guid>300000_OLD</guid><pubDate>Tue, 31 Dec 2024 00:00:00 +0000</pubDate>"
            "</item></channel></rss>",
            encoding="utf-8",
        )
        assert stories.main(["thebeths"]) == 0
        xml = (feed_dir / "instagram-stories.xml").read_text(encoding="utf-8")
        assert "300000_OLD" in xml

    def test_cap_keeps_newest_items(self, feed_dir, monkeypatch):
        self._offline(
            monkeypatch,
            stories_page(
                [story_node(node_id=f"30050{i}_9", taken_at=1735689600 + i) for i in range(3)]
            ),
        )
        (feed_dir / "instagram-stories.xml").write_text(
            "<?xml version='1.0'?><rss version='2.0'><channel>"
            "<title>Instagram Stories</title><link>https://www.instagram.com/</link>"
            "<description>d</description>"
            + "".join(
                f"<item><title>old {i}</title>"
                f"<link>https://www.instagram.com/stories/x{i}/</link>"
                f"<guid>20000{i}_OLD</guid>"
                f"<pubDate>Mon, 30 Dec 2024 0{i}:00:00 +0000</pubDate></item>"
                for i in range(2)
            )
            + "</channel></rss>",
            encoding="utf-8",
        )
        monkeypatch.setattr(stories, "MAX_ITEMS", 4)
        assert stories.main(["thebeths"]) == 0
        xml = (feed_dir / "instagram-stories.xml").read_text(encoding="utf-8")
        assert "300502_9" in xml
        assert "200000_OLD" not in xml
        assert "200001_OLD" in xml
