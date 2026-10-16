from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MoveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: int = Field(ge=1)
    start: datetime  # new start, on the planning grid (for example every 30 minutes)

    @field_validator("start")
    @classmethod
    def must_have_offset(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("must include a UTC offset, for example 2026-10-20T02:00:00+05:30")
        return value


class WhatIfIn(MoveIn):
    time_limit_s: int = Field(default=5, ge=1, le=60)


class OverrideIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    moves: list[MoveIn] = Field(min_length=1, max_length=20)
    time_limit_s: int = Field(default=10, ge=1, le=120)


class ExplanationOut(BaseModel):
    id: int
    code: str
    text: str
    numbers: dict
    block_id: int | None
    request_id: int | None


class ExplanationsOut(BaseModel):
    plan_id: int
    items: list[ExplanationOut]
