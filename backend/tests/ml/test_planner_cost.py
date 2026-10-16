"""The planner uses the delay model only when one is active and works, and says which it used."""
from datetime import date

import pytest

from app.config import get_settings
from app.db.models import PlanRun
from app.ml import predict, registry
from app.services import traffic_service
from tests.conftest import HORIZON

PLANS = "/api/v1/plans"


@pytest.fixture(autouse=True)
def _fresh_stats():
    predict.stats["ml_inference_fallback_total"] = 0


@pytest.fixture
def traffic(client, world):
    client.post("/api/v1/traffic/synthetic", json={"seed": 1}, headers=world.h("planner"))
    client.post(
        "/api/v1/traffic/rebuild",
        json={"date_from": "2026-10-19", "date_to": "2026-10-25"},
        headers=world.h("planner"),
    )


@pytest.fixture
def requests_(submit_request):
    for who in ("engg", "trd", "snt"):
        submit_request(who, duration_minutes=120)


def run(client, world, inline_planner):
    plan_id = client.post(PLANS, json=HORIZON, headers=world.h("planner")).json()["id"]
    return client.get(f"{PLANS}/{plan_id}", headers=world.h("viewer")).json()


def train_delay(client, world):
    response = client.post("/api/v1/ml/train", json={"kind": "delay", "days": 40}, headers=world.h("admin"))
    assert response.status_code == 201 and response.json()["results"][0]["is_active"]


def weighted_counts(db):
    cost, _ = traffic_service.load_arrays(db, ["A-B"], date(2026, 10, 19), 7, 30)
    return cost["A-B"]


def test_without_a_model_the_plan_uses_train_counts_and_says_so(client, world, traffic, requests_, inline_planner):
    plan = run(client, world, inline_planner)
    assert plan["status"] == "succeeded"
    assert plan["model_versions"] == {"cost": "traffic_count", "ml_fallback": "no active delay model"}
    assert predict.stats["ml_inference_fallback_total"] == 1


def test_with_an_active_model_the_plan_uses_predicted_delay(client, world, traffic, requests_, inline_planner, db):
    train_delay(client, world)
    plan = run(client, world, inline_planner)
    assert plan["status"] == "succeeded"
    assert plan["model_versions"] == {"cost": "delay_model:v1"}
    assert plan["metrics"]["integrated"]["closures"] <= plan["metrics"]["baseline"]["closures"]
    stored = db.get(PlanRun, plan["id"]).snapshot["cost"]["A-B"]
    assert stored != {str(d): v for d, v in weighted_counts(db).items()}  # the arrays came from the model
    assert all(v >= 0 for day in stored.values() for v in day)
    assert predict.stats["ml_inference_fallback_total"] == 0


def test_the_cost_arrays_follow_the_traffic(client, world, traffic, requests_, inline_planner, db):
    train_delay(client, world)
    plan = run(client, world, inline_planner)
    predicted = db.get(PlanRun, plan["id"]).snapshot["cost"]["A-B"]["0"]
    counts = weighted_counts(db)[0]
    busiest = max(range(48), key=lambda k: counts[k])
    quietest = min(range(48), key=lambda k: counts[k])
    assert predicted[busiest] > predicted[quietest]  # more traffic in the slot, more predicted delay


def test_a_broken_model_file_does_not_stop_the_plan(client, world, traffic, requests_, inline_planner, db):
    train_delay(client, world)
    (registry.model_dir() / registry.active_model(db, "delay").artifact_path).write_bytes(b"corrupt")
    plan = run(client, world, inline_planner)
    assert plan["status"] == "succeeded"  # the plan still runs, on train counts
    assert plan["model_versions"]["cost"] == "traffic_count"
    assert "cannot be read" in plan["model_versions"]["ml_fallback"]
    assert predict.stats["ml_inference_fallback_total"] == 1


def test_a_deleted_model_file_does_not_stop_the_plan(client, world, traffic, requests_, inline_planner, db):
    train_delay(client, world)
    (registry.model_dir() / registry.active_model(db, "delay").artifact_path).unlink()
    plan = run(client, world, inline_planner)
    assert plan["status"] == "succeeded" and "missing" in plan["model_versions"]["ml_fallback"]


def test_switching_the_model_off_uses_train_counts(client, world, traffic, requests_, inline_planner, monkeypatch):
    train_delay(client, world)
    monkeypatch.setattr(get_settings(), "ml_cost_enabled", False)
    plan = run(client, world, inline_planner)
    assert plan["status"] == "succeeded"
    assert plan["model_versions"] == {"cost": "traffic_count", "ml": "disabled"}


def test_without_traffic_data_there_is_nothing_to_predict(client, world, requests_, inline_planner):
    train_delay(client, world)
    plan = run(client, world, inline_planner)
    assert plan["status"] == "succeeded"
    assert plan["model_versions"]["ml_fallback"] == "no traffic data to predict from"


def test_what_if_and_override_use_the_cost_the_plan_was_made_with(client, world, traffic, requests_, inline_planner, db):
    train_delay(client, world)
    plan = run(client, world, inline_planner)
    block = client.get(f"{PLANS}/{plan['id']}/schedule", headers=world.h("viewer")).json()["blocks"][0]
    move = {"request_id": block["members"][0]["request_id"], "start": block["start"], "time_limit_s": 5}
    result = client.post(f"{PLANS}/{plan['id']}/whatif", json=move, headers=world.h("planner"))
    assert result.status_code == 200 and result.json()["feasible"] is True
    child = client.post(
        f"{PLANS}/{plan['id']}/overrides",
        json={"moves": [{"request_id": move["request_id"], "start": move["start"]}]},
        headers=world.h("planner"),
    )
    assert child.status_code == 201
    assert child.json()["parent_id"] == plan["id"]
