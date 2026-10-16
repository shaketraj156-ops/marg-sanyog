from app.planner.checker import check_plan
from app.planner.metrics import compute_metrics, objective
from app.planner.plan import Block, Placement, Plan, span_blocks
from tests.planner.factories import dep, req, snap


def _plan(placements, deferred=None, blocks=None):
    plan = Plan({p.request_id: p for p in placements}, dict(deferred or {}))
    plan.blocks = blocks if blocks is not None else span_blocks(placements)
    return plan


def P(i, day, offset, slots, section="A-B"):
    return Placement(i, section, day, offset, slots)


# ---------- metrics ----------


def test_metrics_are_computed_from_blocks_and_traffic():
    trains = {"A-B": {0: [1] * 48, 1: [2] * 48}}
    snapshot = snap([req(1), req(2)], trains=trains, cost={"A-B": {0: [3] * 48, 1: [3] * 48}})
    plan = _plan([P(1, 0, 0, 4), P(2, 1, 10, 6)])
    metrics = compute_metrics(snapshot, plan)
    assert metrics["closures"] == 2
    assert metrics["block_hours"] == 5.0  # (4 + 6) slots of 30 minutes
    assert metrics["trains_affected"] == 4 * 1 + 6 * 2
    assert metrics["traffic_cost"] == 10 * 3
    assert metrics["deferred"] == 0


def test_postponement_is_weighted_by_priority():
    snapshot = snap([req(1, earliest=1, priority=3), req(2, earliest=0, priority=1)])
    plan = _plan([P(1, 3, 0, 2), P(2, 0, 0, 2)])
    assert compute_metrics(snapshot, plan)["weighted_postponement_days"] == 3 * 2


def test_objective_matches_the_formula():
    snapshot = snap(
        [req(1, priority=2, earliest=0), req(2, priority=3)], cost={"A-B": {1: [2] * 48}}
    )
    plan = _plan([P(1, 1, 0, 4)], deferred={2: "NO_CAPACITY"})
    expected = 150 * 1 + 10 * (4 * 2) + 20 * (2 * 1) + 4 + 1000 * 3
    assert objective(snapshot, plan) == expected


# ---------- checker: a valid plan, then planted violations ----------


def test_valid_plan_has_no_violations():
    snapshot = snap([req(1), req(2, dept="TRD")])
    assert check_plan(snapshot, _plan([P(1, 0, 0, 4), P(2, 0, 2, 4)])) == []


def _violations(snapshot, plan):
    return " | ".join(check_plan(snapshot, plan))


def test_checker_catches_a_missing_request():
    assert "cover" in _violations(snap([req(1), req(2)]), _plan([P(1, 0, 0, 4)]))


def test_checker_catches_a_placement_outside_its_window():
    assert "outside" in _violations(snap([req(1, deadline=2)]), _plan([P(1, 5, 0, 4)]))


def test_checker_catches_work_running_past_midnight():
    assert "does not fit" in _violations(snap([req(1, minutes=120)]), _plan([P(1, 0, 46, 4)]))


def test_checker_catches_wrong_duration_and_section():
    snapshot = snap([req(1, minutes=120, section="A-B")])
    assert "duration" in _violations(snapshot, _plan([P(1, 0, 0, 2)]))
    assert "wrong section" in _violations(snapshot, _plan([P(1, 0, 0, 4, "B-C")]))


def test_checker_catches_placing_a_request_that_must_be_deferred():
    snapshot = snap([req(1, deadline=9)])
    assert "must be deferred" in _violations(snapshot, _plan([P(1, 0, 0, 4)]))


def test_checker_catches_unknown_and_wrong_deferral_reasons():
    snapshot = snap([req(1, deadline=9)])
    assert "unknown reason" in _violations(snapshot, _plan([], {1: "BECAUSE"}))
    assert "should be deferred as OUT_OF_HORIZON" in _violations(
        snapshot, _plan([], {1: "NO_CAPACITY"})
    )


def test_checker_catches_a_request_both_placed_and_deferred():
    assert "both" in _violations(snap([req(1)]), _plan([P(1, 0, 0, 4)], {1: "NO_CAPACITY"}))


def test_checker_catches_crew_overload():
    snapshot = snap([req(i, section=s) for i, s in [(1, "A-B"), (2, "B-C"), (3, "C-D")]])
    plan = _plan([P(1, 0, 0, 4), P(2, 0, 0, 4, "B-C"), P(3, 0, 2, 4, "C-D")])
    assert "3 crews at once" in _violations(snapshot, plan)


def test_checker_respects_a_custom_crew_limit():
    snapshot = snap([req(1, section="A-B"), req(2, section="B-C")], crews={"ENGG": 1})
    assert "crews at once" in _violations(snapshot, _plan([P(1, 0, 0, 4), P(2, 0, 2, 4, "B-C")]))


def test_checker_catches_overlap_of_one_department_on_one_section():
    snapshot = snap([req(1), req(2)])
    assert "overlapping work" in _violations(snapshot, _plan([P(1, 0, 0, 4), P(2, 0, 3, 4)]))


def test_checker_catches_a_block_that_is_too_long():
    snapshot = snap([req(1, minutes=360), req(2, dept="TRD", minutes=360)])
    assert "longer than the block maximum" in _violations(
        snapshot, _plan([P(1, 0, 0, 12), P(2, 0, 12, 12)])
    )


def test_checker_catches_two_closures_on_the_same_section_and_day():
    snapshot = snap([req(1), req(2, dept="TRD")])
    blocks = [Block("A-B", 0, 0, 4, (1,)), Block("A-B", 0, 10, 14, (2,))]
    plan = _plan([P(1, 0, 0, 4), P(2, 0, 10, 4)], blocks=blocks)
    assert "two closures" in _violations(snapshot, plan)


def test_checker_catches_a_request_outside_its_closure_and_wrong_member_lists():
    snapshot = snap([req(1)])
    outside = _plan([P(1, 0, 0, 4)], blocks=[Block("A-B", 0, 2, 8, (1,))])
    wrong_members = _plan([P(1, 0, 0, 4)], blocks=[Block("A-B", 0, 0, 4, (1, 99))])
    missing_block = _plan([P(1, 0, 0, 4)], blocks=[])
    assert "outside its closure" in _violations(snapshot, outside)
    assert "wrong requests" in _violations(snapshot, wrong_members)
    assert "no closure" in _violations(snapshot, missing_block)


def test_checker_catches_dependency_order_and_gap():
    snapshot = snap([req(1), req(2, dept="TRD")], deps=[dep(1, 2, gap=60)])
    too_early = _plan([P(1, 0, 0, 4), P(2, 0, 3, 4)])
    gap_too_small = _plan([P(1, 0, 0, 4), P(2, 0, 5, 4)])  # needs 4 + 2 slots of gap
    fine = _plan([P(1, 0, 0, 4), P(2, 0, 6, 4)])
    assert "before request 1 has finished" in _violations(snapshot, too_early)
    assert "before request 1 has finished" in _violations(snapshot, gap_too_small)
    assert check_plan(snapshot, fine) == []


def test_checker_catches_orphan_follow_up_work():
    snapshot = snap([req(1), req(2, dept="TRD")], deps=[dep(1, 2)])
    plan = _plan([P(2, 0, 0, 4)], {1: "NO_CAPACITY"})
    assert "it depends on is not" in _violations(snapshot, plan)


def test_checker_catches_same_day_for_not_same_block():
    snapshot = snap([req(1), req(2, dept="TRD")], deps=[dep(1, 2, "not_same_block")])
    assert "must not share a day" in _violations(snapshot, _plan([P(1, 0, 0, 4), P(2, 0, 2, 4)]))
    assert check_plan(snapshot, _plan([P(1, 0, 0, 4), P(2, 1, 2, 4)])) == []


def test_same_block_allowed_adds_no_constraint():
    snapshot = snap([req(1), req(2, dept="TRD")], deps=[dep(1, 2, "same_block_allowed")])
    assert check_plan(snapshot, _plan([P(1, 0, 0, 4), P(2, 0, 2, 4)])) == []
