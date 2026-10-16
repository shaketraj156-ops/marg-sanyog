from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy import BigInteger, Integer, SmallInteger
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase

# Postgres gets SMALLSERIAL / BIGSERIAL keys; SQLite (used in tests) needs plain INTEGER
# primary keys to auto-increment.
SmallPk = SmallInteger().with_variant(Integer, "sqlite")
BigPk = BigInteger().with_variant(Integer, "sqlite")

# JSONB on Postgres, plain JSON on SQLite.
Json = sa.JSON().with_variant(JSONB(), "postgresql")


class UTCDateTime(sa.TypeDecorator):
    """timestamptz that always comes back timezone-aware in UTC (SQLite drops the zone)."""

    impl = sa.DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


class Base(DeclarativeBase):
    pass
