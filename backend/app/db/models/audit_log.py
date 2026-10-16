from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import BigInteger, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, BigPk, Json, UTCDateTime


class AuditLog(Base):
    """Append-only record of state-changing actions. The app never updates or deletes rows."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigPk, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(UTCDateTime, server_default=sa.func.now())
    user_id: Mapped[int | None] = mapped_column(BigPk, ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(Text)
    entity: Mapped[str] = mapped_column(Text)
    entity_id: Mapped[int | None] = mapped_column(BigInteger)
    details: Mapped[dict] = mapped_column(Json, default=dict)
