"""Tests for scripts/status.py."""

from datetime import datetime, timedelta, timezone

import pytest

import status


UTC = timezone.utc
NOW = datetime(2026, 10, 9, 21, 0, 0, tzinfo=UTC)


def write_feed(path, items=3, warnings=0, last_build=None, newest=None):
    """Write a small RSS file shaped like the generated feeds."""
    if last_build is None:
        last_build = NOW - timedelta(days=2)
    if newest is None:
        newest = NOW - timedelta(days=5)
    lines = [
        "<?xml version='1.0' encoding='UTF-8'?>",
        "<rss version='2.0'><channel>",
        f"<lastBuildDate>{last_build:%a, %d %b %Y %H:%M:%S +0000}</lastBuildDate>",
    ]
    for i in range(items):
        lines += [
            "<item>",
            f"<guid>https://example.com/{i}</guid>",
            f"<pubDate>{newest:%a, %d %b %Y %H:%M:%S +0000}</pubDate>",
            "</item>",
        ]
    for i in range(warnings):
        lines += [
            "<item>",
            "<title>Feed build failed</title>",
            f"<guid>https://example.com/{i}#build-status</guid>",
            f"<pubDate>{last_build:%a, %d %b %Y %H:%M:%S +0000}</pubDate>",
            "</item>",
        ]
    lines += ["</channel></rss>"]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


class TestFeedSummary:
    def test_counts_items_and_finds_no_warnings(self, tmp_path):
        summary = status.feed_summary(str(write_feed(tmp_path / "f.xml")))
        assert summary["items"] == 3
        assert summary["warnings"] == 0
        assert summary["last_build"] == NOW - timedelta(days=2)
        assert summary["newest"] == NOW - timedelta(days=5)

    def test_counts_warning_items(self, tmp_path):
        summary = status.feed_summary(
            str(write_feed(tmp_path / "f.xml", items=2, warnings=1))
        )
        assert summary["items"] == 3
        assert summary["warnings"] == 1

    def test_missing_file(self, tmp_path):
        assert status.feed_summary(str(tmp_path / "nope.xml")) is None

    def test_unparseable_file(self, tmp_path):
        path = tmp_path / "broken.xml"
        path.write_text("not xml at all <<<", encoding="utf-8")
        assert status.feed_summary(str(path)) is None

    def test_missing_dates(self, tmp_path):
        path = tmp_path / "f.xml"
        path.write_text(
            "<rss version='2.0'><channel><item><guid>x</guid></item>"
            "</channel></rss>",
            encoding="utf-8",
        )
        summary = status.feed_summary(str(path))
        assert summary["items"] == 1
        assert summary["warnings"] == 0
        assert summary["last_build"] is None
        assert summary["newest"] is None


class TestStaleness:
    def test_none(self):
        assert status.staleness(NOW, None) == "never"

    def test_minutes(self):
        assert status.staleness(NOW, NOW - timedelta(minutes=5)) == "5m ago"

    def test_hours(self):
        assert status.staleness(NOW, NOW - timedelta(hours=7)) == "7h ago"

    def test_days(self):
        assert status.staleness(NOW, NOW - timedelta(days=3)) == "3d ago"

    def test_future_date_clamps_to_now(self):
        assert status.staleness(NOW, NOW + timedelta(hours=2)) == "now"

    def test_naive_date_treated_as_utc(self):
        naive = datetime(2026, 10, 9, 20, 55, 0)
        assert status.staleness(NOW, naive) == "5m ago"


class TestLastUpdateRun:
    def test_parses_git_log_line(self):
        def run(argv):
            return 0, "abc1234\x002026-10-07T18:23:25+02:00\x00Update feeds: slides\n"

        info = status.last_update_run(run)
        assert info["hash"] == "abc1234"
        assert info["subject"] == "Update feeds: slides"
        assert info["date"] == datetime(
            2026, 10, 7, 18, 23, 25, tzinfo=timezone(timedelta(hours=2))
        )

    def test_no_matching_commit(self):
        assert status.last_update_run(lambda argv: (0, "")) is None

    def test_unparseable_date_keeps_rest(self):
        def run(argv):
            return 0, "abc1234\x00not-a-date\x00Update feeds\n"

        info = status.last_update_run(run)
        assert info["hash"] == "abc1234"
        assert info["date"] is None


class TestTimerState:
    def test_enabled_with_next_elapse(self):
        calls = []

        def run(argv):
            calls.append(argv)
            if "is-enabled" in argv:
                return 0, "enabled\n"
            return 0, str(int(NOW.timestamp() * 1_000_000)) + "\n"

        state, next_elapse = status.timer_state(run)
        assert state == "enabled"
        assert next_elapse is not None

    def test_disabled_unit_is_inactive(self):
        def run(argv):
            return 1, "disabled\n"

        assert status.timer_state(run) == ("inactive", None)

    def test_missing_unit_is_inactive(self):
        def run(argv):
            return 1, "not-found\n"

        assert status.timer_state(run) == ("inactive", None)

    def test_no_bus_is_unknown(self):
        def run(argv):
            return 1, ""

        assert status.timer_state(run) == ("unknown", None)

    def test_no_systemctl_binary_is_unknown(self):
        def run(argv):
            raise FileNotFoundError("systemctl")

        assert status.timer_state(run) == ("unknown", None)


class TestLoadEnvFile:
    def test_parses_key_value(self, tmp_path):
        path = tmp_path / "env"
        path.write_text(
            "JINA_API_KEY=abc123\n"
            "# comment\n"
            "\n"
            "INSTAGRAM_SESSIONID=def456\n",
            encoding="utf-8",
        )
        assert status.load_env_file(str(path)) == {
            "JINA_API_KEY": "abc123",
            "INSTAGRAM_SESSIONID": "def456",
        }

    def test_missing_file(self, tmp_path):
        assert status.load_env_file(str(tmp_path / "nope")) == {}


class TestMain:
    def make_feeds(self, tmp_path, warnings=0):
        feeds = tmp_path / "feeds"
        feeds.mkdir()
        write_feed(feeds / "a.xml", warnings=warnings)
        write_feed(feeds / "b.xml")
        return feeds

    def fake_runners(self, monkeypatch, tmp_path, timer=("enabled", "soon")):
        monkeypatch.setattr(status, "last_update_run", lambda run=None: {
            "hash": "abc1234",
            "date": NOW - timedelta(hours=2),
            "subject": "Update feeds",
        })
        monkeypatch.setattr(status, "timer_state", lambda run=None: timer)
        monkeypatch.setattr(status, "repo_root", lambda: tmp_path)

    def test_healthy_exit_zero(self, monkeypatch, capsys, tmp_path):
        self.make_feeds(tmp_path)
        self.fake_runners(monkeypatch, tmp_path)
        assert status.main([]) == 0
        out = capsys.readouterr().out
        assert "a.xml" in out and "b.xml" in out
        assert "failed feeds: 0" in out

    def test_warning_items_exit_one(self, monkeypatch, capsys, tmp_path):
        self.make_feeds(tmp_path, warnings=1)
        self.fake_runners(monkeypatch, tmp_path)
        assert status.main([]) == 1
        out = capsys.readouterr().out
        assert "failed feeds: 1" in out

    def test_timer_inactive_exit_two_even_with_failures(
        self, monkeypatch, capsys, tmp_path
    ):
        self.make_feeds(tmp_path, warnings=1)
        self.fake_runners(
            monkeypatch, tmp_path, timer=("inactive", None)
        )
        assert status.main([]) == 2

    def test_timer_unknown_does_not_fail(self, monkeypatch, capsys, tmp_path):
        self.make_feeds(tmp_path)
        self.fake_runners(monkeypatch, tmp_path, timer=("unknown", None))
        assert status.main([]) == 0

    def test_check_session_failure_exits_one(self, monkeypatch, capsys, tmp_path):
        self.make_feeds(tmp_path)
        self.fake_runners(monkeypatch, tmp_path)
        monkeypatch.setattr(
            status, "run_session_check", lambda account: (3, "auth_failed: x\n")
        )
        assert status.main(["--check-session"]) == 1
        out = capsys.readouterr().out
        assert "instagram session: auth_failed" in out

    def test_check_session_ok(self, monkeypatch, capsys, tmp_path):
        self.make_feeds(tmp_path)
        self.fake_runners(monkeypatch, tmp_path)
        monkeypatch.setattr(
            status, "run_session_check", lambda account: (0, "ok: tiny_ruins — 7 post(s) parsed\n")
        )
        assert status.main(["--check-session"]) == 0
        out = capsys.readouterr().out
        assert "instagram session: ok" in out
