import sqlalchemy as sa
from sqlalchemy import ForeignKey, Index, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, BigPk, Json

EXPLANATION_CODES = (
    "MERGED",
    "LOW_TRAFFIC",
    "DEADLINE_DRIVEN",
    "DEPENDENCY_ORDER",
    "DEFERRED",
    "OVERRIDE",
)


class Explanation(Base):
    """A reason code with text and the numbers it was computed from."""

    __tablename__ = "explanations"
    __table_args__ = (Index("ix_explanations_run", "plan_run_id"),)

    id: Mapped[int] = mapped_column(BigPk, primary_key=True, autoincrement=True)
    plan_run_id: Mapped[int] = mapped_column(
        BigPk, ForeignKey("plan_runs.id", ondelete="CASCADE")
    )
    block_id: Mapped[int | None] = mapped_column(BigPk, ForeignKey("blocks.id"))
    request_id: Mapped[int | None] = mapped_column(BigPk, ForeignKey("block_requests.id"))
    code: Mapped[str] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text)
    numbers: Mapped[dict] = mapped_column(Json, default=dict, server_default=sa.text("'{}'"))
