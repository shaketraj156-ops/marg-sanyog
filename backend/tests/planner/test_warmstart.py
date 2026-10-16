import random

import pytest

from app.planner.checker import check_plan
from app.planner.model import solve
from app.planner.snapshot import DEPENDENCY_UNMET, NO_CAPACITY, OUT_OF_HORIZON, TOO_LONG
from app.planner.warmstart import all_deferred, greedy_plan
from tests.planner.factories import dep, req, snap
from tests.planner.test_model import _random_instance


def valid(snapshot, plan):
    assert check_plan(snapshot, plan) == [], check_plan(snapshot, plan)


def test_an_empty_instance_gives_an_empty_valid_plan():
    snapshot = snap([])
    plan = greedy_plan(snapshot)
    valid(snapshot, plan)
    assert plan.placements == {} and plan.deferred == {}


def test_a_request_goes_where_its_department_usually_works():
    snapshot = snap([req(1, dept="ENGG"), req(2, dept="TRD", section="B-C")])
    plan = greedy_plan(snapshot)
    valid(snapshot, plan)
    assert plan.placements[1].offset == 20  # ENGG's usual 10:00
    assert plan.placements[2].offset == 8  # TRD's usual 04:00


def test_the_preferred_start_is_honoured_when_it_is_free():
    snapshot = snap([req(1, pref_day=2, pref_offset=30, deadline=3)])
    plan = greedy_plan(snapshot)
    assert (plan.placements[1].day, plan.placements[1].offset) == (0, 30)  # first allowed day, wanted slot


def test_requests_on_one_section_share_a_day_when_they_can():
    snapshot = snap([req(i, dept=d, deadline=4) for i, d in enumerate(["ENGG", "TRD", "SNT"], 1)])
    plan = greedy_plan(snapshot)
    valid(snapshot, plan)
    assert len({p.day for p in plan.placements.values()}) == 1  # merged onto one day


def test_the_block_maximum_is_respected():
    # four 6-hour jobs by one department on one section and day cannot all fit in one closure
    snapshot = snap([req(i, minutes=360, deadline=0) for i in range(1, 5)], crews={"ENGG": 4})
    plan = greedy_plan(snapshot)
    valid(snapshot, plan)
    assert len(plan.placements) == 1 and len(plan.deferred) == 3
    assert set(plan.deferred.values()) == {NO_CAPACITY}


def test_crew_limits_are_respected():
    snapshot = snap(
        [req(1, section="A-B", minutes=180, deadline=0), req(2, section="B-C", minutes=180, deadline=0)],
        crews={"ENGG": 1},
        days=1,
    )
    plan = greedy_plan(snapshot)
    valid(snapshot, plan)
    one, two = plan.placements[1], plan.placements[2]
    assert one.end <= two.offset or two.end <= one.offset


def test_dependencies_are_ordered_with_their_gap():
    snapshot = snap([req(1, deadline=1), req(2, dept="TRD", deadline=1)], deps=[dep(1, 2, gap=60)], days=2)
    plan = greedy_plan(snapshot)
    valid(snapshot, plan)
    first, second = plan.placements[1], plan.placements[2]
    assert first.day * 48 + first.end + 2 <= second.day * 48 + second.offset


def test_dependencies_are_handled_whatever_the_id_order():
    # request 1 depends on request 2: the later id must be placed first
    snapshot = snap([req(1, deadline=1), req(2, dept="TRD", deadline=1)], deps=[dep(2, 1)], days=2)
    plan = greedy_plan(snapshot)
    valid(snapshot, plan)
    assert len(plan.placements) == 2


def test_not_same_block_puts_requests_on_different_days():
    snapshot = snap(
        [req(1, deadline=2), req(2, dept="SNT", deadline=2)], deps=[dep(1, 2, "not_same_block")], days=3
    )
    plan = greedy_plan(snapshot)
    valid(snapshot, plan)
    assert plan.placements[1].day != plan.placements[2].day


def test_deferrals_carry_the_right_reasons_and_follow_ups_wait():
    snapshot = snap(
        [req(1, deadline=30), req(2, minutes=480), req(3), req(4, dept="TRD")],
        deps=[dep(1, 3)],
    )
    plan = greedy_plan(snapshot)
    valid(snapshot, plan)
    assert plan.deferred == {1: OUT_OF_HORIZON, 2: TOO_LONG, 3: DEPENDENCY_UNMET}
    assert set(plan.placements) == {4}


def test_all_deferred_is_valid_whatever_the_instance():
    snapshot = _random_instance(3)
    plan = all_deferred(snapshot)
    valid(snapshot, plan)
    assert plan.placements == {} and set(plan.deferred) == {r.id for r in snapshot.requests}


@pytest.mark.parametrize("seed", range(10))
def test_random_instances_always_give_a_valid_plan(seed):
    snapshot = _random_instance(seed)
    plan = greedy_plan(snapshot)
    valid(snapshot, plan)
    assert set(plan.placements) | set(plan.deferred) == {r.id for r in snapshot.requests}


def test_the_checker_failure_fallback_is_the_deferral_plan(monkeypatch):
    from app.planner import warmstart

    monkeypatch.setattr(warmstart, "check_plan", lambda s, p: ["planted"])
    snapshot = snap([req(1), req(2, dept="TRD")])
    plan = warmstart.greedy_plan(snapshot)
    assert plan.placements == {} and set(plan.deferred) == {1, 2}


def test_it_is_fast_even_for_a_large_instance():
    import time

    rng = random.Random(5)
    requests = [
        req(
            i,
            dept=rng.choice(["ENGG", "TRD", "SNT"]),
            section=f"S{i % 50:02d}",
            minutes=rng.choice([60, 120, 180]),
            earliest=rng.randint(0, 3),
            deadline=rng.randint(3, 6),
            priority=rng.randint(1, 3),
        )
        for i in range(1, 201)
    ]
    snapshot = snap(requests)
    started = time.perf_counter()
    plan = greedy_plan(snapshot)
    assert time.perf_counter() - started < 5
    valid(snapshot, plan)
    assert len(plan.placements) > 150  # most requests are placed straight away


def test_the_solver_accepts_it_as_a_complete_hint_and_improves_on_it():
    snapshot = _random_instance(2)
    start = greedy_plan(snapshot)
    result = solve(snapshot, hints=start, time_limit_s=10, workers=1)
    assert result.status in ("OPTIMAL", "FEASIBLE")
    valid(snapshot, result.plan)
    from app.planner.metrics import objective

    assert objective(snapshot, result.plan) <= objective(snapshot, start)
