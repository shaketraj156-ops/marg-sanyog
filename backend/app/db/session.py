from functools import lru_cache

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings


def _sqlite_foreign_keys_on(dbapi_connection, _record) -> None:
    dbapi_connection.execute("PRAGMA foreign_keys=ON")


@lru_cache
def get_engine() -> Engine:
    url = get_settings().database_url
    if url.startswith("sqlite"):
        # Sync endpoints run in a thread pool, so SQLite must allow cross-thread use.
        engine = create_engine(url, connect_args={"check_same_thread": False})
        event.listen(engine, "connect", _sqlite_foreign_keys_on)
        return engine
    return create_engine(url, pool_pre_ping=True)


def get_session() -> Session:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)()
