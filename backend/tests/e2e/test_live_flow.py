"""The whole story over real HTTP, against a real server process and a real background solver."""
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]


def test_the_full_workflow_works_through_the_real_api():
    result = subprocess.run(
        [sys.executable, "-m", "scripts.e2e_check"],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        timeout=420,
        check=False,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "17/17 checks passed" in output, output
