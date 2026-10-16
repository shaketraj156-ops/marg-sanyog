import pytest

from app.db.models import AuditLog, BlockRequest
from tests.conftest import request_body

URL = "/api/v1/requests"


# ---------- create ----------


def test_dept_user_creates_a_draft(client, world):
    response = client.post(URL, json=request_body(), headers=world.h("engg"))
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "draft"
    assert body["version"] == 1
    assert body["department"] == "ENGG"
    assert body["section_code"] == "A-B"
    assert body["duration_minutes"] == 180
    assert body["dependencies"] == []
    assert body["warnings"] == []
    assert body["created_at"].endswith("+05:30")


def test_planner_must_name_the_department(client, world):
    response = client.post(URL, json=request_body(), headers=world.h("planner"))
    assert response.status_code == 422
    assert response.json()["errors"][0]["field"] == "department_code"


@pytest.mark.parametrize("who", ["planner", "admin"])
def test_planner_and_admin_can_create_for_a_department(client, world, who):
    response = client.post(URL, json=request_body(department_code="TRD"), headers=world.h(who))
    assert response.status_code == 201
    assert response.json()["department"] == "TRD"


def test_unknown_department_code_is_422(client, world):
    response = client.post(URL, json=request_body(department_code="NOPE"), headers=world.h("admin"))
    assert response.status_code == 422
    assert response.json()["title"] == "unknown_department"


def test_dept_user_cannot_create_for_another_department(client, world):
    response = client.post(URL, json=request_body(department_code="TRD"), headers=world.h("engg"))
    assert response.status_code == 403
    assert response.json()["title"] == "forbidden"


def test_dept_user_may_name_their_own_department(client, world):
    response = client.post(URL, json=request_body(department_code="ENGG"), headers=world.h("engg"))
    assert response.status_code == 201


def test_viewer_cannot_create(client, world):
    assert client.post(URL, json=request_body(), headers=world.h("viewer")).status_code == 403


def test_create_needs_login(client, world):
    assert client.post(URL, json=request_body()).status_code == 401


def test_unknown_section(client, world):
    response = client.post(URL, json=request_body(section_code="Z-Z"), headers=world.h("engg"))
    assert response.status_code == 422
    assert response.json()["title"] == "unknown_section"


@pytest.mark.parametrize(
    ("overrides", "field", "message"),
    [
        ({"duration_minutes": 10}, "duration_minutes", "greater than or equal to 15"),
        ({"duration_minutes": 361}, "duration_minutes", "less than or equal to 360"),
        ({"priority": 0}, "priority", "greater than or equal to 1"),
        ({"priority": 4}, "priority", "less than or equal to 3"),
        ({"work_type": "magic"}, "work_type", "Input should be"),
        (
            {"earliest_date": "2026-10-23", "deadline_date": "2026-10-19"},
            "(whole request)",
            "deadline_date must not be before earliest_date",
        ),
        ({"preferred_start": "2026-10-19T08:00:00"}, "preferred_start", "UTC offset"),
        ({"earliest_date": "not-a-date"}, "earliest_date", "date"),
    ],
)
def test_validation_errors(client, world, overrides, field, message):
    response = client.post(URL, json=request_body(**overrides), headers=world.h("engg"))
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    errors = response.json()["errors"]
    assert any(e["field"] == field and message in e["message"] for e in errors), errors


def test_unknown_fields_are_rejected(client, world):
    response = client.post(URL, json=request_body(status="published"), headers=world.h("engg"))
    assert response.status_code == 422


def test_boundary_durations_are_accepted(client, world):
    for minutes in (15, 360):
        response = client.post(
            URL, json=request_body(duration_minutes=minutes), headers=world.h("engg")
        )
        assert response.status_code == 201


def test_same_day_window_is_valid(client, world):
    response = client.post(
        URL,
        json=request_body(earliest_date="2026-10-19", deadline_date="2026-10-19"),
        headers=world.h("engg"),
    )
    assert response.status_code == 201


def test_preferred_start_is_returned_in_ist(client, world):
    response = client.post(
        URL,
        json=request_body(preferred_start="2026-10-19T02:30:00+00:00"),
        headers=world.h("engg"),
    )
    assert response.json()["preferred_start"] == "2026-10-19T08:00:00+05:30"


def test_duplicate_request_gives_a_warning_not_an_error(client, world, create_request):
    first = create_request("engg")
    response = client.post(URL, json=request_body(), headers=world.h("engg"))
    assert response.status_code == 201
    warning = response.json()["warnings"][0]
    assert warning["code"] == "duplicate_request"
    assert warning["request_ids"] == [first["id"]]


def test_no_duplicate_warning_for_other_department_or_dates(client, world, create_request):
    create_request("engg")
    other_dept = client.post(URL, json=request_body(), headers=world.h("trd"))
    other_dates = client.post(
        URL,
        json=request_body(earliest_date="2026-11-01", deadline_date="2026-11-02"),
        headers=world.h("engg"),
    )
    assert other_dept.json()["warnings"] == []
    assert other_dates.json()["warnings"] == []


# ---------- read ----------


def test_get_one_request(client, world, create_request):
    created = create_request("engg")
    response = client.get(f"{URL}/{created['id']}", headers=world.h("viewer"))
    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


def test_get_missing_request_is_404(client, world):
    response = client.get(f"{URL}/999", headers=world.h("viewer"))
    assert response.status_code == 404
    assert response.json()["title"] == "not_found"


def test_departments_can_read_each_others_requests(client, world, create_request):
    created = create_request("engg")
    assert client.get(f"{URL}/{created['id']}", headers=world.h("trd")).status_code == 200


def test_list_filters(client, world, create_request, submit_request):
    create_request("engg", section_code="A-B")
    submit_request("trd", section_code="B-C")
    create_request("trd", section_code="B-C", earliest_date="2026-12-01", deadline_date="2026-12-05")

    def ids(**params):
        response = client.get(URL, params=params, headers=world.h("viewer"))
        assert response.status_code == 200
        return [r["id"] for r in response.json()["items"]]

    assert len(ids()) == 3
    assert len(ids(status="submitted")) == 1
    assert len(ids(status="draft")) == 2
    assert len(ids(section="B-C")) == 2
    assert len(ids(department="ENGG")) == 1
    assert len(ids(date_from="2026-11-30")) == 1
    assert len(ids(date_to="2026-10-31")) == 2
    assert len(ids(section="B-C", department="TRD", status="submitted")) == 1


def test_list_pagination(client, world, create_request):
    for _ in range(5):
        create_request("engg")
    first = client.get(URL, params={"limit": 2}, headers=world.h("viewer")).json()
    assert len(first["items"]) == 2
    assert first["next_cursor"] == first["items"][-1]["id"]
    second = client.get(
        URL, params={"limit": 2, "cursor": first["next_cursor"]}, headers=world.h("viewer")
    ).json()
    assert [r["id"] for r in second["items"]] == [3, 4]
    last = client.get(
        URL, params={"limit": 2, "cursor": second["next_cursor"]}, headers=world.h("viewer")
    ).json()
    assert [r["id"] for r in last["items"]] == [5]
    assert last["next_cursor"] is None


def test_list_limit_is_bounded(client, world):
    assert client.get(URL, params={"limit": 0}, headers=world.h("viewer")).status_code == 422
    assert client.get(URL, params={"limit": 1000}, headers=world.h("viewer")).status_code == 422


def test_list_needs_login(client):
    assert client.get(URL).status_code == 401


# ---------- update ----------


def test_patch_updates_and_bumps_the_version(client, world, create_request):
    created = create_request("engg")
    response = client.patch(
        f"{URL}/{created['id']}",
        json={"version": 1, "duration_minutes": 120, "priority": 1},
        headers=world.h("engg"),
    )
    assert response.status_code == 200
    body = response.json()
    assert (body["duration_minutes"], body["priority"], body["version"]) == (120, 1, 2)


def test_patch_needs_a_version(client, world, create_request):
    created = create_request("engg")
    response = client.patch(
        f"{URL}/{created['id']}", json={"priority": 1}, headers=world.h("engg")
    )
    assert response.status_code == 422


def test_patch_with_stale_version_is_409(client, world, create_request):
    created = create_request("engg")
    ok = client.patch(
        f"{URL}/{created['id']}", json={"version": 1, "priority": 2}, headers=world.h("engg")
    )
    assert ok.status_code == 200
    stale = client.patch(
        f"{URL}/{created['id']}", json={"version": 1, "priority": 1}, headers=world.h("engg")
    )
    assert stale.status_code == 409
    assert stale.json()["title"] == "version_conflict"
    assert client.get(f"{URL}/{created['id']}", headers=world.h("engg")).json()["priority"] == 2


def test_patch_cannot_change_status(client, world, create_request):
    created = create_request("engg")
    response = client.patch(
        f"{URL}/{created['id']}",
        json={"version": 1, "status": "published"},
        headers=world.h("engg"),
    )
    assert response.status_code == 422


def test_patch_other_departments_request_is_403(client, world, create_request):
    created = create_request("engg")
    response = client.patch(
        f"{URL}/{created['id']}", json={"version": 1, "priority": 1}, headers=world.h("trd")
    )
    assert response.status_code == 403


@pytest.mark.parametrize("who", ["planner", "admin"])
def test_planner_and_admin_can_patch_any_request(client, world, create_request, who):
    created = create_request("engg")
    response = client.patch(
        f"{URL}/{created['id']}", json={"version": 1, "priority": 1}, headers=world.h(who)
    )
    assert response.status_code == 200


def test_patch_viewer_is_403(client, world, create_request):
    created = create_request("engg")
    response = client.patch(
        f"{URL}/{created['id']}", json={"version": 1, "priority": 1}, headers=world.h("viewer")
    )
    assert response.status_code == 403


def test_patch_a_submitted_request_is_allowed(client, world, submit_request):
    submitted = submit_request("engg")
    response = client.patch(
        f"{URL}/{submitted['id']}",
        json={"version": submitted["version"], "priority": 1},
        headers=world.h("engg"),
    )
    assert response.status_code == 200
    assert response.json()["status"] == "submitted"


@pytest.mark.parametrize("status", ["scheduled", "published", "cancelled", "rejected"])
def test_patch_other_states_is_409(client, world, create_request, db, status):
    created = create_request("engg")
    db.get(BlockRequest, created["id"]).status = status
    db.commit()
    response = client.patch(
        f"{URL}/{created['id']}",
        json={"version": created["version"] + 1, "priority": 1},
        headers=world.h("engg"),
    )
    assert response.status_code == 409
    assert response.json()["title"] == "invalid_state"


def test_patch_date_order_is_checked_against_stored_values(client, world, create_request):
    created = create_request("engg")  # window 2026-10-19 .. 2026-10-23
    response = client.patch(
        f"{URL}/{created['id']}",
        json={"version": 1, "earliest_date": "2026-10-30"},
        headers=world.h("engg"),
    )
    assert response.status_code == 422
    assert response.json()["errors"][0]["field"] == "deadline_date"


def test_patch_validates_duration_and_section(client, world, create_request):
    created = create_request("engg")
    too_long = client.patch(
        f"{URL}/{created['id']}", json={"version": 1, "duration_minutes": 400}, headers=world.h("engg")
    )
    bad_section = client.patch(
        f"{URL}/{created['id']}", json={"version": 1, "section_code": "Z-Z"}, headers=world.h("engg")
    )
    assert too_long.status_code == 422
    assert bad_section.status_code == 422
    assert bad_section.json()["title"] == "unknown_section"


def test_patch_can_move_section_and_clear_preferred_start(client, world, create_request):
    created = create_request("engg", preferred_start="2026-10-19T08:00:00+05:30")
    response = client.patch(
        f"{URL}/{created['id']}",
        json={"version": 1, "section_code": "B-C", "preferred_start": None},
        headers=world.h("engg"),
    )
    assert response.status_code == 200
    assert response.json()["section_code"] == "B-C"
    assert response.json()["preferred_start"] is None


def test_empty_patch_changes_nothing(client, world, create_request):
    created = create_request("engg")
    response = client.patch(f"{URL}/{created['id']}", json={"version": 1}, headers=world.h("engg"))
    assert response.status_code == 200
    assert response.json()["version"] == 1


def test_patch_can_not_null_required_fields(client, world, create_request):
    created = create_request("engg")
    response = client.patch(
        f"{URL}/{created['id']}", json={"version": 1, "priority": None}, headers=world.h("engg")
    )
    assert response.status_code == 422


# ---------- submit / cancel / reject ----------


def test_submit_moves_draft_to_submitted(client, world, create_request):
    created = create_request("engg")
    response = client.post(f"{URL}/{created['id']}/submit", headers=world.h("engg"))
    assert response.status_code == 200
    assert response.json()["status"] == "submitted"
    assert response.json()["version"] == 2


def test_submit_twice_is_409(client, world, submit_request):
    submitted = submit_request("engg")
    response = client.post(f"{URL}/{submitted['id']}/submit", headers=world.h("engg"))
    assert response.status_code == 409
    assert response.json()["title"] == "invalid_transition"


def test_submit_other_department_is_403(client, world, create_request):
    created = create_request("engg")
    assert client.post(f"{URL}/{created['id']}/submit", headers=world.h("trd")).status_code == 403


def test_submit_with_version(client, world, create_request):
    created = create_request("engg")
    stale = client.post(
        f"{URL}/{created['id']}/submit", json={"version": 5}, headers=world.h("engg")
    )
    ok = client.post(f"{URL}/{created['id']}/submit", json={"version": 1}, headers=world.h("engg"))
    assert stale.status_code == 409
    assert ok.status_code == 200


def test_submit_fails_if_a_dependency_was_cancelled_since(client, world, create_request):
    first = create_request("engg")
    second = create_request("engg", section_code="B-C")
    client.put(
        f"{URL}/{second['id']}/dependencies",
        json={"dependencies": [{"depends_on": first["id"]}]},
        headers=world.h("engg"),
    )
    client.post(f"{URL}/{first['id']}/cancel", headers=world.h("engg"))
    response = client.post(f"{URL}/{second['id']}/submit", headers=world.h("engg"))
    assert response.status_code == 422
    assert response.json()["title"] == "unknown_dependency"


@pytest.mark.parametrize("start", ["draft", "submitted", "scheduled"])
def test_cancel_from_allowed_states(client, world, create_request, db, start):
    created = create_request("engg")
    db.get(BlockRequest, created["id"]).status = start
    db.commit()
    response = client.post(f"{URL}/{created['id']}/cancel", headers=world.h("engg"))
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


@pytest.mark.parametrize("start", ["published", "completed", "cancelled", "rejected"])
def test_cancel_from_other_states_is_409(client, world, create_request, db, start):
    created = create_request("engg")
    db.get(BlockRequest, created["id"]).status = start
    db.commit()
    response = client.post(f"{URL}/{created['id']}/cancel", headers=world.h("engg"))
    assert response.status_code == 409
    assert response.json()["title"] == "invalid_transition"


def test_cancel_other_department_is_403(client, world, create_request):
    created = create_request("engg")
    assert client.post(f"{URL}/{created['id']}/cancel", headers=world.h("trd")).status_code == 403


def test_viewer_cannot_cancel_or_submit(client, world, create_request):
    created = create_request("engg")
    assert client.post(f"{URL}/{created['id']}/cancel", headers=world.h("viewer")).status_code == 403
    assert client.post(f"{URL}/{created['id']}/submit", headers=world.h("viewer")).status_code == 403


def test_planner_rejects_a_submitted_request(client, world, submit_request):
    submitted = submit_request("engg")
    response = client.post(
        f"{URL}/{submitted['id']}/reject", json={"reason": "No crew"}, headers=world.h("planner")
    )
    assert response.status_code == 200
    assert response.json()["status"] == "rejected"


def test_dept_user_cannot_reject(client, world, submit_request):
    submitted = submit_request("engg")
    response = client.post(
        f"{URL}/{submitted['id']}/reject", json={"reason": "x"}, headers=world.h("engg")
    )
    assert response.status_code == 403


def test_reject_needs_a_reason_and_a_submitted_request(client, world, create_request):
    created = create_request("engg")
    no_reason = client.post(f"{URL}/{created['id']}/reject", json={}, headers=world.h("planner"))
    draft = client.post(
        f"{URL}/{created['id']}/reject", json={"reason": "no"}, headers=world.h("planner")
    )
    assert no_reason.status_code == 422
    assert draft.status_code == 409


# ---------- dependencies ----------


def _deps(client, world, request_id, targets, who="engg", **extra):
    return client.put(
        f"{URL}/{request_id}/dependencies",
        json={"dependencies": targets, **extra},
        headers=world.h(who),
    )


def test_set_and_replace_dependencies(client, world, create_request):
    a, b, c = (create_request("engg", section_code="A-B") for _ in range(3))
    response = _deps(
        client,
        world,
        c["id"],
        [
            {"depends_on": a["id"], "relation": "finish_before_start", "min_gap_minutes": 30},
            {"depends_on": b["id"], "relation": "not_same_block"},
        ],
    )
    assert response.status_code == 200
    assert response.json()["dependencies"] == [
        {"depends_on": a["id"], "relation": "finish_before_start", "min_gap_minutes": 30},
        {"depends_on": b["id"], "relation": "not_same_block", "min_gap_minutes": 0},
    ]
    replaced = _deps(client, world, c["id"], [{"depends_on": b["id"]}])
    assert [d["depends_on"] for d in replaced.json()["dependencies"]] == [b["id"]]
    cleared = _deps(client, world, c["id"], [])
    assert cleared.json()["dependencies"] == []


def test_dependencies_are_shown_on_get(client, world, create_request):
    a, b = create_request("engg"), create_request("engg")
    _deps(client, world, b["id"], [{"depends_on": a["id"]}])
    got = client.get(f"{URL}/{b['id']}", headers=world.h("viewer")).json()
    assert got["dependencies"][0]["depends_on"] == a["id"]


def test_dependency_may_point_at_another_departments_request(client, world, create_request):
    trd = create_request("trd")
    engg = create_request("engg")
    assert _deps(client, world, engg["id"], [{"depends_on": trd["id"]}]).status_code == 200


def test_direct_cycle_is_rejected(client, world, create_request):
    a, b = create_request("engg"), create_request("engg")
    assert _deps(client, world, b["id"], [{"depends_on": a["id"]}]).status_code == 200
    response = _deps(client, world, a["id"], [{"depends_on": b["id"]}])
    assert response.status_code == 422
    assert response.json()["title"] == "dependency_cycle"
    assert f"R{a['id']} -> R{b['id']} -> R{a['id']}" in response.json()["detail"]


def test_indirect_cycle_is_rejected(client, world, create_request):
    a, b, c = (create_request("engg") for _ in range(3))
    assert _deps(client, world, b["id"], [{"depends_on": a["id"]}]).status_code == 200
    assert _deps(client, world, c["id"], [{"depends_on": b["id"]}]).status_code == 200
    response = _deps(client, world, a["id"], [{"depends_on": c["id"]}])
    assert response.status_code == 422
    assert response.json()["title"] == "dependency_cycle"


def test_rejected_cycle_leaves_dependencies_unchanged(client, world, create_request):
    a, b = create_request("engg"), create_request("engg")
    _deps(client, world, b["id"], [{"depends_on": a["id"]}])
    _deps(client, world, a["id"], [{"depends_on": b["id"]}])
    assert client.get(f"{URL}/{a['id']}", headers=world.h("engg")).json()["dependencies"] == []


def test_replacing_dependencies_can_reverse_an_edge(client, world, create_request):
    a, b = create_request("engg"), create_request("engg")
    _deps(client, world, b["id"], [{"depends_on": a["id"]}])
    _deps(client, world, b["id"], [])
    assert _deps(client, world, a["id"], [{"depends_on": b["id"]}]).status_code == 200


def test_self_dependency_is_a_cycle(client, world, create_request):
    a = create_request("engg")
    response = _deps(client, world, a["id"], [{"depends_on": a["id"]}])
    assert response.status_code == 422
    assert response.json()["title"] == "dependency_cycle"


def test_unknown_dependency(client, world, create_request):
    a = create_request("engg")
    response = _deps(client, world, a["id"], [{"depends_on": 999}])
    assert response.status_code == 422
    assert response.json()["title"] == "unknown_dependency"


def test_dependency_on_cancelled_request_is_rejected(client, world, create_request):
    a, b = create_request("engg"), create_request("engg")
    client.post(f"{URL}/{b['id']}/cancel", headers=world.h("engg"))
    response = _deps(client, world, a["id"], [{"depends_on": b["id"]}])
    assert response.status_code == 422
    assert response.json()["title"] == "unknown_dependency"


def test_duplicate_dependency_targets_are_rejected(client, world, create_request):
    a, b = create_request("engg"), create_request("engg")
    response = _deps(client, world, a["id"], [{"depends_on": b["id"]}, {"depends_on": b["id"]}])
    assert response.status_code == 422


def test_bad_relation_is_rejected(client, world, create_request):
    a, b = create_request("engg"), create_request("engg")
    response = _deps(client, world, a["id"], [{"depends_on": b["id"], "relation": "whenever"}])
    assert response.status_code == 422


def test_dependencies_of_other_department_is_403(client, world, create_request):
    a, b = create_request("engg"), create_request("engg")
    assert _deps(client, world, a["id"], [{"depends_on": b["id"]}], who="trd").status_code == 403


def test_viewer_cannot_set_dependencies(client, world, create_request):
    a, b = create_request("engg"), create_request("engg")
    assert _deps(client, world, a["id"], [{"depends_on": b["id"]}], who="viewer").status_code == 403


def test_dependencies_on_a_scheduled_request_are_locked(client, world, create_request, db):
    a, b = create_request("engg"), create_request("engg")
    db.get(BlockRequest, a["id"]).status = "scheduled"
    db.commit()
    response = _deps(client, world, a["id"], [{"depends_on": b["id"]}])
    assert response.status_code == 409


def test_dependency_version_conflict(client, world, create_request):
    a, b = create_request("engg"), create_request("engg")
    response = _deps(client, world, a["id"], [{"depends_on": b["id"]}], version=9)
    assert response.status_code == 409
    assert response.json()["title"] == "version_conflict"


def test_deleting_a_request_removes_its_dependency_rows(client, world, create_request, db):
    a, b = create_request("engg"), create_request("engg")
    _deps(client, world, b["id"], [{"depends_on": a["id"]}])
    db.delete(db.get(BlockRequest, b["id"]))
    db.commit()
    from app.db.models import RequestDependency

    assert db.query(RequestDependency).count() == 0


# ---------- audit log ----------


def _audit(db, action=None):
    query = db.query(AuditLog).order_by(AuditLog.id)
    if action:
        query = query.filter(AuditLog.action == action)
    return query.all()


def test_every_state_change_is_audited(client, world, create_request, db):
    a, b = create_request("engg"), create_request("engg")
    client.patch(f"{URL}/{a['id']}", json={"version": 1, "priority": 1}, headers=world.h("engg"))
    _deps(client, world, a["id"], [{"depends_on": b["id"]}], version=2)
    client.post(f"{URL}/{a['id']}/submit", headers=world.h("engg"))
    client.post(f"{URL}/{a['id']}/reject", json={"reason": "No crew"}, headers=world.h("planner"))
    client.post(f"{URL}/{b['id']}/cancel", headers=world.h("engg"))

    actions = [row.action for row in _audit(db)]
    assert actions == [
        "request.create",
        "request.create",
        "request.update",
        "request.dependencies",
        "request.submit",
        "request.reject",
        "request.cancel",
    ]


def test_audit_rows_record_who_what_and_details(client, world, create_request, db):
    created = create_request("engg")
    client.patch(
        f"{URL}/{created['id']}", json={"version": 1, "priority": 1}, headers=world.h("planner")
    )
    create_row, update_row = _audit(db)
    assert create_row.user_id == db.get(BlockRequest, created["id"]).requested_by
    assert create_row.entity == "block_request"
    assert create_row.entity_id == created["id"]
    assert create_row.details["section"] == "A-B"
    assert update_row.details == {"changes": {"priority": [3, 1]}}
    assert update_row.user_id != create_row.user_id
    assert update_row.ts is not None


def test_reject_reason_is_audited(client, world, submit_request, db):
    submitted = submit_request("engg")
    client.post(
        f"{URL}/{submitted['id']}/reject", json={"reason": "No crew"}, headers=world.h("planner")
    )
    assert _audit(db, "request.reject")[0].details == {"reason": "No crew"}


def test_failed_actions_are_not_audited(client, world, create_request, db):
    created = create_request("engg")
    client.post(f"{URL}/{created['id']}/cancel", headers=world.h("trd"))  # 403
    client.patch(f"{URL}/{created['id']}", json={"version": 7, "priority": 1}, headers=world.h("engg"))  # 409
    client.post(f"{URL}/{created['id']}/reject", json={"reason": "x"}, headers=world.h("planner"))  # 409
    assert [r.action for r in _audit(db)] == ["request.create"]


def test_nothing_is_audited_by_reads(client, world, create_request, db):
    created = create_request("engg")
    client.get(f"{URL}/{created['id']}", headers=world.h("viewer"))
    client.get(URL, headers=world.h("viewer"))
    assert len(_audit(db)) == 1
