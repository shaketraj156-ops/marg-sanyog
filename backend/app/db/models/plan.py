from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import CheckConstraint, ForeignKey, Index, SmallInteger, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, BigPk, Json, UTCDateTime

PLAN_STATUSES = (
    "queued",
    "running",
    "succeeded",
    "infeasible",
    "failed",
    "cancelled",
    "approved",
    "published",
    "superseded",
)
BLOCK_STATUSES = ("proposed", "published", "cancelled", "completed")


def _in_list(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


class PlanRun(Base):
    """One planner run with its settings and results. The stored plan is the record;
    re-running is not relied on to reproduce it."""

    __tablename__ = "plan_runs"
    __table_args__ = (
        CheckConstraint("horizon_end > horizon_start", name="ck_plan_runs_horizon"),
        CheckConstraint(_in_list("status", PLAN_STATUSES), name="ck_plan_runs_status"),
    )

    id: Mapped[int] = mapped_column(BigPk, primary_key=True, autoincrement=True)
    parent_id: Mapped[int | None] = mapped_column(BigPk, ForeignKey("plan_runs.id"))
    created_by: Mapped[int] = mapped_column(BigPk, ForeignKey("users.id"))
    horizon_start: Mapped[datetime] = mapped_column(UTCDateTime)
    horizon_end: Mapped[datetime] = mapped_column(UTCDateTime)
    slot_minutes: Mapped[int] = mapped_column(SmallInteger, server_default="30", default=30)
    weights: Mapped[dict] = mapped_column(Json)
    time_limit_s: Mapped[int] = mapped_column(sa.Integer, server_default="60", default=60)
    random_seed: Mapped[int] = mapped_column(sa.Integer, server_default="1", default=1)
    input_hash: Mapped[str | None] = mapped_column(Text)
    model_versions: Mapped[dict] = mapped_column(Json, default=dict)
    status: Mapped[str] = mapped_column(Text, server_default="queued", default="queued")
    solver_status: Mapped[str | None] = mapped_column(Text)
    objective_value: Mapped[float | None] = mapped_column(sa.Float)
    best_bound: Mapped[float | None] = mapped_column(sa.Float)
    metrics: Mapped[dict | None] = mapped_column(Json)
    error: Mapped[str | None] = mapped_column(Text)
    idempotency_key: Mapped[str | None] = mapped_column(Text, unique=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, server_default=sa.func.now())
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    approved_by: Mapped[int | None] = mapped_column(BigPk, ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    published_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    # Not in Appendix C: the exact input, the baseline and the plan, kept as the record so
    # what-if, override and the review endpoints work from what the run actually saw.
    snapshot: Mapped[dict | None] = mapped_column(Json)
    baseline: Mapped[dict | None] = mapped_column(Json)
    plan: Mapped[dict | None] = mapped_column(Json)


class Block(Base):
    """A closure of one section for a time window."""

    __tablename__ = "blocks"
    __table_args__ = (
        CheckConstraint("end_ts > start_ts", name="ck_blocks_window"),
        CheckConstraint(_in_list("status", BLOCK_STATUSES), name="ck_blocks_status"),
        Index("ix_blocks_section_start", "section_id", "start_ts"),
    )

    id: Mapped[int] = mapped_column(BigPk, primary_key=True, autoincrement=True)
    plan_run_id: Mapped[int] = mapped_column(BigPk, ForeignKey("plan_runs.id"))
    section_id: Mapped[int] = mapped_column(BigPk, ForeignKey("sections.id"))
    start_ts: Mapped[datetime] = mapped_column(UTCDateTime)
    end_ts: Mapped[datetime] = mapped_column(UTCDateTime)
    trains_affected: Mapped[int] = mapped_column(sa.Integer, server_default="0", default=0)
    status: Mapped[str] = mapped_column(Text, server_default="proposed", default="proposed")


class PlanAssignment(Base):
    """Where each request was placed in a run, or why it was not."""

    __tablename__ = "plan_assignments"
    __table_args__ = (
        UniqueConstraint("plan_run_id", "request_id", name="uq_plan_assignments_run_request"),
        Index("ix_plan_assignments_run", "plan_run_id"),
    )

    id: Mapped[int] = mapped_column(BigPk, primary_key=True, autoincrement=True)
    plan_run_id: Mapped[int] = mapped_column(
        BigPk, ForeignKey("plan_runs.id", ondelete="CASCADE")
    )
    request_id: Mapped[int] = mapped_column(BigPk, ForeignKey("block_requests.id"))
    block_id: Mapped[int | None] = mapped_column(BigPk, ForeignKey("blocks.id"))
    start_ts: Mapped[datetime | None] = mapped_column(UTCDateTime)
    end_ts: Mapped[datetime | None] = mapped_column(UTCDateTime)
    deferred: Mapped[bool] = mapped_column(server_default=sa.false(), default=False)
    defer_reason: Mapped[str | None] = mapped_column(Text)
    overridden: Mapped[bool] = mapped_column(server_default=sa.false(), default=False)
