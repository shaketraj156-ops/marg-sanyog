"""Seed synthetic reference data and demo users. Idempotent: existing rows are left alone.

Usage (from backend/ or inside the api container):
    SEED_PASSWORD=<password> python -m scripts.seed_synthetic

Every demo user gets the password from SEED_PASSWORD. Nothing is hardcoded here.
"""
import os
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.models import Department, Section, User
from app.db.session import get_session

DEPARTMENTS = [
    ("ENGG", "Engineering"),
    ("TRD", "Traction Distribution"),
    ("SNT", "Signal and Telecom"),
]

# Same four sections as the planner prototype.
SECTIONS = [
    ("A-B", "A to B", "DIV-1", 2),
    ("B-C", "B to C", "DIV-1", 2),
    ("C-D", "C to D", "DIV-1", 1),
    ("D-E", "D to E", "DIV-1", 2),
]

# (email, name, role, department code)
USERS = [
    ("admin@blockplanner.test", "Demo Admin", "admin", None),
    ("planner@blockplanner.test", "Demo Planner", "planner", None),
    ("engg@blockplanner.test", "Demo Engineering", "dept_user", "ENGG"),
    ("trd@blockplanner.test", "Demo Traction", "dept_user", "TRD"),
    ("snt@blockplanner.test", "Demo Signal and Telecom", "dept_user", "SNT"),
    ("viewer@blockplanner.test", "Demo Viewer", "viewer", None),
]


def seed(db: Session, password: str) -> dict[str, int]:
    """Create whatever is missing. Returns how many rows were created per table."""
    created = {"departments": 0, "sections": 0, "users": 0}

    for code, name in DEPARTMENTS:
        if db.scalar(select(Department).where(Department.code == code)) is None:
            db.add(Department(code=code, name=name))
            created["departments"] += 1
    db.flush()
    departments = {d.code: d.id for d in db.scalars(select(Department))}

    for code, name, division, line_count in SECTIONS:
        if db.scalar(select(Section).where(Section.code == code)) is None:
            db.add(Section(code=code, name=name, division=division, line_count=line_count))
            created["sections"] += 1

    for email, name, role, dept_code in USERS:
        if db.scalar(select(User).where(User.email == email)) is None:
            db.add(
                User(
                    email=email,
                    name=name,
                    role=role,
                    password_hash=hash_password(password),
                    department_id=departments[dept_code] if dept_code else None,
                )
            )
            created["users"] += 1

    db.commit()
    return created


def main() -> int:
    password = os.environ.get("SEED_PASSWORD")
    if not password:
        print("Set SEED_PASSWORD to the password for the demo users.", file=sys.stderr)
        return 1
    with get_session() as db:
        print("created:", seed(db, password))
    return 0


if __name__ == "__main__":
    sys.exit(main())
