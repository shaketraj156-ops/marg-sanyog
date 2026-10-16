"""Runs a plan in a background thread: snapshot, baseline, solve, check, save.

Solving is CPU-bound, so it never happens inside an API request. One solve runs at a time
per process (the solver uses the CPU cores); other runs wait in the queued state."""
import logging
import threading
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import PlanRun
from app.db.session import get_session
from app.planner.baseline import baseline_plan
from app.planner.checker import check_plan
from app.planner.metrics import compute_metrics, objective
from app.planner.model import SolveResult
from app.planner.warmstart import greedy_plan
from app.services import explain, plan_service
from app.services.solving import solve

log = logging.getLogger(__name__)
_solve_lock = threading.Lock()


def open_session() -> Session:
    return get_session()


def run_plan(run_id: int) -> None:
    """Idempotent: only a queued run starts, so a repeated delivery does nothing."""
    with _solve_lock:
        db = open_session()
        try:
            _execute(db, run_id)
        except Exception as exc:
            log.exception("plan run %s failed", run_id)
            _fail(db, run_id, f"{type(exc).__name__}: {exc}")
        finally:
            db.close()


def _fail(db: Session, run_id: int, message: str) -> None:
    db.rollback()
    run = db.get(PlanRun, run_id)
    if run is None:
        return
    run.status = "failed"
    run.error = message[:1000]
    run.finished_at = datetime.now(UTC)
    db.commit()


def _execute(db: Session, run_id: int) -> None:
    run = db.get(PlanRun, run_id)
    if run is None or run.status != "queued":
        return
    run.status = "running"
    db.commit()

    snapshot = plan_service.build_snapshot(db, run)
    baseline = baseline_plan(snapshot)
    start = greedy_plan(snapshot)  # a valid start; the baseline is not (it ignores the rules)
    result = solve(
        snapshot,
        hints=start,
        time_limit_s=run.time_limit_s,
        seed=run.random_seed,
        workers=get_settings().solver_workers or None,
    )

    if result.status == "UNKNOWN" and result.plan is None:
        # The solver ran out of time before it could improve on the starting plan (it has to
        # expand the model first, which takes seconds on big instances). The starting plan is
        # valid, so the run still succeeds with it, and says so.
        result = SolveResult(
            "FEASIBLE",
            start,
            float(objective(snapshot, start)),
            None,
            result.wall_time_s,
            "The time limit ended before the solver improved on the starting plan; "
            "run again with a longer limit for a better one.",
        )

    if result.status in ("OPTIMAL", "FEASIBLE"):
        violations = check_plan(snapshot, result.plan)
        if violations:  # never save a plan that fails the independent checker
            log.error("checker rejected plan run %s: %s", run_id, violations)
            _fail(db, run_id, "Checker rejected the plan: " + "; ".join(violations[:5]))
            return
        metrics = {
            "baseline": compute_metrics(snapshot, baseline),
            "integrated": compute_metrics(snapshot, result.plan),
            "solver": {
                "wall_time_s": round(result.wall_time_s, 2),
                "gap": result.gap,
                "note": result.message,
            },
        }
        plan_service.save_result(
            db,
            run,
            snapshot,
            result.plan,
            baseline,
            metrics,
            result.status,
            result.objective,
            result.best_bound,
        )
        _after_save(db, run, snapshot, result.plan, baseline)
        db.commit()
    elif result.status == "INFEASIBLE":
        run.status = "infeasible"
        run.solver_status = result.status
        run.error = "No plan satisfies the hard constraints"
        run.finished_at = datetime.now(UTC)
        db.commit()
    elif result.status == "CRASHED":
        log.error("the solver crashed on plan run %s: %s", run_id, result.message)
        _fail(
            db,
            run_id,
            f"The solver stopped unexpectedly ({result.message}). The server is unaffected; run the plan again.",
        )
    else:
        _fail(db, run_id, f"Solver ended with {result.status}: no solution within the time limit")


def _after_save(db, run, snapshot, plan, baseline) -> None:
    """Work that belongs in the same transaction as the saved plan."""
    db.flush()
    drafts = explain.explain(
        snapshot, plan, baseline, plan_service.horizon_start_date(run)
    )
    explain.save(db, run, drafts)


def start_in_background(run_id: int) -> None:
    thread = threading.Thread(target=run_plan, args=(run_id,), name=f"plan-{run_id}", daemon=True)
    thread.start()


# Tests replace this with a function that runs the plan inline.
submit = start_in_background
