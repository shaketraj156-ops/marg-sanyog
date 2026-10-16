import pytest
from sklearn.dummy import DummyRegressor
from sqlalchemy.exc import IntegrityError

from app.db.models import MlModel
from app.ml import registry
from app.ml.registry import ModelLoadError
from app.ml.train import TrainResult
from tests.ml.stubs import LinearStub, bundle


def result(kind="delay", beats=True, model=None):
    model = model or DummyRegressor().fit([[0]], [0])
    return TrainResult(kind, bundle(model, kind), {"beats_baseline": beats, "mae": 1.0}, beats)


def test_the_first_model_is_version_one_and_active_when_it_beats_its_baseline(db):
    row = registry.register(db, None, result())
    assert (row.kind, row.version, row.is_active) == ("delay", 1, True)
    assert row.artifact_path == "delay-v1.joblib"
    assert (registry.model_dir() / "delay-v1.joblib").is_file()
    assert registry.active_model(db, "delay").id == row.id


def test_a_new_good_model_replaces_the_active_one(db):
    first = registry.register(db, None, result())
    second = registry.register(db, None, result())
    db.refresh(first)
    assert (second.version, second.is_active, first.is_active) == (2, True, False)
    assert registry.active_model(db, "delay").id == second.id


def test_a_model_that_does_not_beat_its_baseline_is_kept_but_never_activated(db):
    good = registry.register(db, None, result())
    bad = registry.register(db, None, result(beats=False))
    db.refresh(good)
    assert (bad.version, bad.is_active) == (2, False)
    assert good.is_active  # the earlier good model stays in charge
    assert registry.active_model(db, "delay").id == good.id


def test_with_only_a_bad_model_nothing_is_active(db):
    registry.register(db, None, result(beats=False))
    assert registry.active_model(db, "delay") is None


def test_kinds_have_their_own_versions_and_active_models(db):
    delay = registry.register(db, None, result("delay"))
    overrun = registry.register(db, None, result("overrun"))
    assert (delay.version, overrun.version) == (1, 1)
    assert delay.is_active and overrun.is_active


def test_the_database_allows_only_one_active_model_per_kind(db):
    registry.register(db, None, result())
    db.add(MlModel(kind="delay", version=9, metrics={}, artifact_path="x.joblib", is_active=True))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_the_database_refuses_duplicate_versions_and_unknown_kinds(db):
    registry.register(db, None, result())
    db.add(MlModel(kind="delay", version=1, metrics={}, artifact_path="x.joblib"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    db.add(MlModel(kind="weather", version=1, metrics={}, artifact_path="x.joblib"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_models_are_listed_newest_first(db):
    registry.register(db, None, result("delay"))
    registry.register(db, None, result("overrun"))
    registry.register(db, None, result("delay"))
    assert [(m.kind, m.version) for m in registry.list_models(db)] == [("delay", 2), ("overrun", 1), ("delay", 1)]


def test_a_saved_model_loads_and_predicts(db):
    row = registry.register(db, None, result(model=LinearStub()))
    loaded = registry.load_bundle(row)
    assert loaded["kind"] == "delay" and loaded["sections"] == ["A-B", "B-C", "C-D", "D-E"]
    assert list(loaded["model"].predict([[0, 0, 0, 0, 5, 0, 0]])) == [13]


def test_a_missing_model_file_is_a_clear_error(db):
    row = registry.register(db, None, result())
    (registry.model_dir() / row.artifact_path).unlink()
    with pytest.raises(ModelLoadError, match="missing"):
        registry.load_bundle(row)


def test_a_corrupt_model_file_is_a_clear_error(db):
    row = registry.register(db, None, result())
    (registry.model_dir() / row.artifact_path).write_bytes(b"this is not a model")
    with pytest.raises(ModelLoadError, match="cannot be read"):
        registry.load_bundle(row)


def test_a_file_of_the_wrong_kind_is_refused(db):
    row = registry.register(db, None, result("overrun"))
    row.kind = "delay"
    with pytest.raises(ModelLoadError, match="not a delay model"):
        registry.load_bundle(row)


def test_only_the_file_name_is_used_so_paths_cannot_escape_the_model_folder(db):
    row = registry.register(db, None, result())
    row.artifact_path = "../../../../etc/" + row.artifact_path
    assert registry.load_bundle(row)["kind"] == "delay"  # resolved inside MODEL_DIR, not outside
