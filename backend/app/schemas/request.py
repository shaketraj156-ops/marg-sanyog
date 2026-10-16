from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_core import PydanticCustomError

from app.config import get_settings

WorkType = Literal["track", "ohe", "signal", "bridge", "other"]
Relation = Literal["finish_before_start", "not_same_block", "same_block_allowed"]


def _check_duration(value: int | None) -> int | None:
    limit = get_settings().max_block_minutes
    if value is not None and value > limit:
        raise PydanticCustomError(
            "less_than_equal", "Input should be less than or equal to {le}", {"le": limit}
        )
    return value


def _check_aware(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        raise ValueError("must include a UTC offset, for example 2026-10-19T00:00:00+05:30")
    return value


class _RequestFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("duration_minutes", check_fields=False)
    @classmethod
    def duration_within_limit(cls, value):
        return _check_duration(value)

    @field_validator("preferred_start", check_fields=False)
    @classmethod
    def preferred_start_aware(cls, value):
        return _check_aware(value)


class BlockRequestIn(_RequestFields):
    section_code: str = Field(min_length=1, max_length=20)
    work_type: WorkType
    duration_minutes: int = Field(ge=15)
    earliest_date: date
    deadline_date: date
    priority: int = Field(ge=1, le=3)
    needs_power_block: bool = False
    preferred_start: datetime | None = None
    description: str | None = Field(default=None, max_length=500)
    # Planners and admins name the department; department users always use their own.
    department_code: str | None = Field(default=None, max_length=20)

    @model_validator(mode="after")
    def dates_in_order(self):
        if self.deadline_date < self.earliest_date:
            raise ValueError("deadline_date must not be before earliest_date")
        return self


class BlockRequestPatch(_RequestFields):
    version: int = Field(ge=1)
    section_code: str | None = Field(default=None, min_length=1, max_length=20)
    work_type: WorkType | None = None
    duration_minutes: int | None = Field(default=None, ge=15)
    earliest_date: date | None = None
    deadline_date: date | None = None
    priority: int | None = Field(default=None, ge=1, le=3)
    needs_power_block: bool | None = None
    preferred_start: datetime | None = None
    description: str | None = Field(default=None, max_length=500)


class VersionIn(BaseModel):
    version: int | None = Field(default=None, ge=1)


class RejectIn(VersionIn):
    reason: str = Field(min_length=1, max_length=500)


class DependencyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    depends_on: int = Field(ge=1)
    relation: Relation = "finish_before_start"
    min_gap_minutes: int = Field(default=0, ge=0, le=1440)


class DependenciesIn(VersionIn):
    dependencies: list[DependencyIn] = Field(max_length=50)


class DependencyOut(BaseModel):
    depends_on: int
    relation: str
    min_gap_minutes: int


class WarningOut(BaseModel):
    code: str
    detail: str
    request_ids: list[int]


class RequestOut(BaseModel):
    id: int
    status: str
    department: str
    section_code: str
    work_type: str
    description: str | None
    duration_minutes: int
    earliest_date: date
    deadline_date: date
    priority: int
    needs_power_block: bool
    preferred_start: str | None
    requested_by: int
    version: int
    dependencies: list[DependencyOut]
    created_at: str
    updated_at: str
    warnings: list[WarningOut] = []


class RequestListOut(BaseModel):
    items: list[RequestOut]
    next_cursor: int | None
