"""Role checks. No M1 endpoint is role-restricted, so these run on a small test-only app."""
from typing import Annotated

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_db, require_role
from app.api.v1 import auth
from app.core.errors import install_handlers
from app.db.models import User

ROLES = ["admin", "planner", "dept_user", "viewer"]

# route -> roles allowed, mirroring the permission table in the spec
ROUTES = {
    "/admin-only": ("admin",),
    "/planning": ("admin", "planner"),
    "/requests": ("admin", "planner", "dept_user"),
    "/anyone": tuple(ROLES),
}


@pytest.fixture
def role_client(session_factory):
    app = FastAPI()
    install_handlers(app)
    app.include_router(auth.router, prefix="/api/v1")

    def override_get_db():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    for path, roles in ROUTES.items():

        def handler(user: Annotated[User, Depends(require_role(*roles))]):
            return {"role": user.role}

        app.get(path)(handler)

    return TestClient(app)


def _token(client, email, password):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.mark.parametrize("path", ROUTES)
@pytest.mark.parametrize("role", ROLES)
def test_role_matrix(role, path, role_client, make_user, make_department):
    department = make_department()
    make_user(
        email=f"{role}@example.test",
        role=role,
        department=department if role == "dept_user" else None,
    )
    headers = _token(role_client, f"{role}@example.test", "correct-horse-battery")
    response = role_client.get(path, headers=headers)
    if role in ROUTES[path]:
        assert response.status_code == 200
        assert response.json() == {"role": role}
    else:
        assert response.status_code == 403
        assert response.json()["title"] == "forbidden"
        assert response.headers["content-type"].startswith("application/problem+json")


@pytest.mark.parametrize("path", ROUTES)
def test_no_token_is_401_not_403(path, role_client):
    assert role_client.get(path).status_code == 401


def test_role_is_read_from_the_database_not_the_token(
    role_client, make_user, db
):
    user = make_user(role="admin")
    headers = _token(role_client, user.email, "correct-horse-battery")
    assert role_client.get("/admin-only", headers=headers).status_code == 200
    user.role = "viewer"
    db.commit()
    assert role_client.get("/admin-only", headers=headers).status_code == 403
