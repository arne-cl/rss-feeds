"""Tests for scripts/check_instagram_session.py."""

import pytest

import build_instagram_feed
import check_instagram_session as check


class TestClassify:
    def test_ok(self):
        assert check.classify(200) == "ok"
        assert check.classify(204) == "ok"

    def test_rate_limited(self):
        assert check.classify(429) == "rate_limited"

    def test_auth_failed(self):
        assert check.classify(401) == "auth_failed"
        assert check.classify(403) == "auth_failed"

    def test_other_is_error(self):
        assert check.classify(500) == "error"
        assert check.classify(302) == "error"
        assert check.classify(0) == "error"


class TestStatusOf:
    def test_from_response_attribute(self):
        class Resp:
            status_code = 429

        class Exc(Exception):
            response = Resp()

        assert check.status_of(Exc()) == 429

    def test_from_message(self):
        assert check.status_of(Exception("HTTP Error 429: ")) == 429

    def test_unknown(self):
        assert check.status_of(Exception("no code here")) is None


class TestParseArgs:
    def test_default_account(self):
        assert check.parse_args([]).account == "tiny_ruins"

    def test_explicit_account(self):
        assert check.parse_args(["daxwerner"]).account == "daxwerner"


class TestMain:
    def test_ok(self, monkeypatch, capsys):
        monkeypatch.setenv("INSTAGRAM_SESSIONID", "dummy")
        monkeypatch.setattr(
            build_instagram_feed, "fetch_api_profile", lambda a: "{}"
        )
        monkeypatch.setattr(
            check, "count_posts", lambda text: 7
        )
        assert check.main(["daxwerner"]) == check.OK
        out = capsys.readouterr().out
        assert "ok: daxwerner" in out
        assert "7" in out

    def test_rate_limited(self, monkeypatch, capsys):
        monkeypatch.setenv("INSTAGRAM_SESSIONID", "dummy")

        def boom(account):
            raise Exception("HTTP Error 429: ")

        monkeypatch.setattr(build_instagram_feed, "fetch_api_profile", boom)
        assert check.main(["daxwerner"]) == check.RATE_LIMITED
        assert "rate_limited" in capsys.readouterr().out

    def test_auth_failed(self, monkeypatch):
        monkeypatch.setenv("INSTAGRAM_SESSIONID", "dummy")

        def boom(account):
            raise Exception("HTTP Error 401: ")

        monkeypatch.setattr(build_instagram_feed, "fetch_api_profile", boom)
        assert check.main(["daxwerner"]) == check.AUTH_FAILED

    def test_missing_sessionid(self, monkeypatch):
        monkeypatch.delenv("INSTAGRAM_SESSIONID", raising=False)
        assert check.main(["daxwerner"]) == check.NO_SESSION

    def test_invalid_account(self, monkeypatch):
        monkeypatch.setenv("INSTAGRAM_SESSIONID", "dummy")
        assert check.main(["../etc/passwd"]) == check.ERROR
