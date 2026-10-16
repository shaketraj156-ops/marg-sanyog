import json
import logging

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.core.logging import JsonFormatter, setup_logging
from app.main import app
from tests.conftest import PASSWORD


@pytest.fixture
def access(caplog):
    caplog.set_level(logging.INFO, logger="access")
    return caplog


def lines(caplog):
    return [r for r in caplog.records if r.name == "access"]


# ---------- request ids ----------


def test_every_response_carries_a_request_id(client):
    first = client.get("/health").headers["x-request-id"]
    second = client.get("/health").headers["x-request-id"]
    assert len(first) == 12 and first != second


def test_error_responses_have_a_request_id_too(client):
    assert client.get("/api/v1/me").headers["x-request-id"]  # 401
    assert client.get("/nope").headers["x-request-id"]  # 404


def test_a_safe_id_from_the_caller_is_kept(client):
    response = client.get("/health", headers={"X-Request-ID": "trace-2026.10_19"})
    assert response.headers["x-request-id"] == "trace-2026.10_19"


def test_an_unsafe_id_is_replaced(client):
    for bad in ("has spaces", "x" * 100, "semi;colon", "<script>"):
        response = client.get("/health", headers={"X-Request-ID": bad})
        assert response.headers["x-request-id"] != bad
        assert len(response.headers["x-request-id"]) == 12


# ---------- the log line ----------


def test_one_json_ready_line_per_request(client, access):
    client.get("/health", headers={"X-Request-ID": "abc123"})
    (record,) = lines(access)
    assert record.request_id == "abc123"
    assert (record.method, record.path, record.status) == ("GET", "/health", 200)
    assert record.duration_ms >= 0
    assert record.user_id is None


def test_the_signed_in_user_is_logged(client, make_user, auth_headers, access):
    user = make_user()
    client.get("/api/v1/me", headers=auth_headers())
    assert [r.user_id for r in lines(access) if r.path == "/api/v1/me"] == [user.id]


def test_failed_requests_are_logged_with_their_status(client, access):
    client.get("/api/v1/me")
    assert [r.status for r in lines(access) if r.path == "/api/v1/me"] == [401]


def test_the_json_formatter_writes_valid_json_with_the_fields(client, access):
    client.get("/health", headers={"X-Request-ID": "abc123"})
    (record,) = lines(access)
    data = json.loads(JsonFormatter().format(record))
    assert data["request_id"] == "abc123"
    assert data["level"] == "INFO" and data["logger"] == "access" and data["message"] == "request"
    assert data["path"] == "/health" and data["status"] == 200 and "ts" in data
    assert "user_id" not in data  # empty fields are left out


def test_exceptions_are_logged_with_a_traceback():
    try:
        raise ValueError("kaput")
    except ValueError:
        import sys

        record = logging.LogRecord("x", logging.ERROR, "f", 1, "failed", None, sys.exc_info())
    data = json.loads(JsonFormatter().format(record))
    assert "ValueError: kaput" in data["exc"]


def test_passwords_and_tokens_never_reach_the_logs(client, make_user, access):
    make_user()
    login = client.post("/api/v1/auth/login", json={"email": "user@example.test", "password": PASSWORD})
    token = login.json()["access_token"]
    refresh = login.json()["refresh_token"]
    client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    client.post("/api/v1/auth/login", json={"email": "user@example.test", "password": "another-secret"})
    everything = " ".join(JsonFormatter().format(r) for r in access.records) + access.text
    for secret in (PASSWORD, "another-secret", token, refresh):
        assert secret not in everything


def test_query_strings_are_not_logged(client, make_user, auth_headers, access):
    make_user()
    client.get("/api/v1/requests?status=draft&cursor=5", headers=auth_headers())
    assert all("?" not in r.path and "cursor" not in r.path for r in lines(access))


# ---------- unhandled errors ----------


def test_an_unexpected_error_becomes_a_problem_with_the_request_id(client, access):
    def broken():
        raise RuntimeError("database exploded with secret-detail")
        yield  # pragma: no cover

    app.dependency_overrides[get_db] = broken
    crashing = TestClient(app, raise_server_exceptions=False)
    response = crashing.get("/api/v1/sections", headers={"X-Request-ID": "trace-500"})
    assert response.status_code == 500
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["title"] == "internal_error" and body["request_id"] == "trace-500"
    assert "secret-detail" not in response.text  # internals are not shown to the caller
    assert any(r.levelno >= logging.ERROR and r.request_id == "trace-500" for r in lines(access))


# ---------- setup ----------


def test_setup_logging_is_idempotent_and_uses_json():
    setup_logging("INFO")
    setup_logging("WARNING")
    root = logging.getLogger()
    json_handlers = [h for h in root.handlers if h.get_name() == "json"]
    assert len(json_handlers) == 1
    assert isinstance(json_handlers[0].formatter, JsonFormatter)
    assert root.level == logging.WARNING
    setup_logging("INFO")
