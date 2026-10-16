from sqlalchemy import select

from app.core.security import verify_password
from app.db.models import Department, Section, User
from scripts.seed_synthetic import DEPARTMENTS, SECTIONS, USERS, seed


def test_seed_creates_everything(db):
    created = seed(db, "seed-password")
    assert created == {
        "departments": len(DEPARTMENTS),
        "sections": len(SECTIONS),
        "users": len(USERS),
    }
    assert {d.code for d in db.scalars(select(Department))} == {"ENGG", "TRD", "SNT"}
    assert {s.code for s in db.scalars(select(Section))} == {"A-B", "B-C", "C-D", "D-E"}


def test_seed_is_idempotent(db):
    seed(db, "seed-password")
    assert seed(db, "seed-password") == {"departments": 0, "sections": 0, "users": 0}
    assert db.query(User).count() == len(USERS)


def test_seeded_users_have_expected_roles_and_departments(db):
    seed(db, "seed-password")
    users = {u.email: u for u in db.scalars(select(User))}
    assert {u.role for u in users.values()} == {"admin", "planner", "dept_user", "viewer"}
    for email, _name, role, dept_code in USERS:
        user = users[email]
        assert user.role == role
        assert (user.department.code if user.department else None) == dept_code


def test_seeded_password_is_hashed_and_works(db):
    seed(db, "seed-password")
    user = db.scalar(select(User).where(User.email == "admin@blockplanner.test"))
    assert user.password_hash != "seed-password"
    assert verify_password(user.password_hash, "seed-password")


def test_seeded_user_can_log_in(client, db):
    seed(db, "seed-password")
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "engg@blockplanner.test", "password": "seed-password"},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    me = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"}).json()
    assert me["role"] == "dept_user"
    assert me["department"]["code"] == "ENGG"


def test_seed_main_requires_password(monkeypatch, capsys):
    from scripts import seed_synthetic

    monkeypatch.delenv("SEED_PASSWORD", raising=False)
    assert seed_synthetic.main() == 1
    assert "SEED_PASSWORD" in capsys.readouterr().err
