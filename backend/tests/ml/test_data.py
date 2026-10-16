import numpy as np

from app.ml.data import generate_delay_data, generate_overrun_data, time_split
from app.ml.features import DELAY_FEATURES, OVERRUN_FEATURES, WORK_TYPES, delay_row
from app.planner.slots import prefix_sums

SECTIONS = ["A-B", "B-C", "C-D", "D-E"]


# ---------- features ----------


def test_a_delay_row_describes_the_window():
    trains = [0, 2, 1, 0, 3] + [0] * 43
    weighted = [0, 10, 3, 0, 6] + [0] * 43
    row = delay_row(2, 1, 3, 4, prefix_sums(trains), prefix_sums(weighted))
    assert row == [2.0, 0.5, 4.0, 3.0, 3.0, 13.0, 13 / 3]  # section, hour, weekday, slots, trains, weighted, mean


def test_an_empty_window_has_no_mean_weight():
    row = delay_row(0, 10, 2, 0, prefix_sums([0] * 48), prefix_sums([0] * 48))
    assert row[4:] == [0.0, 0.0, 0.0]


# ---------- generators ----------


def test_delay_data_is_the_same_for_the_same_seed_and_differs_for_another():
    a, b, c = (generate_delay_data(SECTIONS, seed, 20) for seed in (1, 1, 2))
    assert np.array_equal(a.X, b.X) and np.array_equal(a.y, b.y)
    assert not np.array_equal(a.y, c.y)


def test_delay_data_has_the_expected_shape():
    data = generate_delay_data(SECTIONS, 1, 30)
    assert data.X.shape == (30 * 4 * 12, len(DELAY_FEATURES))
    assert data.feature_names == DELAY_FEATURES
    assert set(np.unique(data.days)) == set(range(30))
    assert set(np.unique(data.X[:, 0])) == {0.0, 1.0, 2.0, 3.0}  # one index per section
    assert data.X[:, 3].min() >= 1 and data.X[:, 3].max() <= 12  # window of 1 to 12 slots


def test_delay_targets_are_never_negative_and_follow_the_traffic():
    data = generate_delay_data(SECTIONS, 1, 40)
    assert data.y.min() >= 0
    busy = data.X[:, 5] > np.percentile(data.X[:, 5], 75)
    quiet = data.X[:, 5] < np.percentile(data.X[:, 5], 25)
    assert data.y[busy].mean() > data.y[quiet].mean() * 2


def test_no_feature_is_a_copy_of_the_target():
    for data in (generate_delay_data(SECTIONS, 1, 30), generate_overrun_data(SECTIONS, 1, 30)):
        for column in range(data.X.shape[1]):
            assert not np.allclose(data.X[:, column], data.y), data.feature_names[column]
            assert abs(np.corrcoef(data.X[:, column], data.y)[0, 1]) < 0.99, data.feature_names[column]


def test_overrun_data_has_sensible_values():
    data = generate_overrun_data(SECTIONS, 1, 60)
    assert data.X.shape == (60 * 30, len(OVERRUN_FEATURES))
    assert data.y.min() >= 0.7
    assert set(np.unique(data.X[:, 0])) <= set(range(len(WORK_TYPES)))
    assert set(np.unique(data.X[:, 3])) <= set(range(1, 13))  # months
    assert 1 <= data.X[:, 4].min() and data.X[:, 4].max() <= 4  # crew size


def test_overrun_is_worse_in_the_monsoon_and_for_bridges():
    data = generate_overrun_data(SECTIONS, 1, 365)
    monsoon = (data.X[:, 3] >= 6) & (data.X[:, 3] <= 9)
    assert data.y[monsoon].mean() > data.y[~monsoon].mean()
    bridge = data.X[:, 0] == WORK_TYPES.index("bridge")
    track = data.X[:, 0] == WORK_TYPES.index("track")
    assert data.y[bridge].mean() > data.y[track].mean()


# ---------- the time-based split ----------


def test_everything_in_the_test_set_is_later_than_everything_in_training():
    for days in (50, 120, 365):
        data = np.repeat(np.arange(days), 7)
        train, test = time_split(data)
        assert data[train].max() < data[test].min()
        assert not (train & test).any() and (train | test).all()


def test_the_split_is_about_80_20_by_days():
    days = np.repeat(np.arange(100), 5)
    train, test = time_split(days)
    assert len(np.unique(days[test])) == 20 and len(np.unique(days[train])) == 80


def test_the_split_does_not_depend_on_row_order():
    days = np.repeat(np.arange(60), 4)
    shuffled = np.random.default_rng(0).permutation(days)
    train, test = time_split(shuffled)
    assert shuffled[train].max() < shuffled[test].min()
    assert sorted(np.unique(shuffled[test])) == sorted(np.unique(days[time_split(days)[1]]))


def test_no_day_is_split_between_training_and_test():
    data = generate_delay_data(SECTIONS, 1, 40)
    train, test = time_split(data.days)
    assert not set(data.days[train]) & set(data.days[test])
