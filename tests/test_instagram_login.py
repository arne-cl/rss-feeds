"""Tests for scripts/instagram_login.py (pure functions, offline)."""

import os
import stat

import pytest

import build_instagram_feed as b
import check_instagram_session as check
import instagram_login as il


class _FakeResponse:
    def __init__(self, text, status=200):
        self.text = text
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            exc = Exception(f"HTTP Error {self.status_code}:")
            exc.response = self
            raise exc


class _ApiError(Exception):
    def __init__(self, status):
        super().__init__(f"HTTP Error {status}:")
        self.response = type("R", (), {"status_code": status})()


class TestReadEnvValue:
    def test_reads_value(self, tmp_path):
        path = tmp_path / "env"
        path.write_text("JINA_API_KEY=x\nINSTAGRAM_SESSIONID=abc\n")
        assert il.read_env_value(str(path)) == "abc"

    def test_missing_file(self, tmp_path):
        assert il.read_env_value(str(tmp_path / "nope")) is None

    def test_missing_key(self, tmp_path):
        path = tmp_path / "env"
        path.write_text("JINA_API_KEY=x\n")
        assert il.read_env_value(str(path)) is None

    def test_custom_key(self, tmp_path):
        path = tmp_path / "env"
        path.write_text("FOO=bar\n")
        assert il.read_env_value(str(path), key="FOO") == "bar"


class TestUpdateEnvFile:
    def test_append_to_existing(self, tmp_path):
        path = tmp_path / "env"
        path.write_text("JINA_API_KEY=x\n")
        il.update_env_file(str(path), "abc")
        assert path.read_text() == "JINA_API_KEY=x\nINSTAGRAM_SESSIONID=abc\n"

    def test_replace_existing_preserves_others(self, tmp_path):
        path = tmp_path / "env"
        path.write_text(
            "JINA_API_KEY=x\nINSTAGRAM_SESSIONID=old\nB=b\n"
            "# INSTAGRAM_SESSIONID=comment\n"
        )
        il.update_env_file(str(path), "new")
        assert (
            path.read_text()
            == "JINA_API_KEY=x\nINSTAGRAM_SESSIONID=new\nB=b\n"
            "# INSTAGRAM_SESSIONID=comment\n"
        )

    def test_creates_missing_file(self, tmp_path):
        path = tmp_path / "sub" / "env"
        il.update_env_file(str(path), "abc")
        assert path.read_text() == "INSTAGRAM_SESSIONID=abc\n"

    def test_perms_600(self, tmp_path):
        path = tmp_path / "env"
        with open(path, "w") as f:
            f.write("A=b\n")
        os.chmod(path, 0o644)
        il.update_env_file(str(path), "abc")
        assert stat.S_IMODE(path.stat().st_mode) == 0o600

    def test_idempotent(self, tmp_path):
        path = tmp_path / "env"
        path.write_text("A=b\nINSTAGRAM_SESSIONID=abc\n")
        il.update_env_file(str(path), "abc")
        assert path.read_text() == "A=b\nINSTAGRAM_SESSIONID=abc\n"


class TestPickCookie:
    def test_finds_sessionid(self):
        cookies = [
            {"name": "csrftoken", "value": "c", "domain": ".instagram.com"},
            {"name": "sessionid", "value": "s1", "domain": ".instagram.com"},
        ]
        assert il.pick_cookie(cookies) == "s1"

    def test_ignores_other_domains(self):
        cookies = [{"name": "sessionid", "value": "s", "domain": ".example.com"}]
        assert il.pick_cookie(cookies) is None

    def test_ignores_other_names(self):
        cookies = [{"name": "ds_user_id", "value": "u", "domain": ".instagram.com"}]
        assert il.pick_cookie(cookies) is None

    def test_empty(self):
        assert il.pick_cookie([]) is None


class TestVerifySessionid:
    API_SIDECAR = (
        b'{"data": {"user": {"edge_owner_to_timeline_media": '
        b'{"edges": [{"node": {"shortcode": "abc"}}, '
        b'{"node": {"shortcode": "def"}}]}}}}'
    )

    def _ok_fetch(self, monkeypatch, body):
        def fake(account, session_id=None):
            return body

        monkeypatch.setattr(b, "fetch_api_profile", fake)

    def test_ok_counts_posts(self, monkeypatch):
        self._ok_fetch(monkeypatch, self.API_SIDECAR)
        assert il.verify_sessionid("abc") == ("ok", 2)

    def test_auth_failed(self, monkeypatch):
        def fake(account, session_id=None):
            raise _ApiError(401)

        monkeypatch.setattr(b, "fetch_api_profile", fake)
        assert il.verify_sessionid("abc") == ("auth_failed", 0)

    def test_rate_limited(self, monkeypatch):
        def fake(account, session_id=None):
            raise _ApiError(429)

        monkeypatch.setattr(b, "fetch_api_profile", fake)
        assert il.verify_sessionid("abc") == ("rate_limited", 0)

    def test_error(self, monkeypatch):
        def fake(account, session_id=None):
            raise _ApiError(500)

        monkeypatch.setattr(b, "fetch_api_profile", fake)
        assert il.verify_sessionid("abc") == ("error", 0)

    def test_passes_sessionid(self, monkeypatch):
        seen = {}

        def fake(account, session_id=None):
            seen["account"] = account
            seen["session_id"] = session_id
            return b"{}"

        monkeypatch.setattr(b, "fetch_api_profile", fake)
        il.verify_sessionid("xyz", account="daxwerner")
        assert seen == {"account": "daxwerner", "session_id": "xyz"}


class TestRefreshPolicy:
    """(action, value): noop keep stored, adopt candidate, expired needs login."""

    def test_candidate_equals_stored(self):
        assert il.refresh_policy("s", "s", "ok", "ok") == ("noop", "s")

    def test_no_candidate_stored_ok(self):
        assert il.refresh_policy("s", None, "ok", None) == ("noop", "s")

    def test_no_candidate_stored_throttled(self):
        assert il.refresh_policy("s", None, "rate_limited", None) == ("noop", "s")

    def test_no_candidate_nothing_left(self):
        assert il.refresh_policy(None, None, None, None) == ("expired", None)

    def test_no_candidate_stored_dead(self):
        assert il.refresh_policy("s", None, "auth_failed", None) == ("expired", None)

    def test_candidate_ok_wins(self):
        assert il.refresh_policy("s", "n", "ok", "ok") == ("adopt", "n")

    def test_candidate_ok_over_dead_stored(self):
        assert il.refresh_policy("s", "n", "auth_failed", "ok") == ("adopt", "n")

    def test_throttled_candidate_over_dead_stored(self):
        # 429 means the cookie authenticated fine; it is the best we have
        assert il.refresh_policy("s", "n", "auth_failed", "rate_limited") == (
            "adopt",
            "n",
        )

    def test_throttled_candidate_no_stored(self):
        assert il.refresh_policy(None, "n", None, "rate_limited") == ("adopt", "n")

    def test_throttled_candidate_keeps_live_stored(self):
        assert il.refresh_policy("s", "n", "ok", "rate_limited") == ("noop", "s")

    def test_dead_candidate_live_stored(self):
        assert il.refresh_policy("s", "n", "ok", "auth_failed") == ("noop", "s")

    def test_dead_candidate_nothing_left(self):
        assert il.refresh_policy("s", "n", "auth_failed", "auth_failed") == (
            "expired",
            None,
        )

    def test_unverifiable_candidate_untouched(self):
        assert il.refresh_policy("s", "n", "ok", "error") == ("noop", "s")
        assert il.refresh_policy("s", "n", "ok", None) == ("noop", "s")


class TestWaitForSessionid:
    def test_finds_cookie(self):
        calls = []

        def cookies_fn():
            calls.append(1)
            if len(calls) < 3:
                return [{"name": "csrftoken", "value": "c", "domain": ".instagram.com"}]
            return [{"name": "sessionid", "value": "late", "domain": ".instagram.com"}]

        assert il.wait_for_sessionid(cookies_fn, timeout=10, poll=0) == "late"

    def test_timeout_returns_none(self):
        assert (
            il.wait_for_sessionid(
                lambda: [{"name": "x", "value": "y", "domain": ".instagram.com"}],
                timeout=0.05,
                poll=0.01,
            )
            is None
        )


class TestFetchApiProfileExplicitSessionid:
    """fetch_api_profile accepts an explicit session_id, falling back to env."""

    def test_explicit_wins_over_env(self, monkeypatch):
        captured = {}

        def fake_get(url, **kwargs):
            captured.update(kwargs)
            return _FakeResponse('{"data": {}}')

        monkeypatch.setattr(b.common.creq, "get", fake_get)
        monkeypatch.delenv("INSTAGRAM_SESSIONID", raising=False)

        text = b.fetch_api_profile("tiny_ruins", session_id="explicit")
        assert captured["cookies"] == {"sessionid": "explicit"}
        assert text == '{"data": {}}'

    def test_env_fallback(self, monkeypatch):
        captured = {}

        def fake_get(url, **kwargs):
            captured.update(kwargs)
            return _FakeResponse("{}")

        monkeypatch.setattr(b.common.creq, "get", fake_get)
        monkeypatch.setenv("INSTAGRAM_SESSIONID", "from-env")

        b.fetch_api_profile("tiny_ruins")
        assert captured["cookies"] == {"sessionid": "from-env"}


class TestParseArgs:
    def test_login_defaults(self):
        args = il.parse_args(["login"])
        assert args.command == "login"
        assert args.account == "tiny_ruins"
        assert args.store_throttled is False

    def test_login_store_throttled(self):
        args = il.parse_args(["login", "--store-throttled"])
        assert args.store_throttled is True

    def test_refresh_defaults(self):
        args = il.parse_args(["refresh"])
        assert args.command == "refresh"
        assert args.account == "tiny_ruins"
        assert not hasattr(args, "store_throttled")
