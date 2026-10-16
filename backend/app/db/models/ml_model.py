from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import CheckConstraint, ForeignKey, Index, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, BigPk, Json, UTCDateTime

ML_KINDS = ("delay", "overrun")


class MlModel(Base):
    """Registry of trained models. At most one model per kind is active."""

    __tablename__ = "ml_models"
    __table_args__ = (
        CheckConstraint("kind IN ('delay', 'overrun')", name="ck_ml_models_kind"),
        UniqueConstraint("kind", "version", name="uq_ml_models_kind_version"),
        # one active model per kind, enforced by the database
        Index(
            "uq_ml_models_one_active",
            "kind",
            unique=True,
            sqlite_where=sa.text("is_active"),
            postgresql_where=sa.text("is_active"),
        ),
    )

    id: Mapped[int] = mapped_column(BigPk, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(sa.Integer)
    metrics: Mapped[dict] = mapped_column(Json)
    artifact_path: Mapped[str] = mapped_column(Text)  # file name inside MODEL_DIR
    is_active: Mapped[bool] = mapped_column(server_default=sa.false(), default=False)
    trained_by: Mapped[int | None] = mapped_column(BigPk, ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, server_default=sa.func.now())
