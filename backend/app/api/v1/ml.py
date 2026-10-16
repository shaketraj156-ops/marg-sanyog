from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_role
from app.core.errors import ProblemError
from app.core.timeutil import iso_ist
from app.db.models import MlModel, Section, User
from app.ml import registry
from app.ml.train import TRAINERS
from app.services import audit

router = APIRouter(prefix="/ml", tags=["ml"])

lookers = require_role("planner", "admin")
trainers = require_role("admin")


class TrainIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["delay", "overrun", "all"] = "all"
    seed: int = Field(default=1, ge=0, le=2**31 - 1)
    days: int = Field(default=120, ge=30, le=365)  # days of synthetic history to learn from


class ModelOut(BaseModel):
    id: int
    kind: str
    version: int
    is_active: bool
    beats_baseline: bool
    metrics: dict
    created_at: str


class ModelList(BaseModel):
    items: list[ModelOut]


class TrainOut(BaseModel):
    results: list[ModelOut]


def to_out(row: MlModel) -> ModelOut:
    return ModelOut(
        id=row.id,
        kind=row.kind,
        version=row.version,
        is_active=row.is_active,
        beats_baseline=bool(row.metrics.get("beats_baseline")),
        metrics=row.metrics,
        created_at=iso_ist(row.created_at),
    )


@router.get("/models", response_model=ModelList)
def list_models(_: User = Depends(lookers), db: Session = Depends(get_db)) -> ModelList:
    """Every trained model, newest first. The active one per kind is the one the planner may use."""
    return ModelList(items=[to_out(r) for r in registry.list_models(db)])


@router.post("/train", status_code=201, response_model=TrainOut)
def train(body: TrainIn, user: User = Depends(trainers), db: Session = Depends(get_db)) -> TrainOut:
    """Train on synthetic data, compare with the baseline on a later period, and register the
    result. A model becomes active only if it beats its baseline."""
    sections = list(db.scalars(select(Section.code)))
    if not sections:
        raise ProblemError(422, "no_sections", "There are no sections to train for; seed the data first")
    kinds = list(TRAINERS) if body.kind == "all" else [body.kind]
    rows = [
        registry.register(db, user, TRAINERS[kind](sections, body.seed, body.days)) for kind in kinds
    ]
    audit.record(
        db,
        user,
        "ml.train",
        "ml_model",
        rows[-1].id,
        {"models": [{"kind": r.kind, "version": r.version, "active": r.is_active} for r in rows]},
    )
    db.commit()
    return TrainOut(results=[to_out(r) for r in rows])
