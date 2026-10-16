"""scripts/load_demo_data.py fills a database for a web-interface demo, and is careful about it."""
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]


def run(module, db_file, extra=(), **env):
    full = {
        **{k: v for k, v in os.environ.items() if k != "DATABASE_URL"},
        "DATABASE_URL": f"sqlite:///{db_file.as_posix()}",
        "PYTHONPATH": str(BACKEND),
        **env,
    }
    return subprocess.run(
        [sys.executable, "-m", module, *extra],
        cwd=BACKEND,
        env=full,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )


@pytest.fixture
def database(tmp_path):
    db_file = tmp_path / "app.db"
    assert run("alembic", db_file, ["upgrade", "head"]).returncode == 0
    return db_file


def count(db_file, table, where="1=1"):
    with sqlite3.connect(db_file) as connection:
        return connection.execute(f"SELECT COUNT(*) FROM {table} WHERE {where}").fetchone()[0]


def test_it_needs_the_seed_data_first(database):
    result = run("scripts.load_demo_data", database)
    assert result.returncode == 1
    assert "seed script first" in result.stderr
    assert count(database, "block_requests") == 0


def test_it_loads_requests_and_traffic_and_then_refuses_to_run_twice(database):
    assert run("scripts.seed_synthetic", database, SEED_PASSWORD="demo-pass-123").returncode == 0
    first = run("scripts.load_demo_data", database)
    assert first.returncode == 0, first.stderr
    assert "16 submitted requests" in first.stdout
    assert count(database, "block_requests", "status = 'submitted'") == 16
    assert count(database, "timetable_entries") > 100
    assert count(database, "traffic_profile") > 100
    assert count(database, "request_dependencies") == 2

    again = run("scripts.load_demo_data", database)
    assert again.returncode == 1 and "already has 16 requests" in again.stderr
    assert count(database, "block_requests") == 16  # nothing was added

    forced = run("scripts.load_demo_data", database, ["--add"])
    assert forced.returncode == 0
    assert count(database, "block_requests") == 32
