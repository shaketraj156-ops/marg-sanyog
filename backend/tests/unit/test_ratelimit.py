import pytest

from app.core.errors import ProblemError
from app.core.ratelimit import LoginGuard


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def guard(clock, **kwargs):
    kwargs.setdefault("max_failures", 3)
    kwargs.setdefault("lockout_seconds", 600)
    kwargs.setdefault("per_minute", 100)
    return LoginGuard(clock=clock, **kwargs)


def refused(g, email="a@x.test", address="1.1.1.1"):
    with pytest.raises(ProblemError) as err:
        g.check(email, address)
    return err.value


def fail(g, email="a@x.test", times=1):
    for _ in range(times):
        g.check(email, "1.1.1.1")
        g.record_failure(email)


# ---------- lockout ----------


def test_failures_below_the_limit_do_not_lock_anything():
    g = guard(Clock())
    fail(g, times=2)
    g.check("a@x.test", "1.1.1.1")  # still allowed


def test_the_last_allowed_failure_locks_the_account():
    g = guard(Clock())
    fail(g, times=3)
    error = refused(g)
    assert (error.status, error.code) == (429, "too_many_attempts")
    assert error.headers["Retry-After"] == "600"
    assert "600 seconds" in error.detail


def test_the_retry_after_counts_down_and_rounds_up():
    clock = Clock()
    g = guard(clock)
    fail(g, times=3)
    clock.advance(100.2)
    assert refused(g).headers["Retry-After"] == "500"
    clock.advance(499)
    assert refused(g).headers["Retry-After"] == "1"  # never zero


def test_the_lockout_ends_and_the_count_starts_afresh():
    clock = Clock()
    g = guard(clock)
    fail(g, times=3)
    clock.advance(601)
    g.check("a@x.test", "1.1.1.1")
    g.record_failure("a@x.test")
    g.check("a@x.test", "1.1.1.1")  # one failure after the lockout is not another lockout
    g.record_failure("a@x.test")
    g.check("a@x.test", "1.1.1.1")
    g.record_failure("a@x.test")  # the third one locks again
    assert refused(g).code == "too_many_attempts"


def test_a_success_clears_the_failures():
    g = guard(Clock())
    fail(g, times=2)
    g.record_success("a@x.test")
    fail(g, times=2)
    g.check("a@x.test", "1.1.1.1")  # 2 + 2 failures, but never 3 in a row


def test_old_failures_are_forgiven():
    clock = Clock()
    g = guard(clock)
    fail(g, times=2)
    clock.advance(601)
    fail(g, times=2)
    g.check("a@x.test", "1.1.1.1")  # the first two no longer count


def test_accounts_are_locked_independently():
    g = guard(Clock())
    fail(g, "a@x.test", times=3)
    g.check("b@x.test", "1.1.1.1")
    assert refused(g, "a@x.test").code == "too_many_attempts"


def test_an_email_that_does_not_exist_is_locked_the_same_way():
    """The guard knows nothing about accounts, so it cannot reveal which ones exist."""
    g = guard(Clock())
    fail(g, "nobody@x.test", times=3)
    assert refused(g, "nobody@x.test").code == "too_many_attempts"


def test_a_locked_account_is_refused_even_before_the_password_is_tried():
    g = guard(Clock())
    fail(g, times=3)
    assert refused(g).status == 429  # check() runs first, so the right password would not help


# ---------- rate limit per address ----------


def test_an_address_may_try_a_few_times_per_minute():
    clock = Clock()
    g = guard(clock, per_minute=3)
    for _ in range(3):
        g.check("a@x.test", "9.9.9.9")
    error = refused(g, address="9.9.9.9")
    assert (error.status, error.code) == (429, "rate_limited")
    assert error.headers["Retry-After"] == "60"


def test_the_rate_limit_window_slides():
    clock = Clock()
    g = guard(clock, per_minute=2)
    g.check("a@x.test", "9.9.9.9")
    clock.advance(30)
    g.check("a@x.test", "9.9.9.9")
    assert refused(g, address="9.9.9.9").headers["Retry-After"] == "30"
    clock.advance(31)  # the first attempt left the window
    g.check("a@x.test", "9.9.9.9")


def test_addresses_are_limited_independently():
    g = guard(Clock(), per_minute=1)
    g.check("a@x.test", "1.1.1.1")
    g.check("a@x.test", "2.2.2.2")
    assert refused(g, address="1.1.1.1").code == "rate_limited"


def test_a_refused_attempt_does_not_extend_the_wait():
    clock = Clock()
    g = guard(clock, per_minute=1)
    g.check("a@x.test", "9.9.9.9")
    for _ in range(5):
        refused(g, address="9.9.9.9")
    clock.advance(61)
    g.check("a@x.test", "9.9.9.9")


# ---------- housekeeping ----------


def test_old_entries_are_forgotten():
    clock = Clock()
    g = guard(clock)
    fail(g, "a@x.test", times=3)
    g.check("b@x.test", "5.5.5.5")
    clock.advance(10_000)
    g._forget_old(clock())
    assert not g._attempts and not g._failures and not g._locked_until
