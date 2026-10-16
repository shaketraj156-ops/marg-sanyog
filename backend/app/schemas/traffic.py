from datetime import date, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Category = Literal["premium", "mail", "passenger", "local", "freight"]


class TimetableEntryIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    train_no: str = Field(min_length=1, max_length=20)
    category: Category
    weight: int | None = Field(default=None, ge=1, le=10)  # defaults from the category
    section_code: str = Field(min_length=1, max_length=20)
    days_of_week: int = Field(default=127, ge=1, le=127)  # bitmask, Monday is bit 0
    enters_at: time
    leaves_at: time


class TimetableUploadIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entries: list[TimetableEntryIn] = Field(max_length=5000)
    replace: bool = False  # delete the existing timetable first


class SyntheticIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seed: int = Field(default=1, ge=0, le=2**31 - 1)
    replace: bool = True


class RebuildIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date_from: date
    date_to: date


class InsertedOut(BaseModel):
    inserted: int


class RebuildOut(BaseModel):
    days: int
    sections: int
    rows: int


class ProfileDay(BaseModel):
    date: date
    trains: list[int]
    weighted: list[int]


class ProfileOut(BaseModel):
    section_code: str
    slot_minutes: int
    days: list[ProfileDay]
