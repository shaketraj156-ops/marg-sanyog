import pytest

from app.api.v1 import auth as auth_module
from app.config import get_settings
from app.core.ratelimit import LoginGuard


@pytest.fixture
def demo_email(monkeypatch):
    """Turns the demo login on for one account."""

    def _set(email):
        monkeypatch.setattr(get_settings(), "demo_login_email", email)

    return _set


def test_the_demo_login_is_off_unless_it_is_set_up(client, make_user):
    make_user("demo@example.test", "viewer")
    assert client.get("/api/v1/auth/demo").json() == {"enabled": False, "email": None}
    refused = client.post("/api/v1/auth/demo")
    assert refused.status_code == 404
    assert refused.json()["title"] == "demo_unavailable"


def test_the_demo_login_signs_in_as_the_read_only_account_without_a_password(client, make_user, demo_email):
    make_user("demo@example.test", "viewer", name="Demo Viewer")
    demo_email("demo@example.test")

    assert client.get("/api/v1/auth/demo").json() == {"enabled": True, "email": "demo@example.test"}
    response = client.post("/api/v1/auth/demo")
    assert response.status_code == 200
    tokens = response.json()
    assert tokens["token_type"] == "bearer"
    assert tokens["access_token"] and tokens["refresh_token"]

    me = client.get("/api/v1/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}).json()
    assert me["email"] == "demo@example.test"
    assert me["role"] == "viewer"


def test_the_demo_session_can_be_refreshed_like_any_other(client, make_user, demo_email):
    make_user("demo@example.test", "viewer")
    demo_email("demo@example.test")
    tokens = client.post("/api/v1/auth/demo").json()
    refreshed = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert refreshed.status_code == 200


def test_the_demo_session_cannot_change_anything(client, world, make_user, demo_email):
    make_user("demo@example.test", "viewer")
    demo_email("demo@example.test")
    token = client.post("/api/v1/auth/demo").json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/v1/requests", headers=headers).status_code == 200
    created = client.post(
        "/api/v1/plans",
        json={"horizon_start": "2026-10-19T00:00:00+05:30", "horizon_end": "2026-10-26T00:00:00+05:30"},
        headers=headers,
    )
    assert created.status_code == 403


@pytest.mark.parametrize("role", ["planner", "admin", "dept_user"])
def test_an_account_that_is_not_a_viewer_is_never_used_for_the_demo(client, make_user, demo_email, role):
    make_user("boss@example.test", role)
    demo_email("boss@example.test")
    assert client.get("/api/v1/auth/demo").json() == {"enabled": False, "email": None}
    assert client.post("/api/v1/auth/demo").status_code == 404


def test_an_inactive_or_unknown_account_is_not_used(client, make_user, demo_email):
    make_user("gone@example.test", "viewer", active=False)
    demo_email("gone@example.test")
    assert client.post("/api/v1/auth/demo").status_code == 404
    demo_email("nobody@example.test")
    assert client.post("/api/v1/auth/demo").status_code == 404


def test_the_demo_email_is_matched_without_regard_to_case_or_spaces(client, make_user, demo_email):
    make_user("demo@example.test", "viewer")
    demo_email("  Demo@Example.test ")
    assert client.post("/api/v1/auth/demo").status_code == 200


def test_the_demo_login_is_rate_limited_per_address(client, make_user, demo_email, monkeypatch):
    make_user("demo@example.test", "viewer")
    demo_email("demo@example.test")
    guard = LoginGuard(per_minute=2)
    monkeypatch.setattr(auth_module, "get_login_guard", lambda: guard)
    assert client.post("/api/v1/auth/demo").status_code == 200
    assert client.post("/api/v1/auth/demo").status_code == 200
    limited = client.post("/api/v1/auth/demo")
    assert limited.status_code == 429
    assert limited.json()["title"] == "rate_limited"
