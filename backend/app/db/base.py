from sqlalchemy import BigInteger, Integer, SmallInteger
from sqlalchemy.orm import DeclarativeBase

# Postgres gets SMALLSERIAL / BIGSERIAL keys; SQLite (used in tests) needs plain INTEGER
# primary keys to auto-increment.
SmallPk = SmallInteger().with_variant(Integer, "sqlite")
BigPk = BigInteger().with_variant(Integer, "sqlite")


class Base(DeclarativeBase):
    pass
