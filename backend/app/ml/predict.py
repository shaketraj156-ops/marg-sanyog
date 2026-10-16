"""Use the active delay model as the planner's cost, with a safe fallback.

The solver never calls a model while it searches. Before solving, a CostProvider turns the model
into integer arrays (cost per section, day and slot), exactly where the plain train counts would
have gone. If there is no active model, or anything about it fails, the planner uses the train-count
cost instead and says so (spec section 11: "if a model is missing or fails, use TrafficCountCost
and log ml_inference_fallback")."""
import logging
from datetime import date, timedelta

import numpy as np
from sqlalchemy.orm import Session

from app.config import get_settings
from app.ml.features import delay_row
from app.ml.registry import ModelLoadError, active_model, load_bundle
from app.planner.slots import prefix_sums

log = logging.getLogger(__name__)
Arrays = dict[str, dict[int, list[int]]]

# Counts fallbacks since the process started (the spec's ml_inference_fallback_total).
stats = {"ml_inference_fallback_total": 0}


class DelayModelCost:
    """Per-slot cost: the extra train-minutes lost when a closure covers that slot, compared with
    covering it when no train runs. Window costs are the sum over the window's slots, an additive
    approximation that fits the solver's prefix-sum formulation."""

    def __init__(self, bundle: dict, trains: Arrays, weighted: Arrays, start_date: date):
        self.model = bundle["model"]
        self.sections = {code: i for i, code in enumerate(bundle["sections"])}
        self.slot_minutes = bundle.get("slot_minutes", 30)
        self.trains, self.weighted, self.start_date = trains, weighted, start_date

    def cost(self, section: str, day: int) -> list[int]:
        if section not in self.sections:
            raise ValueError(f"the delay model was not trained for section {section}")
        per_day = 24 * 60 // self.slot_minutes
        trains = self.trains.get(section, {}).get(day) or [0] * per_day
        weighted = self.weighted.get(section, {}).get(day) or [0] * per_day
        weekday = (self.start_date + timedelta(days=day)).weekday()
        trains_cum, weighted_cum = prefix_sums(trains), prefix_sums(weighted)
        empty = [0] * (per_day + 1)
        index = self.sections[section]
        with_traffic = [
            delay_row(index, slot, 1, weekday, trains_cum, weighted_cum, self.slot_minutes)
            for slot in range(per_day)
        ]
        without = [delay_row(index, slot, 1, weekday, empty, empty, self.slot_minutes) for slot in range(per_day)]
        both = np.array(with_traffic + without)
        predicted = np.asarray(self.model.predict(both), dtype=float)
        extra = (predicted[:per_day] - predicted[per_day:]).tolist()  # plain Python floats
        return [max(0, round(value)) for value in extra]


def _fallback(reason: str, cost: Arrays) -> tuple[Arrays, dict]:
    stats["ml_inference_fallback_total"] += 1
    log.warning("ml_inference_fallback: %s", reason)
    return cost, {"cost": "traffic_count", "ml_fallback": reason}


def choose_cost(
    db: Session,
    sections: list[str],
    cost: Arrays,
    trains: Arrays,
    days: int,
    start_date: date,
) -> tuple[Arrays, dict]:
    """Returns the cost arrays the planner should use and a small record of where they came from
    (stored with the plan run). `cost` holds the weighted train counts."""
    if not get_settings().ml_cost_enabled:
        return cost, {"cost": "traffic_count", "ml": "disabled"}
    row = active_model(db, "delay")
    if row is None:
        return _fallback("no active delay model", cost)
    if not trains:
        return _fallback("no traffic data to predict from", cost)
    try:
        bundle = load_bundle(row)
        provider = DelayModelCost(bundle, trains, cost, start_date)
        predicted = {
            section: {day: provider.cost(section, day) for day in range(days)} for section in sections
        }
    except (ModelLoadError, ValueError, KeyError, AttributeError, TypeError) as exc:
        return _fallback(f"delay model v{row.version}: {exc}", cost)
    except Exception as exc:  # noqa: BLE001  (whatever a model does, the plan must still run)
        return _fallback(f"delay model v{row.version} failed: {type(exc).__name__}", cost)
    return predicted, {"cost": f"delay_model:v{row.version}"}
