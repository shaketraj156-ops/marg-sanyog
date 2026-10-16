"""Smoke test: the demo script runs end to end in its own process and database."""
import os
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]


def _mtime(path: Path):
    return path.stat().st_mtime_ns if path.exists() else None


def test_demo_script_runs_and_the_integrated_plan_wins(tmp_path):
    real_database = BACKEND / "blockplanner.db"
    before = _mtime(real_database)
    env = {k: v for k, v in os.environ.items() if k not in ("DATABASE_URL", "JWT_SECRET")}
    result = subprocess.run(
        [sys.executable, "-m", "scripts.demo", "--time-limit", "10", "--db", str(tmp_path / "demo.db")],
        cwd=BACKEND,
        env={**env, "PYTHONPATH": str(BACKEND)},
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    out = result.stdout
    assert "Synthetic data only" in out, out
    assert "16 submitted across 4 sections" in out, out
    for heading in ("Closures", "Block hours", "Trains affected", "Integrated schedule", "Why (reason codes)"):
        assert heading in out, out
    line = next(row for row in out.splitlines() if row.startswith("Closures"))
    baseline, integrated = (int(x.replace(",", "")) for x in line.split()[1:3])
    assert integrated < baseline, out
    assert (tmp_path / "demo.db").exists()
    assert _mtime(real_database) == before, "the demo must never touch the real database"
