import threading
from datetime import UTC, datetime

import pytest

from app.db.models import AuditLog, Block, BlockRequest, PlanAssignment, PlanRun
from app.planner.checker import check_plan
from app.planner.model import SolveResult
from app.planner.plan import Plan
from app.planner.snapshot import Snapshot
from app.services import plan_runner, plan_service
from tests.conftest import HORIZON, request_body

URL = "/api/v1/plans"


def get_plan(client, world, plan_id, who="viewer"):
    response = client.get(f"{URL}/{plan_id}", headers=world.h(who))
    assert response.status_code == 200, response.text
    return response.json()


def schedule(client, world, plan_id, who="viewer"):
    response = client.get(f"{URL}/{plan_id}/schedule", headers=world.h(who))
    assert response.status_code == 200, response.text
    return response.json()


# ---------- creating a run ----------


def test_post_plans_returns_202_with_a_link(client, world, inline_planner):
    response = client.post(URL, json=HORIZON, headers=world.h("planner"))
    assert response.status_code == 202
    body = response.json()
    assert body["links"] == {"self": f"/api/v1/plans/{body['id']}"}
    assert inline_planner == [body["id"]]


def test_empty_run_succeeds_with_nothing_to_plan(client, world, create_plan):
    plan = get_plan(client, world, create_plan()["id"])
    assert plan["status"] == "succeeded"
    assert plan["solver_status"] == "OPTIMAL"
    assert plan["metrics"]["integrated"]["closures"] == 0
    assert schedule(client, world, plan["id"])["blocks"] == []


def test_three_departments_on_one_section_become_one_closure(
    client, world, submit_request, create_plan
):
    for who in ("engg", "trd", "snt"):
        submit_request(who, section_code="A-B", duration_minutes=120)
    plan = get_plan(client, world, create_plan()["id"])
    assert plan["status"] == "succeeded"
    assert plan["metrics"]["baseline"]["closures"] == 3
    assert plan["metrics"]["integrated"]["closures"] == 1
    assert plan["metrics"]["integrated"]["block_hours"] < plan["metrics"]["baseline"]["block_hours"]
    assert plan["deferred_request_ids"] == []

    blocks = schedule(client, world, plan["id"])["blocks"]
    assert len(blocks) == 1
    block = blocks[0]
    assert block["section_code"] == "A-B"
    assert block["start"].endswith("+05:30") and block["end"].endswith("+05:30")
    assert {m["dept"] for m in block["members"]} == {"ENGG", "TRD", "SNT"}
    assert all(len(m["start"]) == 5 and len(m["end"]) == 5 for m in block["members"])
    assert all(m["request"] == f"R{m['request_id']}" for m in block["members"])


def test_plan_metrics_and_solver_details(client, world, submit_request, create_plan):
    submit_request("engg")
    plan = get_plan(client, world, create_plan()["id"])
    assert set(plan["metrics"]) == {"baseline", "integrated", "solver"}
    assert set(plan["metrics"]["integrated"]) >= {"closures", "block_hours", "trains_affected"}
    assert plan["objective_value"] is not None
    assert plan["gap"] == pytest.approx(0.0, abs=1e-6)
    assert plan["input_hash"] and len(plan["input_hash"]) == 64
    assert plan["slot_minutes"] == 30
    assert plan["weights"] == {"block": 150, "traffic": 10, "delay": 20, "defer": 1000}
    assert plan["horizon_start"] == "2026-10-19T00:00:00+05:30"
    assert plan["finished_at"] is not None


def test_custom_weights_and_seed_are_stored(client, world, create_plan):
    created = create_plan(weights={"block": 500}, seed=7, time_limit_s=3)
    plan = get_plan(client, world, created["id"])
    assert plan["weights"]["block"] == 500
    assert plan["weights"]["defer"] == 1000
    assert (plan["seed"], plan["time_limit_s"]) == (7, 3)


def test_only_submitted_requests_are_planned(client, world, create_request, submit_request, create_plan, db):
    create_request("engg")  # draft
    cancelled = submit_request("engg", section_code="B-C")
    client.post(f"/api/v1/requests/{cancelled['id']}/cancel", headers=world.h("engg"))
    kept = submit_request("trd", section_code="C-D")
    schedule_ = schedule(client, world, create_plan()["id"])
    members = [m["request_id"] for b in schedule_["blocks"] for m in b["members"]]
    assert members == [kept["id"]]


def test_dependencies_are_planned_and_respected(client, world, submit_request, create_plan):
    first = submit_request("engg", duration_minutes=120)
    second = submit_request("snt", duration_minutes=120)
    client.put(
        f"/api/v1/requests/{second['id']}/dependencies",
        json={"dependencies": [{"depends_on": first["id"], "min_gap_minutes": 30}]},
        headers=world.h("snt"),
    )
    blocks = schedule(client, world, create_plan()["id"])["blocks"]
    times = {m["request_id"]: (b["start"][:10], m["start"], m["end"]) for b in blocks for m in b["members"]}
    first_day, _, first_end = times[first["id"]]
    second_day, second_start, _ = times[second["id"]]
    assert (second_day, second_start) > (first_day, first_end)


def test_requests_outside_the_horizon_are_deferred_with_a_reason(
    client, world, submit_request, create_plan
):
    far = submit_request("engg", earliest_date="2026-12-01", deadline_date="2026-12-05")
    near = submit_request("trd", section_code="B-C")
    plan = get_plan(client, world, create_plan()["id"])
    assert plan["deferred_request_ids"] == [far["id"]]
    deferred = schedule(client, world, plan["id"])["deferred"]
    assert deferred == [{"request_id": far["id"], "request": f"R{far['id']}", "reason": "OUT_OF_HORIZON"}]
    assert plan["metrics"]["integrated"]["deferred"] == 1
    # the deferred request stays submitted so a later plan can pick it up
    assert client.get(f"/api/v1/requests/{far['id']}", headers=world.h("viewer")).json()["status"] == "submitted"
    assert near["id"] not in plan["deferred_request_ids"]


def test_request_longer_than_the_block_maximum_is_deferred(
    client, world, submit_request, create_plan, db
):
    long_one = submit_request("engg")
    db.get(BlockRequest, long_one["id"]).duration_minutes = 480  # the database allows up to 720
    db.commit()
    plan = get_plan(client, world, create_plan()["id"])
    assert schedule(client, world, plan["id"])["deferred"][0]["reason"] == "TOO_LONG"


def test_follow_up_of_a_deferred_request_is_deferred_too(client, world, submit_request, create_plan):
    far = submit_request("engg", earliest_date="2026-12-01", deadline_date="2026-12-05")
    follow = submit_request("engg", section_code="B-C")
    client.put(
        f"/api/v1/requests/{follow['id']}/dependencies",
        json={"dependencies": [{"depends_on": far["id"]}]},
        headers=world.h("engg"),
    )
    deferred = {d["request_id"]: d["reason"] for d in schedule(client, world, create_plan()["id"])["deferred"]}
    assert deferred == {far["id"]: "OUT_OF_HORIZON", follow["id"]: "DEPENDENCY_UNMET"}


def test_saved_rows_match_the_schedule(client, world, submit_request, create_plan, db):
    submit_request("engg")
    submit_request("trd")
    plan_id = create_plan()["id"]
    blocks = db.query(Block).filter_by(plan_run_id=plan_id).all()
    assignments = db.query(PlanAssignment).filter_by(plan_run_id=plan_id).all()
    assert len(blocks) == 1 and len(assignments) == 2
    scheduled = schedule(client, world, plan_id)["blocks"][0]
    assert scheduled["id"] == blocks[0].id
    assert all(a.block_id == blocks[0].id and not a.deferred for a in assignments)
    assert blocks[0].status == "proposed"
    assert blocks[0].start_ts.tzinfo is not None
    assert blocks[0].start_ts < blocks[0].end_ts


def test_stored_plan_passes_the_checker_when_reloaded(client, world, submit_request, create_plan, db):
    for who in ("engg", "trd", "snt"):
        submit_request(who)
    run = db.get(PlanRun, create_plan()["id"])
    snapshot, plan = Snapshot.from_dict(run.snapshot), Plan.from_dict(run.plan)
    assert check_plan(snapshot, plan) == []
    assert run.input_hash == snapshot.input_hash()


def test_baseline_endpoint_shows_the_independent_plan(client, world, submit_request, create_plan):
    for who in ("engg", "trd", "snt"):
        submit_request(who)
    plan_id = create_plan()["id"]
    response = client.get(f"{URL}/{plan_id}/baseline", headers=world.h("viewer"))
    assert response.status_code == 200
    body = response.json()
    assert len(body["blocks"]) == 3
    assert body["metrics"]["closures"] == 3
    assert all(b["id"] is None for b in body["blocks"])


def test_baseline_uses_the_preferred_start(client, world, submit_request, create_plan):
    submit_request("engg", preferred_start="2026-10-20T08:00:00+05:30", duration_minutes=60)
    body = client.get(f"{URL}/{create_plan()['id']}/baseline", headers=world.h("viewer")).json()
    block = body["blocks"][0]
    assert block["start"] == "2026-10-20T08:00:00+05:30"
    assert block["end"] == "2026-10-20T09:00:00+05:30"


def test_same_input_gives_the_same_hash(client, world, submit_request, create_plan):
    submit_request("engg")
    first = get_plan(client, world, create_plan()["id"])
    second = get_plan(client, world, create_plan()["id"])
    assert first["input_hash"] == second["input_hash"]


def test_creating_a_run_is_audited(client, world, create_plan, db):
    plan_id = create_plan()["id"]
    row = db.query(AuditLog).filter_by(action="plan.create").one()
    assert (row.entity, row.entity_id) == ("plan_run", plan_id)


# ---------- roles ----------


def test_only_planners_and_admins_can_start_a_run(client, world, inline_planner):
    for who, expected in [("planner", 202), ("admin", 202), ("engg", 403), ("viewer", 403)]:
        assert client.post(URL, json=HORIZON, headers=world.h(who)).status_code == expected
    assert client.post(URL, json=HORIZON).status_code == 401


def test_every_signed_in_role_can_read_plans(client, world, create_plan):
    plan_id = create_plan()["id"]
    for who in ("planner", "admin", "engg", "trd", "viewer"):
        assert client.get(f"{URL}/{plan_id}", headers=world.h(who)).status_code == 200
        assert client.get(f"{URL}/{plan_id}/schedule", headers=world.h(who)).status_code == 200
        assert client.get(f"{URL}/{plan_id}/baseline", headers=world.h(who)).status_code == 200
        assert client.get(URL, headers=world.h(who)).status_code == 200
    assert client.get(f"{URL}/{plan_id}").status_code == 401


def test_unknown_plan_is_404(client, world):
    for path in ("", "/schedule", "/baseline"):
        response = client.get(f"{URL}/999{path}", headers=world.h("viewer"))
        assert response.status_code == 404
        assert response.json()["title"] == "not_found"


# ---------- validation ----------


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"horizon_start": "2026-10-19T00:00:00"}, "horizon_start"),  # no offset
        ({"horizon_start": "2026-10-19T06:00:00+05:30"}, "horizon_start"),  # not midnight
        ({"horizon_end": "2026-10-26T06:00:00+05:30"}, "horizon_start"),  # not midnight
        ({"horizon_end": "2026-10-19T00:00:00+05:30"}, "horizon_end"),  # zero days
        ({"horizon_end": "2026-10-10T00:00:00+05:30"}, "horizon_end"),  # before the start
        ({"horizon_end": "2026-12-25T00:00:00+05:30"}, "horizon_end"),  # too long
        ({"slot_minutes": 60}, "slot_minutes"),
        ({"time_limit_s": 0}, "time_limit_s"),
        ({"time_limit_s": 601}, "time_limit_s"),
        ({"weights": {"block": -1}}, "weights.block"),
        ({"weights": {"speed": 1}}, "weights.speed"),
        ({"nonsense": 1}, "nonsense"),
    ],
)
def test_invalid_plan_requests(client, world, inline_planner, overrides, field):
    response = client.post(URL, json={**HORIZON, **overrides}, headers=world.h("planner"))
    assert response.status_code == 422, response.text
    assert response.headers["content-type"].startswith("application/problem+json")
    assert any(e["field"] == field for e in response.json()["errors"]), response.json()
    assert inline_planner == []


def test_horizon_in_utc_that_is_midnight_in_ist_is_accepted(client, world, inline_planner):
    body = {**HORIZON, "horizon_start": "2026-10-18T18:30:00+00:00", "horizon_end": "2026-10-25T18:30:00+00:00"}
    assert client.post(URL, json=body, headers=world.h("planner")).status_code == 202


def test_missing_horizon_is_422(client, world):
    assert client.post(URL, json={}, headers=world.h("planner")).status_code == 422


# ---------- idempotency ----------


def test_same_idempotency_key_returns_the_original_run(client, world, create_plan, inline_planner, db):
    first = create_plan(key="plan-2026-10-19")
    second = create_plan(key="plan-2026-10-19")
    assert second["id"] == first["id"]
    assert inline_planner == [first["id"]]  # the job ran once
    assert db.query(PlanRun).count() == 1


def test_different_keys_make_different_runs(client, world, create_plan, db):
    assert create_plan(key="a")["id"] != create_plan(key="b")["id"]
    assert create_plan()["id"] != create_plan()["id"]
    assert db.query(PlanRun).count() == 4


def test_idempotent_replay_skips_validation(client, world, create_plan):
    first = create_plan(key="k")
    replay = client.post(
        URL, json={"horizon_start": "garbage"}, headers={**world.h("planner"), "Idempotency-Key": "k"}
    )
    assert replay.status_code == 422  # body validation still applies; only a valid body replays
    assert first["id"] == create_plan(key="k")["id"]


# ---------- failure handling ----------


def _status(db, plan_id):
    db.expire_all()
    return db.get(PlanRun, plan_id)


def test_a_crash_in_the_solver_fails_the_run_cleanly(client, world, monkeypatch, create_plan, db, submit_request):
    submit_request("engg")

    def boom(*args, **kwargs):
        raise RuntimeError("solver exploded")

    monkeypatch.setattr(plan_runner, "solve", boom)
    run = _status(db, create_plan()["id"])
    assert run.status == "failed"
    assert "solver exploded" in run.error
    assert db.query(Block).count() == 0 and db.query(PlanAssignment).count() == 0


def test_a_plan_that_fails_the_checker_is_never_saved(client, world, monkeypatch, create_plan, db, submit_request):
    submit_request("engg")
    monkeypatch.setattr(plan_runner, "check_plan", lambda snapshot, plan: ["planted violation"])
    run = _status(db, create_plan()["id"])
    assert run.status == "failed"
    assert "Checker rejected the plan" in run.error and "planted violation" in run.error
    assert db.query(Block).count() == 0 and db.query(PlanAssignment).count() == 0
    assert run.plan is None and run.metrics is None


def test_infeasible_result_is_recorded(client, world, monkeypatch, create_plan, db):
    monkeypatch.setattr(plan_runner, "solve", lambda *a, **k: SolveResult("INFEASIBLE"))
    run = _status(db, create_plan()["id"])
    assert (run.status, run.solver_status) == ("infeasible", "INFEASIBLE")


@pytest.mark.parametrize("status", ["UNKNOWN", "MODEL_INVALID"])
def test_no_solution_fails_the_run(client, world, monkeypatch, create_plan, db, status):
    monkeypatch.setattr(plan_runner, "solve", lambda *a, **k: SolveResult(status))
    run = _status(db, create_plan()["id"])
    assert run.status == "failed" and status in run.error


def test_a_solver_crash_fails_the_run_and_the_server_keeps_working(
    client, world, monkeypatch, create_plan, db, submit_request
):
    submit_request("engg")
    real_solve = plan_runner.solve
    monkeypatch.setattr(
        plan_runner, "solve", lambda *a, **k: SolveResult("CRASHED", message="the solver process ended with exit code 3")
    )
    first = _status(db, create_plan()["id"])
    assert first.status == "failed"
    assert "stopped unexpectedly" in first.error and "exit code 3" in first.error
    assert db.query(Block).count() == 0
    monkeypatch.setattr(plan_runner, "solve", real_solve)  # the next run works as normal
    assert _status(db, create_plan()["id"]).status == "succeeded"


def test_schedule_of_an_unfinished_run_is_409(client, world, monkeypatch, db):
    monkeypatch.setattr(plan_runner, "submit", lambda run_id: None)  # never runs
    plan_id = client.post(URL, json=HORIZON, headers=world.h("planner")).json()["id"]
    assert get_plan(client, world, plan_id)["status"] == "queued"
    for path in ("/schedule", "/baseline"):
        response = client.get(f"{URL}/{plan_id}{path}", headers=world.h("viewer"))
        assert response.status_code == 409
        assert response.json()["title"] == "plan_not_ready"


def test_a_run_only_starts_once(monkeypatch, client, world, create_plan, db):
    plan_id = create_plan()["id"]
    calls = []
    monkeypatch.setattr(plan_runner, "solve", lambda *a, **k: calls.append(1))
    plan_runner.run_plan(plan_id)  # already succeeded: must do nothing
    assert calls == []
    assert _status(db, plan_id).status == "succeeded"


def test_run_plan_ignores_unknown_ids(inline_planner):
    plan_runner.run_plan(12345)  # no error


def test_start_in_background_uses_a_thread(monkeypatch):
    seen = {}
    done = threading.Event()

    def fake_run(run_id):
        seen["id"], seen["thread"] = run_id, threading.current_thread()
        done.set()

    monkeypatch.setattr(plan_runner, "run_plan", fake_run)
    plan_runner.start_in_background(42)
    assert done.wait(5)
    assert seen["id"] == 42
    assert seen["thread"] is not threading.main_thread()
    assert seen["thread"].daemon


def test_unfinished_runs_are_failed_on_startup(client, world, db, monkeypatch):
    monkeypatch.setattr(plan_runner, "submit", lambda run_id: None)
    queued = client.post(URL, json=HORIZON, headers=world.h("planner")).json()["id"]
    running = client.post(URL, json=HORIZON, headers=world.h("planner")).json()["id"]
    db.get(PlanRun, running).status = "running"
    db.commit()
    assert plan_service.fail_orphaned_runs(db) == 2
    db.expire_all()
    assert {db.get(PlanRun, i).status for i in (queued, running)} == {"failed"}
    assert "server stopped" in db.get(PlanRun, queued).error


def test_succeeded_runs_survive_a_restart(client, world, create_plan, db):
    plan_id = create_plan()["id"]
    assert plan_service.fail_orphaned_runs(db) == 0
    assert _status(db, plan_id).status == "succeeded"


# ---------- listing ----------


def test_list_plans_newest_first_with_filter_and_paging(client, world, create_plan, monkeypatch, db):
    ids = [create_plan()["id"] for _ in range(3)]
    db.get(PlanRun, ids[0]).status = "failed"
    db.commit()
    everything = client.get(URL, headers=world.h("viewer")).json()
    assert [p["id"] for p in everything["items"]] == ids[::-1]
    failed = client.get(URL, params={"status": "failed"}, headers=world.h("viewer")).json()
    assert [p["id"] for p in failed["items"]] == [ids[0]]
    page = client.get(URL, params={"limit": 2}, headers=world.h("viewer")).json()
    assert len(page["items"]) == 2 and page["next_cursor"] == ids[1]
    rest = client.get(URL, params={"limit": 2, "cursor": page["next_cursor"]}, headers=world.h("viewer")).json()
    assert [p["id"] for p in rest["items"]] == [ids[0]]
    assert rest["next_cursor"] is None


def test_timestamps_are_stored_in_utc_and_shown_in_ist(client, world, create_plan, db):
    plan_id = create_plan()["id"]
    run = db.get(PlanRun, plan_id)
    assert run.horizon_start == datetime(2026, 10, 18, 18, 30, tzinfo=UTC)
    assert get_plan(client, world, plan_id)["horizon_start"] == "2026-10-19T00:00:00+05:30"


def test_request_body_helper_is_valid(client, world):
    assert client.post("/api/v1/requests", json=request_body(), headers=world.h("engg")).status_code == 201
