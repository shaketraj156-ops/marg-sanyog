"""The fallback: the planner must keep working whatever happens to the model."""
import logging
from datetime import date

import pytest

from app.config import get_settings
from app.ml import predict, registry
from app.ml.predict import DelayModelCost, choose_cost
from app.ml.train import TrainResult
from tests.ml.stubs import BrokenStub, LinearStub, bundle

START = date(2026, 10, 19)  # a Monday
SECTIONS = ["A-B", "B-C"]


def traffic():
    """Two trains in slot 16 and one in slot 20 of day 0 on A-B, weights 5 and 1."""
    plain = {"A-B": {0: [0] * 16 + [2] + [0] * 3 + [1] + [0] * 27}}
    weighted = {"A-B": {0: [0] * 16 + [6] + [0] * 3 + [1] + [0] * 27}}
    return plain, weighted


def register_stub(db, model, beats=True, kind="delay"):
    return registry.register(db, None, TrainResult(kind, bundle(model, kind), {"beats_baseline": beats}, beats))


@pytest.fixture(autouse=True)
def _fresh_stats():
    predict.stats["ml_inference_fallback_total"] = 0


# ---------- the cost provider ----------


def test_the_cost_of_a_slot_is_the_extra_delay_the_trains_in_it_cause():
    plain, weighted = traffic()
    cost = DelayModelCost(bundle(LinearStub()), plain, weighted, START).cost("A-B", 0)
    # the stub says 3 + 2 per train; the 3 is the cost of closing at all and is subtracted
    assert len(cost) == 48 and all(isinstance(c, int) for c in cost)
    assert cost[16] == 4 and cost[20] == 2
    assert sum(cost) == 6 and min(cost) == 0


def test_a_day_without_traffic_costs_nothing_and_a_missing_section_data_is_zero_traffic():
    provider = DelayModelCost(bundle(LinearStub()), {}, {}, START)
    assert provider.cost("A-B", 3) == [0] * 48


def test_a_window_costs_the_sum_of_its_slots():
    plain, weighted = traffic()
    cost = DelayModelCost(bundle(LinearStub()), plain, weighted, START).cost("A-B", 0)
    assert sum(cost[16:21]) == cost[16] + cost[20]


def test_a_section_the_model_was_not_trained_for_is_refused():
    provider = DelayModelCost(bundle(LinearStub(), sections=("A-B",)), {}, {}, START)
    with pytest.raises(ValueError, match="not trained for section B-C"):
        provider.cost("B-C", 0)


# ---------- choosing between the model and the train counts ----------


def test_with_no_active_model_the_train_counts_are_used_and_the_fallback_is_counted(db, caplog):
    plain, weighted = traffic()
    with caplog.at_level(logging.WARNING, logger="app.ml.predict"):
        cost, info = choose_cost(db, ["A-B"], weighted, plain, 7, START)
    assert cost is weighted
    assert info == {"cost": "traffic_count", "ml_fallback": "no active delay model"}
    assert predict.stats["ml_inference_fallback_total"] == 1
    assert "ml_inference_fallback" in caplog.text


def test_an_active_model_is_used_for_the_cost(db):
    plain, weighted = traffic()
    row = register_stub(db, LinearStub())
    cost, info = choose_cost(db, ["A-B"], weighted, plain, 7, START)
    assert info == {"cost": f"delay_model:v{row.version}"}
    assert cost["A-B"][0][16] == 4 and cost["A-B"][0][20] == 2  # predicted, not the weighted counts
    assert set(cost["A-B"]) == set(range(7))
    assert predict.stats["ml_inference_fallback_total"] == 0


def test_a_model_that_did_not_beat_its_baseline_is_never_used(db):
    plain, weighted = traffic()
    register_stub(db, LinearStub(), beats=False)
    cost, info = choose_cost(db, ["A-B"], weighted, plain, 7, START)
    assert cost is weighted and info["cost"] == "traffic_count"
    assert info["ml_fallback"] == "no active delay model"


def test_a_better_new_model_takes_over_and_a_worse_one_does_not(db):
    plain, weighted = traffic()
    register_stub(db, LinearStub())
    register_stub(db, BrokenStub(), beats=False)  # stored, not activated
    _, info = choose_cost(db, ["A-B"], weighted, plain, 7, START)
    assert info == {"cost": "delay_model:v1"}


def test_with_no_traffic_data_there_is_nothing_to_predict_from(db):
    register_stub(db, LinearStub())
    cost, info = choose_cost(db, ["A-B"], {}, {}, 7, START)
    assert cost == {} and info["ml_fallback"] == "no traffic data to predict from"


def test_a_missing_model_file_falls_back(db):
    plain, weighted = traffic()
    row = register_stub(db, LinearStub())
    (registry.model_dir() / row.artifact_path).unlink()
    cost, info = choose_cost(db, ["A-B"], weighted, plain, 7, START)
    assert cost is weighted and "missing" in info["ml_fallback"]
    assert predict.stats["ml_inference_fallback_total"] == 1


def test_a_corrupt_model_file_falls_back(db):
    plain, weighted = traffic()
    row = register_stub(db, LinearStub())
    (registry.model_dir() / row.artifact_path).write_bytes(b"garbage")
    cost, info = choose_cost(db, ["A-B"], weighted, plain, 7, START)
    assert cost is weighted and "cannot be read" in info["ml_fallback"]


def test_a_model_that_fails_while_predicting_falls_back(db):
    plain, weighted = traffic()
    register_stub(db, BrokenStub())
    cost, info = choose_cost(db, ["A-B"], weighted, plain, 7, START)
    assert cost is weighted
    assert info["cost"] == "traffic_count" and "RuntimeError" in info["ml_fallback"]


def test_a_section_the_model_does_not_know_falls_back_for_the_whole_plan(db):
    plain, weighted = traffic()
    register_stub(db, LinearStub())
    cost, info = choose_cost(db, ["A-B", "Z-Z"], weighted, plain, 7, START)
    assert cost is weighted and "Z-Z" in info["ml_fallback"]


def test_the_model_can_be_switched_off(db, monkeypatch):
    plain, weighted = traffic()
    register_stub(db, LinearStub())
    monkeypatch.setattr(get_settings(), "ml_cost_enabled", False)
    cost, info = choose_cost(db, ["A-B"], weighted, plain, 7, START)
    assert cost is weighted and info == {"cost": "traffic_count", "ml": "disabled"}
    assert predict.stats["ml_inference_fallback_total"] == 0  # switching off is not a failure
