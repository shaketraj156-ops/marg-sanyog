from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PlanWeights(BaseModel):
    model_config = ConfigDict(extra="forbid")

    block: int = Field(default=150, ge=0, le=100_000)
    traffic: int = Field(default=10, ge=0, le=100_000)
    delay: int = Field(default=20, ge=0, le=100_000)
    defer: int = Field(default=1000, ge=0, le=1_000_000)


class PlanCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    horizon_start: datetime
    horizon_end: datetime
    slot_minutes: int = 30
    weights: PlanWeights = PlanWeights()
    time_limit_s: int = Field(default=60, ge=1, le=600)
    seed: int = Field(default=1, ge=0, le=2**31 - 1)

    @field_validator("horizon_start", "horizon_end")
    @classmethod
    def must_have_offset(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("must include a UTC offset, for example 2026-10-19T00:00:00+05:30")
        return value


class PlanAccepted(BaseModel):
    id: int
    status: str
    links: dict[str, str]


class PlanOut(BaseModel):
    id: int
    parent_id: int | None
    status: str
    solver_status: str | None
    horizon_start: str
    horizon_end: str
    slot_minutes: int
    weights: dict
    time_limit_s: int
    seed: int
    input_hash: str | None
    objective_value: float | None
    best_bound: float | None
    gap: float | None
    metrics: dict | None
    model_versions: dict  # where the cost came from: delay model version or train counts
    deferred_request_ids: list[int]
    error: str | None
    created_by: int
    created_at: str
    finished_at: str | None
    approved_at: str | None
    published_at: str | None


class PlanListOut(BaseModel):
    items: list[PlanOut]
    next_cursor: int | None
