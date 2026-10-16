import pytest

ROLES = ["admin", "planner", "dept_user", "viewer"]


def test_sections_require_login(client):
    assert client.get("/api/v1/sections").status_code == 401
    assert client.get("/api/v1/sections/1").status_code == 401


def test_departments_require_login(client):
    assert client.get("/api/v1/departments").status_code == 401


@pytest.mark.parametrize("role", ROLES)
def test_every_role_can_read_reference_data(
    role, client, make_user, make_department, make_section, auth_headers
):
    department = make_department()
    make_section()
    make_user(role=role, department=department if role == "dept_user" else None)
    headers = auth_headers()
    assert client.get("/api/v1/sections", headers=headers).status_code == 200
    assert client.get("/api/v1/departments", headers=headers).status_code == 200


def test_sections_are_listed_by_code(client, make_user, make_section, auth_headers):
    make_section("C-D", "C to D", "DIV-1", 1)
    make_section("A-B", "A to B", "DIV-1", 2)
    make_user()
    response = client.get("/api/v1/sections", headers=auth_headers())
    assert [s["code"] for s in response.json()] == ["A-B", "C-D"]
    assert set(response.json()[0]) == {"id", "code", "name", "division", "line_count"}


def test_get_one_section(client, make_user, make_section, auth_headers):
    section = make_section("B-C", "B to C", "DIV-2", 1)
    make_user()
    response = client.get(f"/api/v1/sections/{section.id}", headers=auth_headers())
    assert response.status_code == 200
    assert response.json() == {
        "id": section.id,
        "code": "B-C",
        "name": "B to C",
        "division": "DIV-2",
        "line_count": 1,
    }


def test_missing_section_is_404_problem(client, make_user, auth_headers):
    make_user()
    response = client.get("/api/v1/sections/9999", headers=auth_headers())
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["title"] == "not_found"


def test_non_numeric_section_id_is_422(client, make_user, auth_headers):
    make_user()
    assert client.get("/api/v1/sections/abc", headers=auth_headers()).status_code == 422


def test_departments_are_listed_by_code(client, make_user, make_department, auth_headers):
    make_department("TRD", "Traction Distribution")
    make_department("ENGG", "Engineering")
    make_user()
    response = client.get("/api/v1/departments", headers=auth_headers())
    assert [d["code"] for d in response.json()] == ["ENGG", "TRD"]
