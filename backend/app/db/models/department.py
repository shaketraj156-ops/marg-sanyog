from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, SmallPk


class Department(Base):
    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(SmallPk, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(Text, unique=True)  # ENGG, TRD, SNT
    name: Mapped[str] = mapped_column(Text)
