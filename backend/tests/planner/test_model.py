"""Solver tests on instances small enough to solve by hand."""
import random

import pytest

from app.planner.baseline import baseline_plan
from app.planner.checker import check_plan
from app.planner.metrics import compute_metrics, objective
from app.planner.model import solve
from app.planner.plan import Plan, span_blocks
from app.planner.snapshot import DEPENDENCY_UNMET, NO_CAPACITY, OUT_OF_HORIZON, TOO_LONG
from tests.planner.factories import dep, quiet_night_traffic, req, snap


def run(snapshot, **kwargs):
    kwargs.setdefault("time_limit_s", 20)
    kwargs.setdefault("workers", 1)
    result = solve(snapshot, **kwargs)
    assert result.status in ("OPTIMAL", "FEASIBLE"), result.status
    assert check_plan(snapshot, result.plan) == [], check_plan(snapshot, result.plan)
    return result


def test_three_requests_on_one_section_share_one_closure():
    snapshot = snap(
        [
            req(1, dept="ENGG", minutes=180),
            req(2, dept="SNT", minutes=120),
            req(3, dept="TRD", minutes=120),
        ]
    )
    result = run(snapshot)
    assert result.status == "OPTIMAL"
    assert len(result.plan.blocks) == 1
    assert result.plan.blocks[0].request_ids == (1, 2, 3)
    assert not result.plan.deferred


def test_merged_window_is_as_short_as_possible():
    snapshot = snap(
        [
            req(1, dept="ENGG", minutes=180, deadline=2),
            req(2, dept="SNT", minutes=120, deadline=2),
        ],
        days=3,
    )
    result = run(snapshot)
    block = result.plan.blocks[0]
    assert block.end - block.start == 6  # the longer request, run in parallel with the other


def test_requests_on_different_sections_cannot_share_a_closure():
    snapshot = snap([req(1, section="A-B"), req(2, section="B-C", dept="TRD")])
    assert len(run(snapshot).plan.blocks) == 2


def test_integrated_plan_beats_independent_planning():
    requests = [req(i, dept=d, section="A-B") for i, d in enumerate(["ENGG", "TRD", "SNT"], 1)]
    snapshot = snap(requests)
    baseline = baseline_plan(snapshot)
    result = run(snapshot, hints=baseline)
    assert compute_metrics(snapshot, baseline)["closures"] == 3
    assert compute_metrics(snapshot, result.plan)["closures"] == 1


def test_work_goes_to_the_quiet_night():
    snapshot = snap(
        [req(1, minutes=120, earliest=0, deadline=0)],
        cost=quiet_night_traffic("A-B", 7),
    )
    block = run(snapshot).plan.blocks[0]
    assert block.end <= 12  # inside the 00:00-06:00 quiet window


def test_requests_pile_into_the_same_quiet_day_when_possible():
    snapshot = snap(
        [req(1, minutes=120, deadline=4), req(2, dept="TRD", minutes=120, deadline=4)],
        cost=quiet_night_traffic("A-B", 7),
    )
    plan = run(snapshot).plan
    assert plan.placements[1].day == plan.placements[2].day
    assert len(plan.blocks) == 1


def test_requests_are_not_postponed_without_a_reason():
    snapshot = snap([req(1, earliest=2, deadline=5)])
    assert run(snapshot).plan.placements[1].day == 2


def test_higher_priority_is_postponed_less():
    # One crew, one section, one day too short for both: the second one must move a day.
    snapshot = snap(
        [
            req(1, minutes=360, earliest=0, deadline=1, priority=1),
            req(2, minutes=360, earliest=0, deadline=1, priority=3),
        ],
        crews={"ENGG": 1},
    )
    plan = run(snapshot).plan
    # Two 6-hour jobs cannot share one 6-hour closure with a single crew.
    assert plan.placements[2].day == 0
    assert plan.placements[1].day == 1


def test_start_never_crosses_midnight():
    snapshot = snap([req(1, minutes=360, deadline=0)], cost={"A-B": {0: [1] * 24 + [50] * 24}})
    placement = run(snapshot).plan.placements[1]
    assert placement.offset + placement.slots <= 48


# ---------- dependencies ----------


def test_finish_before_start_with_a_gap_is_respected():
    snapshot = snap(
        [
            req(1, dept="ENGG", minutes=180, deadline=1),
            req(2, dept="SNT", minutes=120, deadline=1),
        ],
        deps=[dep(1, 2, gap=60)],
        days=2,
    )
    plan = run(snapshot).plan
    first, second = plan.placements[1], plan.placements[2]
    end_of_first = first.day * 48 + first.end
    assert end_of_first + 2 <= second.day * 48 + second.offset


def test_dependent_requests_can_still_share_a_closure_when_ordered():
    snapshot = snap(
        [
            req(1, dept="ENGG", minutes=120, deadline=1),
            req(2, dept="SNT", minutes=120, deadline=1),
        ],
        deps=[dep(1, 2)],
        days=2,
    )
    plan = run(snapshot).plan
    assert len(plan.blocks) == 1
    assert plan.placements[2].offset >= plan.placements[1].end


def test_not_same_block_puts_requests_on_different_days():
    snapshot = snap(
        [req(1, deadline=2), req(2, dept="SNT", deadline=2)],
        deps=[dep(1, 2, "not_same_block")],
        days=3,
    )
    plan = run(snapshot).plan
    assert plan.placements[1].day != plan.placements[2].day


def test_same_block_allowed_does_not_stop_sharing():
    snapshot = snap([req(1), req(2, dept="SNT")], deps=[dep(1, 2, "same_block_allowed")])
    assert len(run(snapshot).plan.blocks) == 1


# ---------- deferral ----------


def test_a_request_that_cannot_fit_is_deferred_with_its_follow_up():
    snapshot = snap(
        [req(1, minutes=480, dept="ENGG"), req(2, dept="SNT"), req(3, dept="TRD")],
        deps=[dep(1, 2)],
    )
    plan = run(snapshot).plan
    assert plan.deferred == {1: TOO_LONG, 2: DEPENDENCY_UNMET}
    assert set(plan.placements) == {3}


def test_out_of_horizon_requests_are_deferred_not_fatal():
    snapshot = snap([req(1, deadline=30), req(2)])
    plan = run(snapshot).plan
    assert plan.deferred == {1: OUT_OF_HORIZON}


def test_deferral_when_crews_cannot_cover_the_work():
    # One crew; three 6-hour jobs on one section and one day cannot share a 6-hour closure.
    snapshot = snap(
        [req(i, minutes=360, earliest=0, deadline=0, priority=p) for i, p in [(1, 1), (2, 2), (3, 3)]],
        crews={"ENGG": 1},
    )
    plan = run(snapshot).plan
    assert set(plan.placements) == {3}  # highest priority wins
    assert plan.deferred == {1: NO_CAPACITY, 2: NO_CAPACITY}


def test_crew_limit_is_enforced_across_sections():
    snapshot = snap(
        [
            req(1, section="A-B", minutes=180, deadline=0),
            req(2, section="B-C", minutes=180, deadline=0),
        ],
        crews={"ENGG": 1},
        days=1,
    )
    plan = run(snapshot).plan
    one, two = plan.placements[1], plan.placements[2]
    assert one.end <= two.offset or two.end <= one.offset


def test_empty_instance_is_trivially_solved():
    result = solve(snap([]), time_limit_s=5, workers=1)
    assert result.status == "OPTIMAL"
    assert result.plan.placements == {} and result.plan.blocks == []


# ---------- hints, fixed moves, stopping ----------


def test_fixed_move_is_respected_and_others_adapt():
    snapshot = snap([req(1, deadline=2), req(2, dept="SNT", deadline=2)], days=3)
    free = run(snapshot).plan
    moved = run(snapshot, fixed={1: (2, 20)}, hints=free).plan
    assert (moved.placements[1].day, moved.placements[1].offset) == (2, 20)
    # Request 2 follows request 1 into the same closure rather than opening another.
    assert moved.placements[2].day == 2


def test_fixed_move_outside_the_window_is_infeasible():
    snapshot = snap([req(1, deadline=1)], days=7)
    assert solve(snapshot, fixed={1: (5, 0)}, time_limit_s=5, workers=1).status == "INFEASIBLE"
    assert solve(snapshot, fixed={99: (0, 0)}, time_limit_s=5, workers=1).status == "INFEASIBLE"
    assert solve(snapshot, fixed={1: (0, 47)}, time_limit_s=5, workers=1).status == "INFEASIBLE"


def test_fixed_move_that_breaks_a_dependency_is_infeasible_or_defers_the_other():
    snapshot = snap(
        [req(1, minutes=120, deadline=0), req(2, dept="SNT", minutes=120, deadline=0)],
        deps=[dep(1, 2)],
        days=1,
    )
    result = solve(snapshot, fixed={1: (0, 40), 2: (0, 0)}, time_limit_s=5, workers=1)
    assert result.status == "INFEASIBLE"


def test_hints_do_not_change_the_optimum():
    snapshot = snap([req(i, dept=d) for i, d in enumerate(["ENGG", "TRD", "SNT"], 1)])
    cold = run(snapshot)
    warm = run(snapshot, hints=baseline_plan(snapshot))
    assert objective(snapshot, cold.plan) == objective(snapshot, warm.plan)


def test_stop_flag_ends_the_search_early():
    snapshot = snap([req(i, dept="ENGG") for i in range(1, 6)], cost=quiet_night_traffic("A-B", 7))
    result = solve(snapshot, time_limit_s=30, workers=1, should_stop=lambda: True)
    assert result.status in ("OPTIMAL", "FEASIBLE")  # the first solution is kept


def test_solver_objective_equals_the_independent_objective_function():
    snapshot = snap(
        [req(1, minutes=180), req(2, dept="SNT", minutes=120), req(3, dept="TRD", section="B-C")],
        cost=quiet_night_traffic("A-B", 7),
    )
    result = run(snapshot)
    assert result.status == "OPTIMAL"
    assert objective(snapshot, result.plan) == result.objective


def test_solving_twice_gives_the_same_plan_with_one_worker():
    snapshot = snap([req(i, dept=d) for i, d in enumerate(["ENGG", "TRD", "SNT"], 1)])
    first, second = run(snapshot), run(snapshot)
    assert first.plan == second.plan


# ---------- property: never worse than a feasible baseline, always checker-clean ----------


def _random_instance(seed):
    rng = random.Random(seed)
    sections = ["A-B", "B-C"]
    depts = ["ENGG", "TRD", "SNT"]
    requests = []
    for i in range(1, rng.randint(4, 7)):
        earliest = rng.randint(0, 3)
        requests.append(
            req(
                i,
                dept=rng.choice(depts),
                section=rng.choice(sections),
                minutes=rng.choice([60, 90, 120, 180, 240]),
                earliest=earliest,
                deadline=earliest + rng.randint(0, 3),
                priority=rng.randint(1, 3),
            )
        )
    cost = {s: {d: [rng.randint(0, 4) for _ in range(48)] for d in range(5)} for s in sections}
    deps = []
    if rng.random() < 0.5 and len(requests) > 2:
        deps.append(dep(1, 2, gap=rng.choice([0, 30, 60])))
    return snap(requests, deps, days=5, cost=cost, trains=cost)


@pytest.mark.parametrize("seed", range(6))
def test_random_instances_are_valid_and_not_worse_than_a_feasible_baseline(seed):
    snapshot = _random_instance(seed)
    baseline = baseline_plan(snapshot)
    result = run(snapshot, hints=baseline, time_limit_s=5)
    assert check_plan(snapshot, result.plan) == []

    as_integrated = Plan(baseline.placements, baseline.deferred, span_blocks(baseline.placements.values()))
    if check_plan(snapshot, as_integrated) == []:
        assert objective(snapshot, result.plan) <= objective(snapshot, baseline)
    assert compute_metrics(snapshot, result.plan)["closures"] <= len(snapshot.requests)
