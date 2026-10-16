from datetime import date

import pytest

from app.db.models import (
    AuditLog,
    Block,
    BlockRequest,
    Explanation,
    PlanAssignment,
    PlanRun,
)
from app.db.models.explanation import EXPLANATION_CODES
from tests.conftest import HORIZON

PLANS = "/api/v1/plans"
ONE_DAY = {"earliest_date": "2026-10-19", "deadline_date": "2026-10-19"}


def run_plan(client, world, who="planner", **overrides):
    response = client.post(PLANS, json={**HORIZON, **overrides}, headers=world.h(who))
    assert response.status_code == 202, response.text
    return response.json()["id"]


def get(client, world, path, who="viewer", **params):
    return client.get(path, params=params, headers=world.h(who))


def explanations(client, world, plan_id, **params):
    response = get(client, world, f"{PLANS}/{plan_id}/explanations", **params)
    assert response.status_code == 200, response.text
    return response.json()["items"]


def move(client, world, path, body, who="planner"):
    return client.post(path, json=body, headers=world.h(who))


def request_status(client, world, request_id):
    return get(client, world, f"/api/v1/requests/{request_id}").json()["status"]


@pytest.fixture
def trio(submit_request, inline_planner):
    """Three departments asking for the same section on the same days."""
    return [submit_request(who, duration_minutes=120) for who in ("engg", "trd", "snt")]


@pytest.fixture
def pair(submit_request, inline_planner):
    """Two departments on one section, one day only."""
    return [
        submit_request("engg", duration_minutes=120, **ONE_DAY),
        submit_request("trd", duration_minutes=120, **ONE_DAY),
    ]


# ---------- explanations ----------


def test_merged_explanation_reconciles_with_the_metrics(client, world, trio):
    plan_id = run_plan(client, world)
    plan = get(client, world, f"{PLANS}/{plan_id}").json()
    (merged,) = [e for e in explanations(client, world, plan_id) if e["code"] == "MERGED"]
    baseline, integrated = plan["metrics"]["baseline"], plan["metrics"]["integrated"]
    assert merged["numbers"]["requests"] == sorted(r["id"] for r in trio)
    assert merged["numbers"]["closures_avoided"] == baseline["closures"] - integrated["closures"]
    assert merged["numbers"]["block_hours_saved"] == pytest.approx(
        baseline["block_hours"] - integrated["block_hours"]
    )
    ids = ", ".join(f"R{i}" for i in merged["numbers"]["requests"][:-1])
    assert merged["text"].startswith(f"{ids} and R{merged['numbers']['requests'][-1]} share one block on A-B")
    block = get(client, world, f"{PLANS}/{plan_id}/schedule").json()["blocks"][0]
    assert merged["block_id"] == block["id"]


def test_low_traffic_explanation_uses_the_stored_profile(client, world, submit_request, inline_planner):
    client.post("/api/v1/traffic/synthetic", json={"seed": 1}, headers=world.h("planner"))
    client.post(
        "/api/v1/traffic/rebuild",
        json={"date_from": "2026-10-19", "date_to": "2026-10-25"},
        headers=world.h("planner"),
    )
    submit_request("engg", duration_minutes=120, **ONE_DAY)
    plan_id = run_plan(client, world)
    (low,) = [e for e in explanations(client, world, plan_id) if e["code"] == "LOW_TRAFFIC"]
    assert low["numbers"]["quietest_percent"] <= 25
    assert low["numbers"]["feasible_windows"] == 45  # 48 slots, 4-slot window, one day
    block = get(client, world, f"{PLANS}/{plan_id}/schedule").json()["blocks"][0]
    assert low["numbers"]["trains_in_window"] == block["trains_affected"]
    assert "quietest" in low["text"]


def test_no_low_traffic_explanation_without_traffic(client, world, pair):
    plan_id = run_plan(client, world)
    assert [e for e in explanations(client, world, plan_id) if e["code"] == "LOW_TRAFFIC"] == []


def test_dependency_and_deadline_explanations(client, world, submit_request, inline_planner):
    first = submit_request("engg", duration_minutes=360, **ONE_DAY)
    second = submit_request("trd", duration_minutes=120, section_code="B-C")
    client.put(
        f"/api/v1/requests/{second['id']}/dependencies",
        json={"dependencies": [{"depends_on": first["id"], "min_gap_minutes": 1440}]},
        headers=world.h("trd"),
    )
    plan_id = run_plan(client, world)
    items = explanations(client, world, plan_id)
    (order,) = [e for e in items if e["code"] == "DEPENDENCY_ORDER"]
    assert order["request_id"] == second["id"]
    assert order["numbers"]["before"] == first["id"] and order["numbers"]["after"] == second["id"]
    assert order["numbers"]["required_gap_minutes"] == 1440
    assert order["numbers"]["actual_gap_minutes"] >= 1440
    (late,) = [e for e in items if e["code"] == "DEADLINE_DRIVEN"]
    assert late["request_id"] == second["id"]
    assert late["numbers"]["days_postponed"] >= 1


def test_deferred_explanations(client, world, submit_request, inline_planner, db):
    far = submit_request("engg", earliest_date="2026-12-01", deadline_date="2026-12-05")
    long_one = submit_request("trd", section_code="B-C")
    db.get(BlockRequest, long_one["id"]).duration_minutes = 480
    db.commit()
    follow = submit_request("snt", section_code="C-D")
    client.put(
        f"/api/v1/requests/{follow['id']}/dependencies",
        json={"dependencies": [{"depends_on": far["id"]}]},
        headers=world.h("snt"),
    )
    plan_id = run_plan(client, world)
    deferred = {e["request_id"]: e for e in explanations(client, world, plan_id, code="DEFERRED")}
    assert set(deferred) == {far["id"], long_one["id"], follow["id"]}
    assert deferred[far["id"]]["numbers"]["reason"] == "OUT_OF_HORIZON"
    assert deferred[long_one["id"]]["numbers"] == {
        "reason": "TOO_LONG",
        "duration_minutes": 480,
        "limit_minutes": 360,
    }
    assert deferred[follow["id"]]["numbers"]["waiting_for"] == [far["id"]]
    assert all(e["text"] for e in deferred.values())


def test_every_explanation_has_a_known_code_text_and_numbers(client, world, trio):
    items = explanations(client, world, run_plan(client, world))
    assert items
    for item in items:
        assert item["code"] in EXPLANATION_CODES
        assert item["text"] and isinstance(item["numbers"], dict)


def test_explanation_filters(client, world, trio):
    plan_id = run_plan(client, world)
    everything = explanations(client, world, plan_id)
    assert {e["code"] for e in explanations(client, world, plan_id, code="MERGED")} == {"MERGED"}
    block_id = get(client, world, f"{PLANS}/{plan_id}/schedule").json()["blocks"][0]["id"]
    assert all(e["block_id"] == block_id for e in explanations(client, world, plan_id, block_id=block_id))
    assert explanations(client, world, plan_id, request_id=99999) == []
    assert len(everything) >= len(explanations(client, world, plan_id, code="MERGED"))


def test_explanation_errors_and_roles(client, world, trio):
    plan_id = run_plan(client, world)
    for who in ("engg", "viewer", "planner", "admin"):
        assert get(client, world, f"{PLANS}/{plan_id}/explanations", who=who).status_code == 200
    assert client.get(f"{PLANS}/{plan_id}/explanations").status_code == 401
    assert get(client, world, f"{PLANS}/999/explanations").status_code == 404


def test_explanations_of_an_unfinished_run_are_409(client, world, monkeypatch):
    from app.services import plan_runner

    monkeypatch.setattr(plan_runner, "submit", lambda run_id: None)
    plan_id = client.post(PLANS, json=HORIZON, headers=world.h("planner")).json()["id"]
    assert get(client, world, f"{PLANS}/{plan_id}/explanations").status_code == 409


def test_explanations_are_saved_with_the_plan(client, world, trio, db):
    plan_id = run_plan(client, world)
    assert db.query(Explanation).filter_by(plan_run_id=plan_id).count() >= 1


# ---------- conflicts ----------


def test_section_competition_is_reported_and_resolved(client, world, trio):
    plan_id = run_plan(client, world)
    body = get(client, world, f"{PLANS}/{plan_id}/conflicts").json()
    (competition,) = [c for c in body["conflicts"] if c["type"] == "SECTION_COMPETITION"]
    assert competition["section_code"] == "A-B"
    assert competition["request_ids"] == sorted(r["id"] for r in trio)
    assert competition["departments"] == ["ENGG", "SNT", "TRD"]
    assert competition["resolution"] == "MERGED"
    assert "share one block" in competition["resolution_detail"]


def test_requests_on_different_sections_do_not_conflict(client, world, submit_request, inline_planner):
    submit_request("engg", section_code="A-B")
    submit_request("trd", section_code="B-C")
    body = get(client, world, f"{PLANS}/{run_plan(client, world)}/conflicts").json()
    assert body["conflicts"] == []


def test_requests_with_separate_dates_do_not_compete(client, world, submit_request, inline_planner):
    submit_request("engg", earliest_date="2026-10-19", deadline_date="2026-10-20")
    submit_request("trd", earliest_date="2026-10-23", deadline_date="2026-10-24")
    body = get(client, world, f"{PLANS}/{run_plan(client, world)}/conflicts").json()
    assert [c for c in body["conflicts"] if c["type"] == "SECTION_COMPETITION"] == []


def test_dependency_and_unplaced_conflicts(client, world, submit_request, inline_planner):
    first = submit_request("engg", section_code="A-B", **ONE_DAY)
    second = submit_request("trd", section_code="B-C", **ONE_DAY)
    far = submit_request("snt", section_code="C-D", earliest_date="2026-12-01", deadline_date="2026-12-02")
    client.put(
        f"/api/v1/requests/{second['id']}/dependencies",
        json={"dependencies": [{"depends_on": first["id"]}]},
        headers=world.h("trd"),
    )
    body = get(client, world, f"{PLANS}/{run_plan(client, world)}/conflicts").json()
    kinds = {c["type"]: c for c in body["conflicts"]}
    assert kinds["DEPENDENCY"]["resolution"] == "ORDERED"
    assert kinds["DEPENDENCY"]["request_ids"] == [first["id"], second["id"]]
    assert kinds["UNPLACED"]["request_ids"] == [far["id"]]
    assert kinds["UNPLACED"]["reason"] == "OUT_OF_HORIZON"


def test_not_same_block_dependency_is_reported_as_separated_days(client, world, submit_request, inline_planner):
    first = submit_request("engg", duration_minutes=120)
    second = submit_request("trd", duration_minutes=120)
    client.put(
        f"/api/v1/requests/{second['id']}/dependencies",
        json={"dependencies": [{"depends_on": first["id"], "relation": "not_same_block"}]},
        headers=world.h("trd"),
    )
    body = get(client, world, f"{PLANS}/{run_plan(client, world)}/conflicts").json()
    (dependency,) = [c for c in body["conflicts"] if c["type"] == "DEPENDENCY"]
    assert dependency["resolution"] == "SEPARATED_DAYS"
    (competition,) = [c for c in body["conflicts"] if c["type"] == "SECTION_COMPETITION"]
    assert competition["resolution"] == "SEPARATED"


def test_conflict_errors(client, world):
    assert get(client, world, f"{PLANS}/999/conflicts").status_code == 404
    assert client.get(f"{PLANS}/1/conflicts").status_code == 401


# ---------- what-if ----------


def counts(db):
    return tuple(
        db.query(model).count()
        for model in (PlanRun, Block, PlanAssignment, Explanation, AuditLog, BlockRequest)
    )


def test_whatif_returns_the_difference_and_saves_nothing(client, world, pair, db):
    plan_id = run_plan(client, world)
    before = counts(db)
    run = db.get(PlanRun, plan_id)
    stored = (run.plan, run.metrics, run.status)

    response = move(
        client, world, f"{PLANS}/{plan_id}/whatif", {"request_id": pair[1]["id"], "start": "2026-10-19T12:00:00+05:30"}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["feasible"] is True
    assert body["target"]["to"]["start"] == "2026-10-19T12:00:00+05:30"
    assert body["target"]["to"]["end"] == "2026-10-19T14:00:00+05:30"
    current = get(client, world, f"{PLANS}/{plan_id}").json()["metrics"]["integrated"]
    assert body["metrics"]["current"] == current
    for key, value in body["metrics"]["difference"].items():
        assert value == pytest.approx(body["metrics"]["whatif"][key] - current[key])
    # the other request follows into the same closure instead of opening a second one
    assert [m["request_id"] for m in body["moved_requests"]] == [pair[0]["id"]]
    assert body["metrics"]["whatif"]["closures"] == 1

    db.expire_all()
    assert counts(db) == before
    run = db.get(PlanRun, plan_id)
    assert (run.plan, run.metrics, run.status) == stored


def test_whatif_that_cannot_work_says_so(client, world, submit_request, inline_planner):
    first = submit_request("engg", **ONE_DAY)
    second = submit_request("trd", section_code="B-C", **ONE_DAY)
    client.put(
        f"/api/v1/requests/{second['id']}/dependencies",
        json={"dependencies": [{"depends_on": first["id"]}]},
        headers=world.h("trd"),
    )
    plan_id = run_plan(client, world)
    response = move(
        client, world, f"{PLANS}/{plan_id}/whatif", {"request_id": second["id"], "start": "2026-10-19T00:00:00+05:30"}
    )
    assert response.status_code == 200
    assert response.json()["feasible"] is False
    assert response.json()["solver_status"] == "INFEASIBLE"


@pytest.mark.parametrize(
    ("start", "code"),
    [
        ("2026-10-19T08:10:00+05:30", "validation"),  # not on the 30-minute grid
        ("2026-10-19T08:00:30+05:30", "validation"),
        ("2026-10-25T08:00:00+05:30", "move_outside_window"),  # after the deadline
        ("2026-10-18T08:00:00+05:30", "move_outside_window"),  # before the earliest date
        ("2026-10-19T23:00:00+05:30", "move_outside_window"),  # would run past midnight
    ],
)
def test_whatif_rejects_bad_moves(client, world, pair, start, code):
    plan_id = run_plan(client, world)
    response = move(client, world, f"{PLANS}/{plan_id}/whatif", {"request_id": pair[0]["id"], "start": start})
    assert response.status_code == 422, response.text
    assert response.json()["title"] == code


def test_whatif_rejects_unknown_requests_and_naive_times(client, world, pair):
    plan_id = run_plan(client, world)
    unknown = move(client, world, f"{PLANS}/{plan_id}/whatif", {"request_id": 9999, "start": "2026-10-19T08:00:00+05:30"})
    naive = move(client, world, f"{PLANS}/{plan_id}/whatif", {"request_id": pair[0]["id"], "start": "2026-10-19T08:00:00"})
    assert unknown.status_code == 422 and unknown.json()["title"] == "unknown_request"
    assert naive.status_code == 422


def test_whatif_cannot_move_a_request_the_plan_deferred(client, world, submit_request, inline_planner):
    far = submit_request("engg", earliest_date="2026-12-01", deadline_date="2026-12-05")
    plan_id = run_plan(client, world)
    response = move(client, world, f"{PLANS}/{plan_id}/whatif", {"request_id": far["id"], "start": "2026-10-19T08:00:00+05:30"})
    assert response.status_code == 422
    assert response.json()["title"] == "move_outside_window"


def test_a_solver_crash_during_a_whatif_is_a_clear_error_and_changes_nothing(client, world, pair, db, monkeypatch):
    from app.planner.model import SolveResult
    from app.services import review_service

    plan_id = run_plan(client, world)
    before = counts(db)
    monkeypatch.setattr(review_service, "solve", lambda *a, **k: SolveResult("CRASHED", message="exit code 3"))
    response = move(
        client, world, f"{PLANS}/{plan_id}/whatif", {"request_id": pair[0]["id"], "start": "2026-10-19T08:00:00+05:30"}
    )
    assert response.status_code == 503
    assert response.json()["title"] == "solver_crashed"
    override = move(
        client,
        world,
        f"{PLANS}/{plan_id}/overrides",
        {"moves": [{"request_id": pair[0]["id"], "start": "2026-10-19T08:00:00+05:30"}]},
    )
    assert override.status_code == 503
    db.expire_all()
    assert counts(db) == before


def test_whatif_roles_and_states(client, world, pair, monkeypatch):
    plan_id = run_plan(client, world)
    body = {"request_id": pair[0]["id"], "start": "2026-10-19T08:00:00+05:30"}
    for who, expected in [("planner", 200), ("admin", 200), ("engg", 403), ("viewer", 403)]:
        assert move(client, world, f"{PLANS}/{plan_id}/whatif", body, who=who).status_code == expected
    assert client.post(f"{PLANS}/{plan_id}/whatif", json=body).status_code == 401
    assert move(client, world, f"{PLANS}/999/whatif", body).status_code == 404

    from app.services import plan_runner

    monkeypatch.setattr(plan_runner, "submit", lambda run_id: None)
    queued = client.post(PLANS, json=HORIZON, headers=world.h("planner")).json()["id"]
    assert move(client, world, f"{PLANS}/{queued}/whatif", body).status_code == 409


# ---------- override ----------


def test_override_creates_a_child_run_and_keeps_the_parent(client, world, pair, db):
    plan_id = run_plan(client, world)
    parent = get(client, world, f"{PLANS}/{plan_id}").json()
    response = move(
        client,
        world,
        f"{PLANS}/{plan_id}/overrides",
        {"moves": [{"request_id": pair[1]["id"], "start": "2026-10-19T12:00:00+05:30"}]},
    )
    assert response.status_code == 201, response.text
    child = response.json()
    assert child["id"] != plan_id and child["parent_id"] == plan_id
    assert child["status"] == "succeeded"
    assert child["metrics"]["baseline"] == parent["metrics"]["baseline"]

    after = get(client, world, f"{PLANS}/{plan_id}").json()  # the original stays on record
    assert after["metrics"] == parent["metrics"] and after["status"] == "succeeded"

    moved = {
        m["request_id"]: m for b in get(client, world, f"{PLANS}/{child['id']}/schedule").json()["blocks"] for m in b["members"]
    }
    assert moved[pair[1]["id"]]["start"] == "12:00"
    rows = {a.request_id: a for a in db.query(PlanAssignment).filter_by(plan_run_id=child["id"])}
    assert rows[pair[1]["id"]].overridden is True
    assert rows[pair[0]["id"]].overridden is False


def test_override_is_explained_and_audited(client, world, pair, db):
    plan_id = run_plan(client, world)
    child = move(
        client,
        world,
        f"{PLANS}/{plan_id}/overrides",
        {"moves": [{"request_id": pair[1]["id"], "start": "2026-10-19T12:00:00+05:30"}]},
    ).json()
    items = explanations(client, world, child["id"], code="OVERRIDE")
    assert [e["request_id"] for e in items] == [pair[1]["id"]]
    assert items[0]["numbers"]["moved_to"] == "Mon 19 Oct 12:00-14:00"
    assert "moved by a planner" in items[0]["text"]
    assert explanations(client, world, plan_id, code="OVERRIDE") == []  # the parent has none
    row = db.query(AuditLog).filter_by(action="plan.override").one()
    assert row.entity_id == child["id"] and row.details["parent"] == plan_id


def test_override_with_several_moves(client, world, pair):
    plan_id = run_plan(client, world)
    response = move(
        client,
        world,
        f"{PLANS}/{plan_id}/overrides",
        {
            "moves": [
                {"request_id": pair[0]["id"], "start": "2026-10-19T04:00:00+05:30"},
                {"request_id": pair[1]["id"], "start": "2026-10-19T08:00:00+05:30"},
            ]
        },
    )
    assert response.status_code == 201, response.text
    integrated = response.json()["metrics"]["integrated"]
    assert integrated["closures"] == 1  # still one closure, now 04:00-10:00
    assert integrated["block_hours"] == 6.0


def test_override_cannot_stretch_a_closure_past_the_block_maximum(client, world, pair, db):
    plan_id = run_plan(client, world)
    runs = db.query(PlanRun).count()
    response = move(
        client,
        world,
        f"{PLANS}/{plan_id}/overrides",
        {
            "moves": [
                {"request_id": pair[0]["id"], "start": "2026-10-19T04:00:00+05:30"},
                {"request_id": pair[1]["id"], "start": "2026-10-19T14:00:00+05:30"},
            ]
        },
    )  # one closure would have to run 04:00-16:00, twice the 6-hour maximum
    assert response.status_code == 409
    assert response.json()["title"] == "override_infeasible"
    db.expire_all()
    assert db.query(PlanRun).count() == runs


def test_override_that_cannot_work_is_409_and_creates_nothing(client, world, submit_request, inline_planner, db):
    first = submit_request("engg", **ONE_DAY)
    second = submit_request("trd", section_code="B-C", **ONE_DAY)
    client.put(
        f"/api/v1/requests/{second['id']}/dependencies",
        json={"dependencies": [{"depends_on": first["id"]}]},
        headers=world.h("trd"),
    )
    plan_id = run_plan(client, world)
    runs = db.query(PlanRun).count()
    response = move(
        client,
        world,
        f"{PLANS}/{plan_id}/overrides",
        {"moves": [{"request_id": second["id"], "start": "2026-10-19T00:00:00+05:30"}]},
    )
    assert response.status_code == 409
    assert response.json()["title"] == "override_infeasible"
    db.expire_all()
    assert db.query(PlanRun).count() == runs


def test_override_input_validation(client, world, pair):
    plan_id = run_plan(client, world)
    url = f"{PLANS}/{plan_id}/overrides"
    start = "2026-10-19T08:00:00+05:30"
    assert move(client, world, url, {"moves": []}).status_code == 422
    duplicate = move(client, world, url, {"moves": [{"request_id": pair[0]["id"], "start": start}] * 2})
    assert duplicate.status_code == 422
    assert move(client, world, url, {"moves": [{"request_id": 999, "start": start}]}).status_code == 422
    late = move(client, world, url, {"moves": [{"request_id": pair[0]["id"], "start": "2026-12-01T08:00:00+05:30"}]})
    assert late.json()["title"] == "move_outside_window"


def test_override_roles(client, world, pair):
    plan_id = run_plan(client, world)
    body = {"moves": [{"request_id": pair[0]["id"], "start": "2026-10-19T08:00:00+05:30"}]}
    assert move(client, world, f"{PLANS}/{plan_id}/overrides", body, who="engg").status_code == 403
    assert move(client, world, f"{PLANS}/{plan_id}/overrides", body, who="viewer").status_code == 403
    assert move(client, world, f"{PLANS}/{plan_id}/overrides", body, who="admin").status_code == 201


def test_a_published_plan_cannot_be_overridden(client, world, pair):
    plan_id = run_plan(client, world)
    move(client, world, f"{PLANS}/{plan_id}/approve", None)
    move(client, world, f"{PLANS}/{plan_id}/publish", None)
    body = {"moves": [{"request_id": pair[0]["id"], "start": "2026-10-19T08:00:00+05:30"}]}
    response = move(client, world, f"{PLANS}/{plan_id}/overrides", body)
    assert response.status_code == 409 and response.json()["title"] == "invalid_state"


def test_the_overridden_child_can_be_approved_and_the_parent_then_goes_stale(client, world, pair):
    plan_id = run_plan(client, world)
    child = move(
        client,
        world,
        f"{PLANS}/{plan_id}/overrides",
        {"moves": [{"request_id": pair[1]["id"], "start": "2026-10-19T12:00:00+05:30"}]},
    ).json()
    assert move(client, world, f"{PLANS}/{child['id']}/approve", None).status_code == 200
    stale = move(client, world, f"{PLANS}/{plan_id}/approve", None)
    assert stale.status_code == 409 and stale.json()["title"] == "stale_plan"


# ---------- approve ----------


def test_approve_schedules_the_requests(client, world, pair, db):
    plan_id = run_plan(client, world)
    response = move(client, world, f"{PLANS}/{plan_id}/approve", None)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "approved" and body["approved_at"].endswith("+05:30")
    assert all(request_status(client, world, r["id"]) == "scheduled" for r in pair)
    run = db.get(PlanRun, plan_id)
    assert run.approved_by is not None
    row = db.query(AuditLog).filter_by(action="plan.approve").one()
    assert row.details["requests"] == sorted(r["id"] for r in pair)


def test_deferred_requests_stay_submitted_when_a_plan_is_approved(client, world, submit_request, inline_planner):
    placed = submit_request("engg")
    far = submit_request("trd", earliest_date="2026-12-01", deadline_date="2026-12-05")
    plan_id = run_plan(client, world)
    assert move(client, world, f"{PLANS}/{plan_id}/approve", None).status_code == 200
    assert request_status(client, world, placed["id"]) == "scheduled"
    assert request_status(client, world, far["id"]) == "submitted"


def test_approve_twice_is_409(client, world, pair):
    plan_id = run_plan(client, world)
    move(client, world, f"{PLANS}/{plan_id}/approve", None)
    again = move(client, world, f"{PLANS}/{plan_id}/approve", None)
    assert again.status_code == 409 and again.json()["title"] == "invalid_transition"


def test_only_a_succeeded_plan_can_be_approved(client, world, monkeypatch):
    from app.services import plan_runner

    monkeypatch.setattr(plan_runner, "submit", lambda run_id: None)
    queued = client.post(PLANS, json=HORIZON, headers=world.h("planner")).json()["id"]
    assert move(client, world, f"{PLANS}/{queued}/approve", None).status_code == 409


def test_approve_roles(client, world, pair):
    plan_id = run_plan(client, world)
    assert move(client, world, f"{PLANS}/{plan_id}/approve", None, who="engg").status_code == 403
    assert move(client, world, f"{PLANS}/{plan_id}/approve", None, who="viewer").status_code == 403
    assert client.post(f"{PLANS}/{plan_id}/approve").status_code == 401
    assert move(client, world, f"{PLANS}/999/approve", None).status_code == 404
    assert move(client, world, f"{PLANS}/{plan_id}/approve", None, who="admin").status_code == 200


def test_approve_refuses_a_plan_whose_request_was_cancelled(client, world, pair):
    plan_id = run_plan(client, world)
    client.post(f"/api/v1/requests/{pair[0]['id']}/cancel", headers=world.h("engg"))
    response = move(client, world, f"{PLANS}/{plan_id}/approve", None)
    assert response.status_code == 409
    assert response.json()["title"] == "stale_plan"
    assert response.json()["request_ids"] == [pair[0]["id"]]
    assert request_status(client, world, pair[1]["id"]) == "submitted"  # nothing was changed


def test_approve_refuses_a_plan_whose_request_was_edited(client, world, pair):
    plan_id = run_plan(client, world)
    client.patch(
        f"/api/v1/requests/{pair[1]['id']}",
        json={"version": pair[1]["version"], "priority": 1},
        headers=world.h("trd"),
    )
    response = move(client, world, f"{PLANS}/{plan_id}/approve", None)
    assert response.status_code == 409 and response.json()["request_ids"] == [pair[1]["id"]]


def test_two_plans_cannot_both_be_approved_for_the_same_requests(client, world, pair):
    first, second = run_plan(client, world), run_plan(client, world)
    assert move(client, world, f"{PLANS}/{first}/approve", None).status_code == 200
    assert move(client, world, f"{PLANS}/{second}/approve", None).status_code == 409


# ---------- publish ----------


def test_publish_makes_blocks_and_requests_public(client, world, pair, db):
    plan_id = run_plan(client, world)
    move(client, world, f"{PLANS}/{plan_id}/approve", None)
    response = move(client, world, f"{PLANS}/{plan_id}/publish", None)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "published" and response.json()["published_at"]
    assert {b.status for b in db.query(Block).filter_by(plan_run_id=plan_id)} == {"published"}
    assert all(request_status(client, world, r["id"]) == "published" for r in pair)
    assert db.query(AuditLog).filter_by(action="plan.publish").count() == 1


def test_publish_needs_approval_first(client, world, pair):
    plan_id = run_plan(client, world)
    early = move(client, world, f"{PLANS}/{plan_id}/publish", None)
    assert early.status_code == 409 and early.json()["title"] == "invalid_transition"
    move(client, world, f"{PLANS}/{plan_id}/approve", None)
    move(client, world, f"{PLANS}/{plan_id}/publish", None)
    assert move(client, world, f"{PLANS}/{plan_id}/publish", None).status_code == 409


def test_publish_roles(client, world, pair):
    plan_id = run_plan(client, world)
    move(client, world, f"{PLANS}/{plan_id}/approve", None)
    assert move(client, world, f"{PLANS}/{plan_id}/publish", None, who="engg").status_code == 403
    assert move(client, world, f"{PLANS}/{plan_id}/publish", None, who="viewer").status_code == 403
    assert client.post(f"{PLANS}/{plan_id}/publish").status_code == 401
    assert move(client, world, f"{PLANS}/999/publish", None).status_code == 404
    assert move(client, world, f"{PLANS}/{plan_id}/publish", None, who="admin").status_code == 200


def test_overlapping_published_blocks_are_refused(client, world, submit_request, inline_planner, db):
    submit_request("engg", duration_minutes=120, **ONE_DAY)
    first = run_plan(client, world)
    move(client, world, f"{PLANS}/{first}/approve", None)
    assert move(client, world, f"{PLANS}/{first}/publish", None).status_code == 200

    # A later plan knows nothing about the published closure and picks the same slot.
    submit_request("engg", duration_minutes=120, **ONE_DAY)
    second = run_plan(client, world)
    assert move(client, world, f"{PLANS}/{second}/approve", None).status_code == 200
    response = move(client, world, f"{PLANS}/{second}/publish", None)
    assert response.status_code == 409, response.text
    body = response.json()
    assert body["title"] == "block_overlap"
    assert body["conflicts"][0]["section_code"] == "A-B"
    assert body["conflicts"][0]["conflicts_with_plan"] == first

    db.expire_all()
    assert db.get(PlanRun, second).status == "approved"  # nothing was published
    assert {b.status for b in db.query(Block).filter_by(plan_run_id=second)} == {"proposed"}
    published = db.query(Block).filter_by(status="published").count()
    assert published == 1


def test_non_overlapping_blocks_on_other_sections_publish_fine(client, world, submit_request, inline_planner):
    submit_request("engg", section_code="A-B", **ONE_DAY)
    first = run_plan(client, world)
    move(client, world, f"{PLANS}/{first}/approve", None)
    move(client, world, f"{PLANS}/{first}/publish", None)
    submit_request("engg", section_code="B-C", **ONE_DAY)
    second = run_plan(client, world)
    move(client, world, f"{PLANS}/{second}/approve", None)
    assert move(client, world, f"{PLANS}/{second}/publish", None).status_code == 200


def publish_pinned(client, world, submit_request, start):
    """Plan one request, pin it to `start` with an override, approve and publish the result."""
    request = submit_request("engg", duration_minutes=120, **ONE_DAY)
    plan_id = run_plan(client, world)
    child = move(
        client,
        world,
        f"{PLANS}/{plan_id}/overrides",
        {"moves": [{"request_id": request["id"], "start": start}]},
    ).json()
    assert move(client, world, f"{PLANS}/{child['id']}/approve", None).status_code == 200
    return child["id"]


def test_touching_blocks_may_both_be_published_but_overlapping_ones_may_not(
    client, world, submit_request, inline_planner
):
    first = publish_pinned(client, world, submit_request, "2026-10-19T00:00:00+05:30")
    assert move(client, world, f"{PLANS}/{first}/publish", None).status_code == 200  # 00:00-02:00

    touching = publish_pinned(client, world, submit_request, "2026-10-19T02:00:00+05:30")
    assert move(client, world, f"{PLANS}/{touching}/publish", None).status_code == 200  # 02:00-04:00

    overlapping = publish_pinned(client, world, submit_request, "2026-10-19T03:30:00+05:30")
    response = move(client, world, f"{PLANS}/{overlapping}/publish", None)  # 03:30-05:30
    assert response.status_code == 409
    assert response.json()["conflicts"][0]["conflicts_with_plan"] == touching
    assert len(get(client, world, "/api/v1/blocks").json()["blocks"]) == 2


# ---------- the published calendar ----------


def test_blocks_calendar_lists_only_published_blocks(client, world, submit_request, inline_planner):
    submit_request("engg", section_code="A-B", **ONE_DAY)
    submit_request("trd", section_code="B-C", earliest_date="2026-10-21", deadline_date="2026-10-21")
    plan_id = run_plan(client, world)
    assert get(client, world, "/api/v1/blocks").json() == {"blocks": []}  # proposed only
    move(client, world, f"{PLANS}/{plan_id}/approve", None)
    move(client, world, f"{PLANS}/{plan_id}/publish", None)

    blocks = get(client, world, "/api/v1/blocks").json()["blocks"]
    assert [b["section_code"] for b in blocks] == ["A-B", "B-C"]  # oldest first
    assert all(b["status"] == "published" and b["plan_id"] == plan_id for b in blocks)
    assert blocks[0]["members"][0]["dept"] == "ENGG"
    assert blocks[0]["members"][0]["request"].startswith("R")
    assert blocks[0]["start"].endswith("+05:30")

    only_ab = get(client, world, "/api/v1/blocks", section="A-B").json()["blocks"]
    assert [b["section_code"] for b in only_ab] == ["A-B"]
    window = get(client, world, "/api/v1/blocks", date_from="2026-10-21", date_to="2026-10-21").json()["blocks"]
    assert [b["section_code"] for b in window] == ["B-C"]
    assert get(client, world, "/api/v1/blocks", date_from="2026-11-01").json()["blocks"] == []


def test_blocks_calendar_roles(client, world):
    for who in ("engg", "viewer", "planner", "admin"):
        assert get(client, world, "/api/v1/blocks", who=who).status_code == 200
    assert client.get("/api/v1/blocks").status_code == 401


def test_date_helper_matches_the_horizon():
    assert date(2026, 10, 19).weekday() == 0  # the horizon starts on a Monday
