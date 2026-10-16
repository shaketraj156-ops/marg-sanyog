import jwt

from app.config import get_settings
from app.core.security import ALGORITHM, create_access_token, create_refresh_token
from app.db.models import RefreshToken
from tests.conftest import PASSWORD


def test_login_success_returns_token_pair(client, make_user, login):
    make_user()
    response = login()
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == get_settings().access_token_minutes * 60
    assert body["access_token"] and body["refresh_token"]


def test_login_email_is_case_insensitive_and_trimmed(client, make_user, login):
    make_user(email="user@example.test")
    assert login("  USER@Example.Test ", PASSWORD).status_code == 200


def test_login_stores_only_the_jti(client, make_user, login, db):
    make_user()
    token = login().json()["refresh_token"]
    rows = db.query(RefreshToken).all()
    assert len(rows) == 1
    assert rows[0].jti in jwt.decode(token, options={"verify_signature": False})["jti"]
    assert token not in (rows[0].jti, str(rows[0].user_id))


def test_login_failures_are_indistinguishable(client, make_user, login):
    make_user(email="active@example.test")
    make_user(email="inactive@example.test", active=False)
    wrong_password = login("active@example.test", "nope")
    unknown_user = login("ghost@example.test", PASSWORD)
    inactive = login("inactive@example.test", PASSWORD)
    for response in (wrong_password, unknown_user, inactive):
        assert response.status_code == 401
        assert response.headers["content-type"].startswith("application/problem+json")
    bodies = {r.text for r in (wrong_password, unknown_user, inactive)}
    assert len(bodies) == 1
    assert wrong_password.json()["title"] == "invalid_credentials"


def test_login_validation_error_uses_problem_format(client):
    response = client.post("/api/v1/auth/login", json={"email": "not-an-email", "password": ""})
    assert response.status_code == 422
    body = response.json()
    assert body["title"] == "validation"
    assert {e["field"] for e in body["errors"]} == {"email", "password"}


def test_login_with_missing_body_is_422(client):
    assert client.post("/api/v1/auth/login").status_code == 422


def test_refresh_rotates_the_token(client, make_user, login):
    make_user()
    first = login().json()
    response = client.post("/api/v1/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert response.status_code == 200
    second = response.json()
    assert second["refresh_token"] != first["refresh_token"]
    me = client.get("/api/v1/me", headers={"Authorization": f"Bearer {second['access_token']}"})
    assert me.status_code == 200


def test_refresh_token_cannot_be_reused(client, make_user, login):
    make_user()
    first = login().json()
    body = {"refresh_token": first["refresh_token"]}
    assert client.post("/api/v1/auth/refresh", json=body).status_code == 200
    reuse = client.post("/api/v1/auth/refresh", json=body)
    assert reuse.status_code == 401
    assert reuse.json()["title"] == "invalid_token"


def test_new_refresh_token_works_after_rotation(client, make_user, login):
    make_user()
    first = login().json()
    second = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": first["refresh_token"]}
    ).json()
    third = client.post("/api/v1/auth/refresh", json={"refresh_token": second["refresh_token"]})
    assert third.status_code == 200


def test_access_token_is_not_a_refresh_token(client, make_user, login):
    make_user()
    access = login().json()["access_token"]
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": access}).status_code == 401


def test_unknown_refresh_token_is_rejected(client, make_user):
    user = make_user()
    token, _, _ = create_refresh_token(user.id)  # validly signed but never stored
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": token}).status_code == 401


def test_refresh_token_with_another_secret_is_rejected(client):
    forged = jwt.encode(
        {"sub": "1", "type": "refresh", "jti": "x", "exp": 9999999999},
        "some-other-secret-that-is-also-long-enough-123456",
        algorithm=ALGORITHM,
    )
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": forged}).status_code == 401


def test_refresh_fails_for_deactivated_user(client, make_user, login, db):
    user = make_user()
    tokens = login().json()
    user.is_active = False
    db.commit()
    response = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert response.status_code == 401


def test_me_returns_user_with_department(client, make_user, make_department, auth_headers):
    department = make_department("TRD", "Traction Distribution")
    make_user(role="dept_user", department=department, name="Asha")
    response = client.get("/api/v1/me", headers=auth_headers())
    assert response.status_code == 200
    assert response.json() == {
        "id": response.json()["id"],
        "email": "user@example.test",
        "name": "Asha",
        "role": "dept_user",
        "department": {"id": department.id, "code": "TRD", "name": "Traction Distribution"},
    }
    assert "password_hash" not in response.text


def test_me_for_user_without_department(client, make_user, auth_headers):
    make_user(role="planner")
    assert client.get("/api/v1/me", headers=auth_headers()).json()["department"] is None


def test_me_without_token_is_401(client):
    response = client.get("/api/v1/me")
    assert response.status_code == 401
    assert response.json()["title"] == "not_authenticated"
    assert response.headers["www-authenticate"] == "Bearer"


def test_me_with_garbage_token_is_401(client):
    response = client.get("/api/v1/me", headers={"Authorization": "Bearer garbage"})
    assert response.status_code == 401
    assert response.json()["title"] == "invalid_token"


def test_me_with_expired_token_is_401(client, make_user):
    from datetime import timedelta

    user = make_user()
    token = create_access_token(user.id, lifetime=timedelta(seconds=-5))
    response = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert response.json()["title"] == "token_expired"


def test_me_rejects_refresh_token(client, make_user, login):
    make_user()
    refresh = login().json()["refresh_token"]
    response = client.get("/api/v1/me", headers={"Authorization": f"Bearer {refresh}"})
    assert response.status_code == 401


def test_deactivated_user_loses_access_immediately(client, make_user, auth_headers, db):
    user = make_user()
    headers = auth_headers()
    assert client.get("/api/v1/me", headers=headers).status_code == 200
    user.is_active = False
    db.commit()
    assert client.get("/api/v1/me", headers=headers).status_code == 401


def test_token_for_deleted_user_is_401(client, make_user, auth_headers, db):
    user = make_user()
    headers = auth_headers()
    db.query(RefreshToken).delete()
    db.delete(user)
    db.commit()
    assert client.get("/api/v1/me", headers=headers).status_code == 401


def test_unknown_route_uses_problem_format(client):
    response = client.get("/api/v1/nope")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["title"] == "not_found"
