"""Tests for the Quora feed builder (scripts/build_quora_feed.py)."""

import json
import logging

import build_quora_feed as bq


def qtext(text):
    """A Quora qtext document rendering to exactly `text`."""
    return json.dumps({"sections": [{"spans": [{"text": text}]}]})


def answer_page(answer):
    """Profile page HTML embedding one Answer in the inline JSON store."""
    return "<html><body><script>x.push(%s)</script></body></html>" % json.dumps(
        json.dumps(answer)
    )


DIRECT_PAGE = answer_page(
    {
        "__typename": "Answer",
        "permaUrl": "/Why-is-OOP/answer/Alan-Kay-11",
        "creationTime": 1726743600000000,
        "question": {"title": qtext("What is OOP?")},
        "content": qtext("Objects are fictions."),
    }
)


def redirect_output(monkeypatch, tmp_path):
    monkeypatch.setattr(bq, "OUTPUT_PATH", str(tmp_path / "alankay-quora.xml"))


def use_page(monkeypatch, tmp_path, html):
    """Serve `html` as a local page copy via QUORA_PROFILE_HTML."""
    path = tmp_path / "page.html"
    path.write_text(html, encoding="utf-8")
    monkeypatch.setenv("QUORA_PROFILE_HTML", str(path))


class TestMain:
    def test_offline_run_writes_feed(self, tmp_path, monkeypatch):
        use_page(monkeypatch, tmp_path, DIRECT_PAGE)
        redirect_output(monkeypatch, tmp_path)
        assert bq.main() == 0

        xml = (tmp_path / "alankay-quora.xml").read_text(encoding="utf-8")
        assert xml.count("<item>") == 1
        assert "<title>Alan Kay on Quora</title>" in xml
        assert "<title>What is OOP?</title>" in xml
        assert "https://www.quora.com/Why-is-OOP/answer/Alan-Kay-11" in xml


class TestFailureWarning:
    """Soft failures must end up as an item inside the feed, exit 0."""

    @staticmethod
    def _fail_fetch(monkeypatch, message="direct fetch exploded"):
        def boom(*args, **kwargs):
            raise RuntimeError(message)

        monkeypatch.setattr(bq.common, "fetch_page", boom)

    def test_fetch_failure_writes_warning_feed_and_exits_zero(
        self, tmp_path, monkeypatch, capsys
    ):
        monkeypatch.delenv("QUORA_PROFILE_HTML", raising=False)
        self._fail_fetch(monkeypatch)
        redirect_output(monkeypatch, tmp_path)
        assert bq.main() == 0

        xml = (tmp_path / "alankay-quora.xml").read_text(encoding="utf-8")
        assert "<title>Feed build failed</title>" in xml
        assert "direct fetch exploded" in xml
        assert "Traceback (most recent call last)" in xml
        assert "<pubDate>" in xml
        assert capsys.readouterr().out.count("::warning::") == 1

    def test_jina_rate_limit_page_writes_warning_feed(self, tmp_path, monkeypatch):
        """The CI scenario: fetch_page falls back to jina, which serves an
        error page that yields zero answers."""
        monkeypatch.delenv("QUORA_PROFILE_HTML", raising=False)
        monkeypatch.setattr(
            bq.common,
            "fetch_page",
            lambda *a, **k: ("<html>rate limit exceeded</html>", "jina"),
        )
        redirect_output(monkeypatch, tmp_path)
        assert bq.main() == 0

        xml = (tmp_path / "alankay-quora.xml").read_text(encoding="utf-8")
        assert "<title>Feed build failed</title>" in xml

    def test_jina_fallback_failure_writes_warning_feed(self, tmp_path, monkeypatch):
        monkeypatch.delenv("QUORA_PROFILE_HTML", raising=False)
        monkeypatch.setattr(
            bq.common,
            "fetch_page",
            lambda *a, **k: ("<html>no answers here</html>", "direct"),
        )

        def boom(url):
            raise RuntimeError("jina exploded")

        monkeypatch.setattr(bq.common, "fetch_jina", boom)
        redirect_output(monkeypatch, tmp_path)
        assert bq.main() == 0

        xml = (tmp_path / "alankay-quora.xml").read_text(encoding="utf-8")
        assert "<title>Feed build failed</title>" in xml
        assert "jina exploded" in xml

    def test_repeated_failure_replaces_warning_entry(self, tmp_path, monkeypatch):
        monkeypatch.delenv("QUORA_PROFILE_HTML", raising=False)
        self._fail_fetch(monkeypatch)
        redirect_output(monkeypatch, tmp_path)
        assert bq.main() == 0
        assert bq.main() == 0

        xml = (tmp_path / "alankay-quora.xml").read_text(encoding="utf-8")
        assert xml.count("<item>") == 1
        assert xml.count("Feed build failed") == 1

    def test_failure_keeps_previous_items(self, tmp_path, monkeypatch):
        use_page(monkeypatch, tmp_path, DIRECT_PAGE)
        redirect_output(monkeypatch, tmp_path)
        assert bq.main() == 0

        monkeypatch.delenv("QUORA_PROFILE_HTML")
        self._fail_fetch(monkeypatch)
        assert bq.main() == 0

        xml = (tmp_path / "alankay-quora.xml").read_text(encoding="utf-8")
        assert xml.count("<item>") == 2
        assert "<title>Feed build failed</title>" in xml
        assert "<title>What is OOP?</title>" in xml

    def test_success_removes_stale_warning(self, tmp_path, monkeypatch):
        common_mod = bq.common
        real_fetch_page = common_mod.fetch_page
        monkeypatch.delenv("QUORA_PROFILE_HTML", raising=False)
        self._fail_fetch(monkeypatch)
        redirect_output(monkeypatch, tmp_path)
        assert bq.main() == 0

        monkeypatch.setattr(common_mod, "fetch_page", real_fetch_page)
        use_page(monkeypatch, tmp_path, DIRECT_PAGE)
        assert bq.main() == 0

        xml = (tmp_path / "alankay-quora.xml").read_text(encoding="utf-8")
        assert xml.count("<item>") == 1
        assert "Feed build failed" not in xml

    def test_unparseable_page_writes_warning_feed_without_jina(
        self, tmp_path, monkeypatch
    ):
        """Offline runs must never touch the network, even on bad pages."""

        def no_network(url):
            raise AssertionError(f"network fetch attempted: {url}")

        use_page(monkeypatch, tmp_path, "<html>login wall</html>")
        monkeypatch.setattr(bq.common, "fetch_jina", no_network)
        redirect_output(monkeypatch, tmp_path)
        assert bq.main() == 0

        xml = (tmp_path / "alankay-quora.xml").read_text(encoding="utf-8")
        assert "<title>Feed build failed</title>" in xml
        assert xml.count("<item>") == 1

    def test_zero_item_parse_logs_page_excerpt(self, tmp_path, monkeypatch, caplog):
        """The CI failure showed only '0 answers'; log what was actually
        fetched so rate-limiting and layout changes are distinguishable."""
        monkeypatch.delenv("QUORA_PROFILE_HTML", raising=False)
        monkeypatch.setattr(
            bq.common,
            "fetch_page",
            lambda *a, **k: ("<html>some rate limit notice</html>", "jina"),
        )
        redirect_output(monkeypatch, tmp_path)
        with caplog.at_level(logging.ERROR, logger="build_quora_feed"):
            assert bq.main() == 0
        assert "some rate limit notice" in caplog.text
