from datetime import date, time

import sqlalchemy as sa
from sqlalchemy import CheckConstraint, ForeignKey, SmallInteger, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, BigPk

CATEGORIES = ("premium", "mail", "passenger", "local", "freight")
# Impact of one affected train: premium trains weigh more than goods trains.
CATEGORY_WEIGHT = {"premium": 5, "mail": 4, "passenger": 3, "local": 2, "freight": 1}


class TimetableEntry(Base):
    """One train passing through one section on the days in the bitmask."""

    __tablename__ = "timetable_entries"
    __table_args__ = (
        CheckConstraint(
            "category IN (" + ", ".join(f"'{c}'" for c in CATEGORIES) + ")",
            name="ck_timetable_entries_category",
        ),
        CheckConstraint("days_of_week BETWEEN 1 AND 127", name="ck_timetable_entries_days"),
    )

    id: Mapped[int] = mapped_column(BigPk, primary_key=True, autoincrement=True)
    train_no: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(Text)
    weight: Mapped[int] = mapped_column(SmallInteger, server_default="1", default=1)
    section_id: Mapped[int] = mapped_column(BigPk, ForeignKey("sections.id"))
    days_of_week: Mapped[int] = mapped_column(SmallInteger, server_default="127", default=127)
    enters_at: Mapped[time] = mapped_column(sa.Time)
    leaves_at: Mapped[time] = mapped_column(sa.Time)


class TrafficProfile(Base):
    """Trains per slot per section per day, derived from the timetable. Only slots with
    at least one train are stored."""

    __tablename__ = "traffic_profile"

    section_id: Mapped[int] = mapped_column(
        BigPk, ForeignKey("sections.id"), primary_key=True, autoincrement=False
    )
    day: Mapped[date] = mapped_column(sa.Date, primary_key=True)
    slot_index: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=False)
    trains: Mapped[int] = mapped_column(SmallInteger)
    weighted: Mapped[int] = mapped_column(sa.Integer)
