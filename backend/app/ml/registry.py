"""The model registry: version, activate (only when the model beats its baseline), load.

Model files are saved with joblib, which is pickle underneath, so a model file can run code when
it is loaded. Only files this application wrote itself, named in the registry table and kept inside
MODEL_DIR, are ever loaded."""
from pathlib import Path

import joblib
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import MlModel, User
from app.ml.train import TrainResult


class ModelLoadError(Exception):
    """A registered model could not be loaded or does not look right."""


def model_dir() -> Path:
    path = Path(get_settings().model_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def next_version(db: Session, kind: str) -> int:
    return (db.scalar(select(func.max(MlModel.version)).where(MlModel.kind == kind)) or 0) + 1


def register(db: Session, user: User | None, result: TrainResult) -> MlModel:
    """Save the model file and add a registry row. The model becomes the active one of its kind
    only if it beat its baseline; otherwise it is kept for inspection and the active model stays."""
    version = next_version(db, result.kind)
    filename = f"{result.kind}-v{version}.joblib"
    joblib.dump(result.bundle, model_dir() / filename)
    row = MlModel(
        kind=result.kind,
        version=version,
        metrics=result.metrics,
        artifact_path=filename,
        is_active=False,
        trained_by=user.id if user else None,
    )
    db.add(row)
    db.flush()
    if result.beats_baseline:
        db.execute(
            update(MlModel)
            .where(MlModel.kind == result.kind, MlModel.is_active.is_(True), MlModel.id != row.id)
            .values(is_active=False)
        )
        row.is_active = True
    db.commit()
    return row


def active_model(db: Session, kind: str) -> MlModel | None:
    return db.scalar(select(MlModel).where(MlModel.kind == kind, MlModel.is_active.is_(True)))


def list_models(db: Session) -> list[MlModel]:
    return list(db.scalars(select(MlModel).order_by(MlModel.id.desc())))


def load_bundle(row: MlModel) -> dict:
    path = model_dir() / Path(row.artifact_path).name  # only the file name: no path tricks
    if not path.is_file():
        raise ModelLoadError(f"model file {path.name} is missing")
    try:
        bundle = joblib.load(path)
    except Exception as exc:
        raise ModelLoadError(f"model file {path.name} cannot be read: {type(exc).__name__}") from exc
    if not isinstance(bundle, dict) or bundle.get("kind") != row.kind or "model" not in bundle:
        raise ModelLoadError(f"model file {path.name} is not a {row.kind} model")
    return bundle
