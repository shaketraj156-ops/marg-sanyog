"""The solver runs in a child process, so a native crash cannot take the server down."""
import os
import time

from app.config import get_settings
from app.planner.isolated import CRASHED, _child, solve_isolated
from app.planner.model import SolveResult, solve
from app.services import solving
from tests.planner.factories import dep, quiet_night_traffic, req, snap


# Child-process stand-ins. They must be importable at module level because the child is "spawned".
def die_hard(conn, *args):
    os._exit(3)  # what a native abort looks like from outside


def uncaught_error(conn, *args):
    raise RuntimeError("boom")  # escapes everything: the child exits with code 1


def real_child_with_broken_input(conn, snapshot, *rest):
    _child(conn, {"broken": True}, *rest)  # the real child's own error handling reports it


def hang(conn, *args):
    time.sleep(60)


def close_without_answer(conn, *args):
    conn.close()


def instance():
    traffic = quiet_night_traffic("A-B", 7)
    return snap(
        [req(1, minutes=180), req(2, dept="SNT", minutes=120), req(3, dept="TRD", section="B-C")],
        deps=[dep(1, 2, gap=30)],
        cost=traffic,
        trains=traffic,
    )


def test_a_child_process_gives_the_same_answer_as_solving_here():
    snapshot = instance()
    here = solve(snapshot, time_limit_s=20, workers=1)
    there = solve_isolated(snapshot, time_limit_s=20, workers=1)
    assert there.status == here.status == "OPTIMAL"
    assert there.plan == here.plan
    assert there.objective == here.objective
    assert there.best_bound == here.best_bound


def test_hints_and_pinned_moves_reach_the_child():
    snapshot = snap([req(1, deadline=2), req(2, dept="SNT", deadline=2)], days=3)
    free = solve(snapshot, time_limit_s=10, workers=1)
    pinned = solve_isolated(snapshot, hints=free.plan, fixed={1: (2, 20)}, time_limit_s=10, workers=1)
    assert (pinned.plan.placements[1].day, pinned.plan.placements[1].offset) == (2, 20)


def test_an_infeasible_answer_comes_back_without_a_plan():
    snapshot = snap([req(1, deadline=1)], days=7)
    result = solve_isolated(snapshot, fixed={1: (5, 0)}, time_limit_s=5, workers=1)
    assert result.status == "INFEASIBLE" and result.plan is None


def test_a_hard_crash_of_the_child_is_reported_not_raised():
    result = solve_isolated(instance(), time_limit_s=5, _target=die_hard)
    assert result.status == CRASHED
    assert "exit code 3" in result.message
    assert result.plan is None


def test_an_exception_inside_the_solve_is_reported_with_its_message():
    result = solve_isolated(instance(), time_limit_s=5, _target=real_child_with_broken_input)
    assert result.status == CRASHED
    assert "KeyError" in result.message


def test_an_exception_that_escapes_the_child_is_a_crash_with_its_exit_code():
    result = solve_isolated(instance(), time_limit_s=5, _target=uncaught_error)
    assert result.status == CRASHED
    assert "exit code 1" in result.message


def test_a_child_that_closes_the_pipe_without_answering_is_a_crash():
    result = solve_isolated(instance(), time_limit_s=5, _target=close_without_answer)
    assert result.status == CRASHED


def test_a_child_that_hangs_is_stopped_after_the_deadline():
    started = time.monotonic()
    result = solve_isolated(instance(), time_limit_s=0.5, grace_s=0.5, _target=hang)
    assert result.status == "UNKNOWN"
    assert "did not answer" in result.message
    assert time.monotonic() - started < 15


def test_the_wait_can_be_cancelled():
    started = time.monotonic()
    result = solve_isolated(instance(), time_limit_s=30, _target=hang, should_stop=lambda: True)
    assert result.status == "UNKNOWN" and "stopped" in result.message
    assert time.monotonic() - started < 15


def test_the_parent_is_still_fine_after_a_crash():
    solve_isolated(instance(), time_limit_s=5, _target=die_hard)
    assert solve_isolated(instance(), time_limit_s=20, workers=1).status == "OPTIMAL"


def test_the_setting_chooses_between_child_process_and_in_process(monkeypatch):
    calls = []
    monkeypatch.setattr(solving, "solve_isolated", lambda *a, **k: calls.append("child") or SolveResult("OPTIMAL"))
    monkeypatch.setattr(solving.model, "solve", lambda *a, **k: calls.append("here") or SolveResult("OPTIMAL"))
    settings = get_settings()
    monkeypatch.setattr(settings, "solver_isolation", True)
    solving.solve(instance())
    monkeypatch.setattr(settings, "solver_isolation", False)
    solving.solve(instance())
    assert calls == ["child", "here"]
