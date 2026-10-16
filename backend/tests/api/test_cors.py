import pytest


def preflight(client, origin):
    return client.options(
        "/api/v1/plans",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type,idempotency-key",
        },
    )


@pytest.mark.parametrize("origin", ["http://localhost:5173", "http://127.0.0.1:5173"])
def test_the_vite_dev_server_may_call_the_api(client, origin):
    response = preflight(client, origin)
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    assert "authorization" in response.headers["access-control-allow-headers"].lower()
    assert "idempotency-key" in response.headers["access-control-allow-headers"].lower()


def test_other_origins_are_not_allowed(client):
    response = preflight(client, "http://evil.example")
    assert "access-control-allow-origin" not in response.headers


def test_simple_requests_carry_the_allow_origin_header(client):
    response = client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
