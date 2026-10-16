import pytest

from app.api.v1 import auth as auth_module
from app.core.ratelimit import LoginGuard
from tests.conftest import PASSWORD
from tests.unit.test_ratelimit import Clock


@pytest.fixture
def clock(monkeypatch):
    clock = Clock()
    guard = LoginGuard(max_failures=3, lockout_seconds=600, per_minute=100, clock=clock)
    monkeypatch.setattr(auth_module, "get_login_guard", lambda: guard)
    return clock


def attempt(client, email, password):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def test_repeated_wrong_passwords_lock_the_account(client, make_user, clock):
    make_user()
    for _ in range(3):
        assert attempt(client, "user@example.test", "wrong").status_code == 401
    locked = attempt(client, "user@example.test", "wrong")
    assert locked.status_code == 429
    assert locked.headers["content-type"].startswith("application/problem+json")
    assert locked.json()["title"] == "too_many_attempts"
    assert locked.headers["retry-after"] == "600"


def test_the_right_password_does_not_get_past_a_lockout(client, make_user, clock):
    make_user()
    for _ in range(3):
        attempt(client, "user@example.test", "wrong")
    assert attempt(client, "user@example.test", PASSWORD).status_code == 429


def test_the_account_works_again_when_the_lockout_ends(client, make_user, clock):
    make_user()
    for _ in range(3):
        attempt(client, "user@example.test", "wrong")
    clock.advance(601)
    assert attempt(client, "user@example.test", PASSWORD).status_code == 200


def test_unknown_emails_are_locked_exactly_like_real_ones(client, make_user, clock):
    make_user()
    for _ in range(3):
        assert attempt(client, "ghost@example.test", "wrong").status_code == 401
    ghost = attempt(client, "ghost@example.test", "wrong")
    for _ in range(3):
        attempt(client, "user@example.test", "wrong")
    real = attempt(client, "user@example.test", "wrong")
    assert (ghost.status_code, ghost.json()["title"]) == (real.status_code, real.json()["title"]) == (429, "too_many_attempts")


def test_a_success_resets_the_count(client, make_user, clock):
    make_user()
    for _ in range(2):
        attempt(client, "user@example.test", "wrong")
    assert attempt(client, "user@example.test", PASSWORD).status_code == 200
    for _ in range(2):
        attempt(client, "user@example.test", "wrong")
    assert attempt(client, "user@example.test", PASSWORD).status_code == 200


def test_one_account_being_locked_does_not_affect_another(client, make_user, clock):
    make_user("a@example.test")
    make_user("b@example.test")
    for _ in range(3):
        attempt(client, "a@example.test", "wrong")
    assert attempt(client, "b@example.test", PASSWORD).status_code == 200


def test_email_case_and_spaces_do_not_dodge_the_lockout(client, make_user, clock):
    make_user()
    for email in ("user@example.test", "USER@example.test", "  user@Example.test "):
        attempt(client, email, "wrong")
    assert attempt(client, "user@example.test", PASSWORD).status_code == 429


def test_validation_errors_do_not_count_as_failures(client, make_user, clock):
    make_user()
    for _ in range(5):
        assert attempt(client, "user@example.test", "").status_code == 422
    assert attempt(client, "user@example.test", PASSWORD).status_code == 200


def test_the_address_rate_limit(client, make_user, monkeypatch):
    clock = Clock()
    guard = LoginGuard(max_failures=100, lockout_seconds=600, per_minute=3, clock=clock)
    monkeypatch.setattr(auth_module, "get_login_guard", lambda: guard)
    make_user()
    for _ in range(3):
        assert attempt(client, "user@example.test", PASSWORD).status_code == 200
    limited = attempt(client, "user@example.test", PASSWORD)
    assert limited.status_code == 429
    assert limited.json()["title"] == "rate_limited"
    assert int(limited.headers["retry-after"]) >= 1
    clock.advance(61)
    assert attempt(client, "user@example.test", PASSWORD).status_code == 200


def test_other_endpoints_are_not_affected_by_a_lockout(client, make_user, clock, auth_headers):
    make_user()
    headers = auth_headers()
    for _ in range(3):
        attempt(client, "user@example.test", "wrong")
    assert client.get("/api/v1/me", headers=headers).status_code == 200


def test_the_real_guard_uses_the_settings(monkeypatch):
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "login_max_failures", 7)
    monkeypatch.setattr(settings, "login_lockout_seconds", 123)
    monkeypatch.setattr(settings, "login_rate_limit_per_minute", 9)
    auth_module.get_login_guard.cache_clear()
    guard = auth_module.get_login_guard()
    assert (guard.max_failures, guard.lockout_seconds, guard.per_minute) == (7, 123, 9)
