from sqlalchemy import CheckConstraint, SmallInteger, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, BigPk


class Section(Base):
    __tablename__ = "sections"
    __table_args__ = (CheckConstraint("line_count IN (1, 2)", name="ck_sections_line_count"),)

    id: Mapped[int] = mapped_column(BigPk, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(Text, unique=True)  # for example A-B
    name: Mapped[str] = mapped_column(Text)
    division: Mapped[str] = mapped_column(Text)
    line_count: Mapped[int] = mapped_column(SmallInteger)
