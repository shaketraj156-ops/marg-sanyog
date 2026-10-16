from datetime import date, datetime

import sqlalchemy as sa
from sqlalchemy import CheckConstraint, ForeignKey, Index, SmallInteger, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BigPk, SmallPk, UTCDateTime
from app.db.models.department import Department
from app.db.models.section import Section

REQUEST_STATUSES = (
    "draft",
    "submitted",
    "scheduled",
    "published",
    "completed",
    "cancelled",
    "rejected",
)
DEPENDENCY_RELATIONS = ("finish_before_start", "not_same_block", "same_block_allowed")


def _in_list(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


class RequestDependency(Base):
    """request_id depends on depends_on_request_id."""

    __tablename__ = "request_dependencies"
    __table_args__ = (
        CheckConstraint(
            _in_list("relation", DEPENDENCY_RELATIONS), name="ck_request_dependencies_relation"
        ),
        CheckConstraint(
            "request_id <> depends_on_request_id", name="ck_request_dependencies_not_self"
        ),
    )

    request_id: Mapped[int] = mapped_column(
        BigPk, ForeignKey("block_requests.id", ondelete="CASCADE"), primary_key=True
    )
    depends_on_request_id: Mapped[int] = mapped_column(
        BigPk, ForeignKey("block_requests.id", ondelete="CASCADE"), primary_key=True
    )
    relation: Mapped[str] = mapped_column(Text)
    min_gap_minutes: Mapped[int] = mapped_column(sa.Integer, server_default="0", default=0)


class BlockRequest(Base):
    __tablename__ = "block_requests"
    __table_args__ = (
        CheckConstraint("duration_minutes BETWEEN 15 AND 720", name="ck_block_requests_duration"),
        CheckConstraint("priority BETWEEN 1 AND 3", name="ck_block_requests_priority"),
        CheckConstraint("deadline_date >= earliest_date", name="ck_block_requests_dates"),
        CheckConstraint(_in_list("status", REQUEST_STATUSES), name="ck_block_requests_status"),
        Index("ix_block_requests_status_section", "status", "section_id"),
    )

    id: Mapped[int] = mapped_column(BigPk, primary_key=True, autoincrement=True)
    department_id: Mapped[int] = mapped_column(SmallPk, ForeignKey("departments.id"))
    section_id: Mapped[int] = mapped_column(BigPk, ForeignKey("sections.id"))
    requested_by: Mapped[int] = mapped_column(BigPk, ForeignKey("users.id"))
    work_type: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    duration_minutes: Mapped[int] = mapped_column(sa.Integer)
    earliest_date: Mapped[date] = mapped_column(sa.Date)
    deadline_date: Mapped[date] = mapped_column(sa.Date)
    priority: Mapped[int] = mapped_column(SmallInteger)
    needs_power_block: Mapped[bool] = mapped_column(server_default=sa.false(), default=False)
    preferred_start: Mapped[datetime | None] = mapped_column(UTCDateTime)
    status: Mapped[str] = mapped_column(Text, server_default="draft", default="draft")
    # Optimistic locking: SQLAlchemy adds "AND version = <old>" to every UPDATE and bumps it.
    version: Mapped[int] = mapped_column(sa.Integer, server_default="1")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, server_default=sa.func.now())
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, server_default=sa.func.now())

    __mapper_args__ = {"version_id_col": version}  # noqa: RUF012

    department: Mapped[Department] = relationship(lazy="joined")
    section: Mapped[Section] = relationship(lazy="joined")
    dependencies: Mapped[list[RequestDependency]] = relationship(
        lazy="selectin",
        cascade="all, delete-orphan",
        foreign_keys=[RequestDependency.request_id],
        order_by=RequestDependency.depends_on_request_id,
    )
