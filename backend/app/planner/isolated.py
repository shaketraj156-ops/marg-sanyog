"""Run a solve in a child process.

OR-Tools is native code. If it ever aborts (it has: see the note in model.py), the process that
called it dies. Inside the API server that would take every user's session down with one bad
plan run. In a child process the worst case is a failed run: the parent notices the exit and
reports it. The child is started with "spawn", so it shares nothing with the parent.

The planner package stays free of database and web imports: this module only needs the standard
library and the planner itself.
"""
import multiprocessing
import time
from collections.abc import Callable

from app.planner.model import SolveResult
from app.planner.plan import Plan
from app.planner.snapshot import Snapshot

CRASHED = "CRASHED"


def _child(conn, snapshot: dict, hints: dict | None, fixed, time_limit_s, seed, workers) -> None:
    """Runs in the child process: solve and send back a plain-dict result."""
    try:
        from app.planner.model import solve  # imported here so the child loads OR-Tools itself

        result = solve(
            Snapshot.from_dict(snapshot),
            hints=Plan.from_dict(hints) if hints else None,
            fixed=fixed,
            time_limit_s=time_limit_s,
            seed=seed,
            workers=workers,
        )
        conn.send(
            {
                "status": result.status,
                "plan": result.plan.to_dict() if result.plan else None,
                "objective": result.objective,
                "best_bound": result.best_bound,
                "wall_time_s": result.wall_time_s,
            }
        )
    except Exception as exc:  # noqa: BLE001  (report it to the parent instead of dying silently)
        conn.send({"error": f"{type(exc).__name__}: {exc}"})
    finally:
        conn.close()


def solve_isolated(
    snapshot: Snapshot,
    *,
    hints: Plan | None = None,
    fixed: dict[int, tuple[int, int]] | None = None,
    time_limit_s: float = 60,
    seed: int = 1,
    workers: int | None = None,
    should_stop: Callable[[], bool] | None = None,
    grace_s: float = 60,
    _target: Callable | None = None,
) -> SolveResult:
    """Same answer as model.solve, computed in a child process.

    If the child dies or does not answer within time_limit_s + grace_s, the result has status
    "CRASHED" (or "UNKNOWN" for a time-out) and a message; nothing is raised."""
    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(
        target=_target or _child,
        args=(
            sender,
            snapshot.to_dict(),
            hints.to_dict() if hints else None,
            fixed,
            time_limit_s,
            seed,
            workers,
        ),
        daemon=True,
    )
    started = time.monotonic()
    process.start()
    sender.close()  # the parent keeps only the receiving end, so a dead child ends the wait
    deadline = started + time_limit_s + grace_s
    payload = None
    timed_out = stopped = False
    try:
        while True:
            if receiver.poll(0.2):
                try:
                    payload = receiver.recv()
                except EOFError:
                    payload = None  # the child closed the pipe without answering
                break
            if not process.is_alive():
                break
            if time.monotonic() > deadline:
                timed_out = True
                break
            if should_stop is not None and should_stop():
                stopped = True
                break
    finally:
        # A child that has answered, or died, is about to exit: let it, so its exit code is real.
        process.join(0 if (timed_out or stopped) else 5)
        if process.is_alive():
            process.terminate()
            process.join(10)
        if process.is_alive():
            process.kill()
        receiver.close()

    elapsed = time.monotonic() - started
    if payload is not None and "error" not in payload:
        return SolveResult(
            payload["status"],
            Plan.from_dict(payload["plan"]) if payload["plan"] else None,
            payload["objective"],
            payload["best_bound"],
            payload["wall_time_s"],
        )
    if payload is not None:
        return SolveResult(CRASHED, wall_time_s=elapsed, message=payload["error"])
    if timed_out:
        return SolveResult("UNKNOWN", wall_time_s=elapsed, message="the solver did not answer in time")
    if stopped:
        return SolveResult("UNKNOWN", wall_time_s=elapsed, message="stopped on request")
    return SolveResult(
        CRASHED, wall_time_s=elapsed, message=f"the solver process ended with exit code {process.exitcode}"
    )
