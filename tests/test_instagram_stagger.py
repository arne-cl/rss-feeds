"""Tests for scripts/instagram_stagger.py (reactive Instagram backoff)."""

import instagram_stagger as stagger


class TestNextDelay:
    def test_no_throttle_uses_default(self):
        assert stagger.next_delay(stagger.DEFAULT_DELAY, False) == 2

    def test_first_throttle_waits_45s(self):
        assert stagger.next_delay(stagger.DEFAULT_DELAY, True) == 45

    def test_repeated_throttles_double_and_cap(self):
        delay = stagger.next_delay(2, True)
        assert delay == 45
        delay = stagger.next_delay(delay, True)
        assert delay == 90
        delay = stagger.next_delay(delay, True)
        assert delay == 180
        assert stagger.next_delay(delay, True) == 180

    def test_success_keeps_cautious_delay_for_rest_of_run(self):
        assert stagger.next_delay(90, False) == 90


class TestRunAccounts:
    @staticmethod
    def run_with(outputs, failures=()):
        calls = []

        def run(account):
            calls.append(account)
            return (1 if account in failures else 0), outputs.get(account, "")

        return run, calls

    def test_no_throttle_uses_short_delay_between_accounts(self):
        run, calls = self.run_with({})
        sleeps = []
        rc = stagger.run_accounts(
            ["a", "b", "c"], run, sleeps.append, delay=stagger.DEFAULT_DELAY
        )
        assert rc == 0
        assert calls == ["a", "b", "c"]
        assert sleeps == [2, 2]

    def test_throttle_waits_and_escalates(self):
        marker = stagger.THROTTLE_MARKER
        run, calls = self.run_with({"a": marker, "b": marker, "c": marker})
        sleeps = []
        stagger.run_accounts(["a", "b", "c", "d"], run, sleeps.append, delay=2)
        assert sleeps == [45, 90, 180]

    def test_success_after_throttle_keeps_cautious_delay(self):
        marker = stagger.THROTTLE_MARKER
        run, _ = self.run_with({"a": marker, "b": ""})
        sleeps = []
        stagger.run_accounts(["a", "b", "c"], run, sleeps.append, delay=2)
        assert sleeps == [45, 45]

    def test_output_is_passed_through(self, capsys):
        run, _ = self.run_with({"a": "builder output\n"})
        stagger.run_accounts(["a"], run, lambda _: None)
        assert "builder output" in capsys.readouterr().out

    def test_failure_stops_the_run(self):
        run, calls = self.run_with({"b": "boom"}, failures=("b",))
        sleeps = []
        rc = stagger.run_accounts(["a", "b", "c"], run, sleeps.append)
        assert rc == 1
        assert calls == ["a", "b"]
        assert sleeps == [2]
