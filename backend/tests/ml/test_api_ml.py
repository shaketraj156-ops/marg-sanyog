import pytest

from app.db.models import AuditLog, MlModel
from app.ml import registry

URL = "/api/v1/ml"
FAST = {"days": 40}  # less synthetic history keeps the tests quick


def train(client, world, who="admin", **body):
    return client.post(f"{URL}/train", json={**FAST, **body}, headers=world.h(who))


def test_only_an_admin_can_train(client, world):
    assert train(client, world, "admin").status_code == 201
    for who in ("planner", "engg", "viewer"):
        assert train(client, world, who).status_code == 403
    assert client.post(f"{URL}/train", json=FAST).status_code == 401


def test_training_both_kinds_returns_metrics_against_the_baselines(client, world):
    body = train(client, world).json()
    kinds = {r["kind"]: r for r in body["results"]}
    assert set(kinds) == {"delay", "overrun"}
    delay, overrun = kinds["delay"], kinds["overrun"]
    assert delay["beats_baseline"] and delay["is_active"] and delay["version"] == 1
    assert delay["metrics"]["mae"] < delay["metrics"]["baseline_mae"]
    assert overrun["beats_baseline"] and overrun["is_active"]
    assert overrun["metrics"]["pinball_loss"] < overrun["metrics"]["baseline_pinball_loss"]
    assert delay["created_at"].endswith("+05:30")


def test_one_kind_can_be_trained_on_its_own(client, world):
    results = train(client, world, kind="delay").json()["results"]
    assert [r["kind"] for r in results] == ["delay"]


def test_training_again_makes_a_new_version_and_the_old_one_stops_being_active(client, world, db):
    train(client, world, kind="delay")
    second = train(client, world, kind="delay", seed=2).json()["results"][0]
    assert second["version"] == 2 and second["is_active"]
    rows = {m.version: m.is_active for m in db.query(MlModel).filter_by(kind="delay")}
    assert rows == {1: False, 2: True}
    assert registry.active_model(db, "delay").version == 2


def test_models_are_listed_for_planners_and_admins_only(client, world):
    train(client, world)
    listed = client.get(f"{URL}/models", headers=world.h("planner"))
    assert listed.status_code == 200
    items = listed.json()["items"]
    assert [(i["kind"], i["version"]) for i in items] == [("overrun", 1), ("delay", 1)]  # newest first
    assert all(i["is_active"] and "metrics" in i for i in items)
    assert client.get(f"{URL}/models", headers=world.h("admin")).status_code == 200
    for who in ("engg", "viewer"):
        assert client.get(f"{URL}/models", headers=world.h(who)).status_code == 403
    assert client.get(f"{URL}/models").status_code == 401


def test_no_models_yet_is_an_empty_list(client, world):
    assert client.get(f"{URL}/models", headers=world.h("planner")).json() == {"items": []}


@pytest.mark.parametrize(
    "body",
    [{"kind": "weather"}, {"days": 10}, {"days": 1000}, {"seed": -1}, {"unknown": 1}],
)
def test_bad_training_requests_are_rejected(client, world, body):
    response = client.post(f"{URL}/train", json=body, headers=world.h("admin"))
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")


def test_training_needs_sections(client, make_user, auth_headers):
    make_user("a@example.test", "admin")
    response = client.post(f"{URL}/train", json=FAST, headers=auth_headers("a@example.test"))
    assert response.status_code == 422 and response.json()["title"] == "no_sections"


def test_training_is_audited(client, world, db):
    train(client, world, kind="delay")
    row = db.query(AuditLog).filter_by(action="ml.train").one()
    assert row.entity == "ml_model"
    assert row.details["models"] == [{"kind": "delay", "version": 1, "active": True}]
