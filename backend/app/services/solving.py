"""The one place that decides how a solve is run: in a child process (the default) or in this one.

plan_runner and review_service both call `solve` from here, so what-if, override and plan runs
all get the same protection."""
from app.config import get_settings
from app.planner import model
from app.planner.isolated import solve_isolated
from app.planner.model import SolveResult
from app.planner.plan import Plan
from app.planner.snapshot import Snapshot


def solve(
    snapshot: Snapshot,
    *,
    hints: Plan | None = None,
    fixed: dict[int, tuple[int, int]] | None = None,
    time_limit_s: float = 60,
    seed: int = 1,
    workers: int | None = None,
) -> SolveResult:
    if get_settings().solver_isolation:
        return solve_isolated(
            snapshot, hints=hints, fixed=fixed, time_limit_s=time_limit_s, seed=seed, workers=workers
        )
    return model.solve(
        snapshot, hints=hints, fixed=fixed, time_limit_s=time_limit_s, seed=seed, workers=workers
    )
