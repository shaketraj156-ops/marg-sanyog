import pytest
from sqlalchemy.exc import IntegrityError

from app.db.models import Department, Section, User


def _user(**overrides):
    values = {"email": "a@example.test", "name": "A", "password_hash": "x", "role": "viewer"}
    values.update(overrides)
    return User(**values)


def _fails(db, obj):
    db.add(obj)
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_user_email_is_unique(db):
    db.add(_user())
    db.commit()
    _fails(db, _user(name="B"))


def test_user_role_must_be_known(db):
    _fails(db, _user(role="superuser"))


@pytest.mark.parametrize("role", ["admin", "planner", "dept_user", "viewer"])
def test_user_known_roles_are_accepted(db, role):
    db.add(_user(role=role))
    db.commit()


def test_user_department_must_exist(db):
    _fails(db, _user(department_id=999))


def test_user_defaults(db):
    db.add(_user())
    db.commit()
    user = db.query(User).one()
    assert user.is_active is True
    assert user.created_at is not None
    assert user.department is None


def test_department_code_is_unique(db):
    db.add(Department(code="ENGG", name="Engineering"))
    db.commit()
    _fails(db, Department(code="ENGG", name="Other"))


def test_section_code_is_unique(db):
    db.add(Section(code="A-B", name="x", division="D", line_count=1))
    db.commit()
    _fails(db, Section(code="A-B", name="y", division="D", line_count=2))


@pytest.mark.parametrize("line_count", [0, 3])
def test_section_line_count_must_be_one_or_two(db, line_count):
    _fails(db, Section(code="X-Y", name="x", division="D", line_count=line_count))


@pytest.mark.parametrize("line_count", [1, 2])
def test_section_line_count_one_or_two_is_accepted(db, line_count):
    db.add(Section(code="X-Y", name="x", division="D", line_count=line_count))
    db.commit()
