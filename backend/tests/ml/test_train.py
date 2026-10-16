"""The models must beat their baselines on the future, and must not peek at it."""
import numpy as np
import pytest
from sklearn.ensemble import GradientBoostingRegressor

from app.ml import train as train_module
from app.ml.data import generate_delay_data, time_split
from app.ml.train import pinball_loss, train_delay, train_overrun

SECTIONS = ["A-B", "B-C", "C-D", "D-E"]


@pytest.fixture(scope="module")
def delay():
    return train_delay(SECTIONS, seed=1, days=90)


@pytest.fixture(scope="module")
def overrun():
    return train_overrun(SECTIONS, seed=1, days=90)


# ---------- beating the baselines ----------


def test_the_delay_model_beats_the_raw_train_count_baseline(delay):
    m = delay.metrics
    assert delay.beats_baseline and m["beats_baseline"]
    assert m["mae"] < m["baseline_mae"] * 0.7  # at least 30% lower error
    assert m["rmse"] < m["baseline_rmse"]
    assert m["improvement_percent"] > 30
    assert "number of trains" in m["baseline"]


def test_the_overrun_model_beats_the_per_work_type_percentile_baseline(overrun):
    m = overrun.metrics
    assert overrun.beats_baseline and m["beats_baseline"]
    assert m["pinball_loss"] < m["baseline_pinball_loss"]
    assert m["improvement_percent"] > 2
    assert "per kind of work" in m["baseline"]


def test_the_overrun_prediction_is_honest_about_how_often_it_is_exceeded(overrun):
    # a 75th percentile should cover about 75% of what really happens
    assert 0.65 <= overrun.metrics["coverage"] <= 0.85


def test_metrics_say_how_the_model_was_tested(delay, overrun):
    for result in (delay, overrun):
        m = result.metrics
        assert m["train_rows"] > m["test_rows"] > 0
        assert m["train_period"][1] < m["test_period"][0]  # ISO dates compare as text
        assert "time-based" in m["split"]


def test_the_bundle_has_everything_needed_to_use_the_model(delay, overrun):
    assert delay.bundle["kind"] == "delay" and overrun.bundle["kind"] == "overrun"
    assert delay.bundle["sections"] == SECTIONS
    assert len(delay.bundle["features"]) == 7 and len(overrun.bundle["features"]) == 5
    assert hasattr(delay.bundle["model"], "predict")


def test_training_twice_with_one_seed_gives_the_same_model():
    a = train_delay(SECTIONS, seed=3, days=40)
    b = train_delay(SECTIONS, seed=3, days=40)
    assert a.metrics == b.metrics


def test_a_model_that_is_only_slightly_better_does_not_count(monkeypatch):
    monkeypatch.setattr(train_module, "MIN_IMPROVEMENT", 0.99)
    result = train_delay(SECTIONS, seed=1, days=40)
    assert result.metrics["improvement_percent"] > 0  # it is better ...
    assert result.beats_baseline is False  # ... but not by enough, so it would not be activated


def test_pinball_loss_punishes_under_prediction_more_for_a_high_quantile():
    y = np.array([10.0, 10.0])
    assert pinball_loss(y, np.array([8.0, 8.0]), 0.75) == pytest.approx(1.5)  # under: 0.75 * 2
    assert pinball_loss(y, np.array([12.0, 12.0]), 0.75) == pytest.approx(0.5)  # over: 0.25 * 2
    assert pinball_loss(y, y, 0.75) == 0


# ---------- no leakage ----------


def test_a_model_trained_on_shuffled_targets_cannot_beat_the_baseline():
    """If the features leaked the answer, shuffling the targets would not matter. It does."""
    data = generate_delay_data(SECTIONS, 1, 90)
    train, test = time_split(data.days)
    shuffled = np.random.default_rng(0).permutation(data.y[train])
    model = GradientBoostingRegressor(n_estimators=100, max_depth=3, random_state=1).fit(data.X[train], shuffled)
    mae_shuffled = np.mean(np.abs(data.y[test] - np.maximum(model.predict(data.X[test]), 0)))
    honest = train_delay(SECTIONS, seed=1, days=90).metrics
    assert mae_shuffled > honest["baseline_mae"] * 0.9  # no better than the simple baseline
    assert mae_shuffled > honest["mae"] * 2  # and far worse than the real model


def test_the_model_never_sees_the_test_period_while_training(monkeypatch):
    """Scramble the targets of the test period only: the trained model must not change."""

    def predictions(scramble: bool):
        original = train_module.generate_delay_data

        def generator(*args, **kwargs):
            data = original(*args, **kwargs)
            if scramble:
                _, test = time_split(data.days)
                data.y[test] = np.random.default_rng(1).uniform(0, 500, test.sum())
            return data

        monkeypatch.setattr(train_module, "generate_delay_data", generator)
        result = train_delay(SECTIONS, seed=1, days=60)
        probe = original(SECTIONS, 1, 60).X[:200]
        return result.bundle["model"].predict(probe)

    assert np.array_equal(predictions(False), predictions(True))


def test_the_overrun_model_never_sees_the_test_period_while_training(monkeypatch):
    original = train_module.generate_overrun_data

    def predictions(scramble: bool):
        def generator(*args, **kwargs):
            data = original(*args, **kwargs)
            if scramble:
                _, test = time_split(data.days)
                data.y[test] = np.random.default_rng(1).uniform(0, 9, test.sum())
            return data

        monkeypatch.setattr(train_module, "generate_overrun_data", generator)
        result = train_overrun(SECTIONS, seed=1, days=60)
        return result.bundle["model"].predict(original(SECTIONS, 1, 60).X[:200])

    assert np.array_equal(predictions(False), predictions(True))


def test_the_split_used_for_training_is_the_time_split(monkeypatch):
    seen = {}
    original = train_module.time_split

    def spy(days, *args, **kwargs):
        masks = original(days, *args, **kwargs)
        seen["train_max"], seen["test_min"] = days[masks[0]].max(), days[masks[1]].min()
        return masks

    monkeypatch.setattr(train_module, "time_split", spy)
    train_delay(SECTIONS, seed=1, days=40)
    assert seen["train_max"] < seen["test_min"]
