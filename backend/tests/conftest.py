"""Test fixtures.

Tests run on in-memory SQLite by default. To run the same suite against Postgres, point
TEST_DATABASE_URL at a throwaway database: tables are created at the start of the session,
dropped at the end, and emptied after every test.
"""
import functools
import os

# Must be set before app modules read settings.
os.environ["JWT_SECRET"] = "test-only-secret-key-that-is-long-enough-0123456789"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.core.security import hash_password
from app.db.base import Base
from app.db.models import Department, Section, User
from app.main import app

PASSWORD = "correct-horse-battery"


@functools.cache
def _hash(password: str) -> str:
    return hash_password(password)  # argon2 is slow on purpose; hash each password once


def _sqlite_foreign_keys_on(dbapi_connection, _record):
    dbapi_connection.execute("PRAGMA foreign_keys=ON")


@pytest.fixture(scope="session")
def engine():
    url = os.environ.get("TEST_DATABASE_URL")
    if url:
        eng = create_engine(url)
    else:
        eng = create_engine(
            "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
        )
        event.listen(eng, "connect", _sqlite_foreign_keys_on)
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture
def session_factory(engine):
    yield sessionmaker(bind=engine, expire_on_commit=False)
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())


@pytest.fixture
def db(session_factory):
    with session_factory() as session:
        yield session


@pytest.fixture
def client(session_factory):
    def override_get_db():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def make_department(db):
    def _make(code="ENGG", name="Engineering"):
        department = Department(code=code, name=name)
        db.add(department)
        db.commit()
        return department

    return _make


@pytest.fixture
def make_section(db):
    def _make(code="A-B", name="A to B", division="DIV-1", line_count=2):
        section = Section(code=code, name=name, division=division, line_count=line_count)
        db.add(section)
        db.commit()
        return section

    return _make


@pytest.fixture
def make_user(db):
    def _make(
        email="user@example.test",
        role="viewer",
        department=None,
        password=PASSWORD,
        active=True,
        name="Test User",
    ):
        user = User(
            email=email,
            name=name,
            role=role,
            password_hash=_hash(password),
            department_id=department.id if department else None,
            is_active=active,
        )
        db.add(user)
        db.commit()
        return user

    return _make


@pytest.fixture
def login(client):
    def _login(email="user@example.test", password=PASSWORD):
        return client.post("/api/v1/auth/login", json={"email": email, "password": password})

    return _login


@pytest.fixture
def auth_headers(login):
    def _headers(email="user@example.test", password=PASSWORD):
        response = login(email, password)
        assert response.status_code == 200, response.text
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    return _headers


class World:
    """Departments, sections and one user per role, with lazily created auth headers."""

    def __init__(self, auth_headers, departments):
        self._auth_headers = auth_headers
        self._cache = {}
        self.departments = departments

    def h(self, name):
        if name not in self._cache:
            self._cache[name] = self._auth_headers(f"{name}@example.test")
        return self._cache[name]


@pytest.fixture
def world(make_department, make_section, make_user, auth_headers):
    departments = {
        code: make_department(code, name)
        for code, name in [("ENGG", "Engineering"), ("TRD", "Traction"), ("SNT", "Signal")]
    }
    for code in ("A-B", "B-C", "C-D", "D-E"):
        make_section(code, code.replace("-", " to "), "DIV-1", 2)
    make_user("engg@example.test", "dept_user", departments["ENGG"])
    make_user("trd@example.test", "dept_user", departments["TRD"])
    make_user("snt@example.test", "dept_user", departments["SNT"])
    make_user("planner@example.test", "planner")
    make_user("admin@example.test", "admin")
    make_user("viewer@example.test", "viewer")
    return World(auth_headers, departments)


def request_body(**overrides):
    body = {
        "section_code": "A-B",
        "work_type": "track",
        "duration_minutes": 180,
        "earliest_date": "2026-10-19",
        "deadline_date": "2026-10-23",
        "priority": 3,
    }
    body.update(overrides)
    return body


@pytest.fixture
def create_request(client, world):
    def _create(who="engg", **overrides):
        response = client.post("/api/v1/requests", json=request_body(**overrides), headers=world.h(who))
        assert response.status_code == 201, response.text
        return response.json()

    return _create


@pytest.fixture
def submit_request(client, world, create_request):
    def _submit(who="engg", **overrides):
        created = create_request(who, **overrides)
        response = client.post(f"/api/v1/requests/{created['id']}/submit", headers=world.h(who))
        assert response.status_code == 200, response.text
        return response.json()

    return _submit
