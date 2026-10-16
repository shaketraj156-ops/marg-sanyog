"""Train the delay and overrun models and compare each with its baseline (spec section 11).

A model is only worth using if it beats a simple baseline on data from the future (the last part
of the period, never seen in training). The result says whether it did."""
from dataclasses import dataclass
from datetime import timedelta

import numpy as np
from sklearn.ensemble import GradientBoostingRegressor

from app.ml.data import (
    START,
    Dataset,
    generate_delay_data,
    generate_overrun_data,
    time_split,
)
from app.ml.features import DELAY_FEATURES, OVERRUN_FEATURES, SLOT_MINUTES

MIN_IMPROVEMENT = 0.02  # a model must be at least 2% better than its baseline to count
OVERRUN_QUANTILE = 0.75


@dataclass
class TrainResult:
    kind: str
    bundle: dict  # what is saved: the model plus what is needed to use it
    metrics: dict
    beats_baseline: bool


def pinball_loss(y: np.ndarray, predicted: np.ndarray, quantile: float) -> float:
    """Quantile loss: under-predicting costs `quantile`, over-predicting costs `1 - quantile`."""
    error = y - predicted
    return float(np.mean(np.maximum(quantile * error, (quantile - 1) * error)))


def _periods(data: Dataset, train: np.ndarray, test: np.ndarray) -> dict:
    def day(index: int) -> str:
        return (START + timedelta(days=int(index))).isoformat()

    return {
        "train_rows": int(train.sum()),
        "test_rows": int(test.sum()),
        "train_period": [day(data.days[train].min()), day(data.days[train].max())],
        "test_period": [day(data.days[test].min()), day(data.days[test].max())],
        "split": "time-based: the test period is entirely after the training period",
    }


def train_delay(sections: list[str], seed: int = 1, days: int = 120) -> TrainResult:
    data = generate_delay_data(sections, seed, days)
    train, test = time_split(data.days)
    model = GradientBoostingRegressor(
        n_estimators=250, max_depth=3, learning_rate=0.08, subsample=0.8, random_state=seed
    )
    model.fit(data.X[train], data.y[train])
    predicted = np.maximum(model.predict(data.X[test]), 0)

    # Baseline from the spec: delay proportional to the raw number of trains in the window.
    trains = data.extra["trains"]
    k = float((data.y[train] @ trains[train]) / max(1.0, float(trains[train] @ trains[train])))
    baseline = k * trains[test]

    mae = float(np.mean(np.abs(data.y[test] - predicted)))
    baseline_mae = float(np.mean(np.abs(data.y[test] - baseline)))
    metrics = {
        "target": "train-minutes lost by a closure window",
        "mae": round(mae, 3),
        "rmse": round(float(np.sqrt(np.mean((data.y[test] - predicted) ** 2))), 3),
        "baseline": "delay proportional to the number of trains in the window",
        "baseline_mae": round(baseline_mae, 3),
        "baseline_rmse": round(float(np.sqrt(np.mean((data.y[test] - baseline) ** 2))), 3),
        "improvement_percent": round(100 * (baseline_mae - mae) / baseline_mae, 1),
        **_periods(data, train, test),
    }
    beats = mae < baseline_mae * (1 - MIN_IMPROVEMENT)
    metrics["beats_baseline"] = beats
    bundle = {
        "kind": "delay",
        "model": model,
        "sections": sorted(sections),
        "features": list(DELAY_FEATURES),
        "slot_minutes": SLOT_MINUTES,
        "trained_with": {"seed": seed, "days": days},
    }
    return TrainResult("delay", bundle, metrics, beats)


def train_overrun(sections: list[str], seed: int = 1, days: int = 120) -> TrainResult:
    data = generate_overrun_data(sections, seed, days)
    train, test = time_split(data.days)
    model = GradientBoostingRegressor(
        loss="quantile",
        alpha=OVERRUN_QUANTILE,
        n_estimators=200,
        max_depth=3,
        learning_rate=0.08,
        subsample=0.8,
        random_state=seed,
    )
    model.fit(data.X[train], data.y[train])
    predicted = model.predict(data.X[test])

    # Baseline from the spec: the 75th percentile of the ratio for each kind of work.
    kinds = data.extra["work_type_idx"]
    per_kind = {int(k): float(np.quantile(data.y[train][kinds[train] == k], OVERRUN_QUANTILE)) for k in np.unique(kinds[train])}
    baseline = np.array([per_kind[int(k)] for k in kinds[test]])

    loss = pinball_loss(data.y[test], predicted, OVERRUN_QUANTILE)
    baseline_loss = pinball_loss(data.y[test], baseline, OVERRUN_QUANTILE)
    coverage = float(np.mean(data.y[test] <= predicted))
    metrics = {
        "target": "actual duration divided by planned duration (75th percentile)",
        "pinball_loss": round(loss, 4),
        "baseline": "75th percentile of the ratio per kind of work",
        "baseline_pinball_loss": round(baseline_loss, 4),
        "coverage": round(coverage, 3),
        "baseline_coverage": round(float(np.mean(data.y[test] <= baseline)), 3),
        "improvement_percent": round(100 * (baseline_loss - loss) / baseline_loss, 1),
        **_periods(data, train, test),
    }
    # Better than the baseline AND honest: about 75% of real outcomes should fall under the prediction.
    beats = loss < baseline_loss * (1 - MIN_IMPROVEMENT) and 0.65 <= coverage <= 0.85
    metrics["beats_baseline"] = beats
    bundle = {
        "kind": "overrun",
        "model": model,
        "sections": sorted(sections),
        "features": list(OVERRUN_FEATURES),
        "trained_with": {"seed": seed, "days": days},
    }
    return TrainResult("overrun", bundle, metrics, beats)


TRAINERS = {"delay": train_delay, "overrun": train_overrun}
