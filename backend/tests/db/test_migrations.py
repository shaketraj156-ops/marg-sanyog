"""Run the real Alembic migrations on a scratch SQLite file."""
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext

import app.db.models  # noqa: F401
from app.config import get_settings
from app.db.base import Base

BACKEND = Path(__file__).resolve().parents[2]
TABLES = set(Base.metadata.tables)  # every table the models define


@pytest.fixture
def alembic_cfg(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'migrations.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()  # migrations/env.py reads the URL from settings
    cfg = Config()
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    yield cfg, url
    get_settings.cache_clear()


def _tables(url):
    engine = sa.create_engine(url)
    try:
        return set(sa.inspect(engine).get_table_names()) - {"alembic_version"}
    finally:
        engine.dispose()


def test_upgrade_creates_tables_and_downgrade_removes_them(alembic_cfg):
    cfg, url = alembic_cfg
    command.upgrade(cfg, "head")
    assert _tables(url) == TABLES
    command.downgrade(cfg, "0001")
    assert _tables(url) == set()
    command.upgrade(cfg, "head")
    assert _tables(url) == TABLES


def test_migrations_match_the_models(alembic_cfg):
    cfg, url = alembic_cfg
    command.upgrade(cfg, "head")
    engine = sa.create_engine(url)
    try:
        with engine.connect() as connection:
            context = MigrationContext.configure(connection)
            diff = compare_metadata(context, Base.metadata)
    finally:
        engine.dispose()
    assert diff == []
