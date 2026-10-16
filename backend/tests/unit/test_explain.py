from datetime import date

from app.planner.baseline import baseline_plan
from app.planner.model import solve
from app.planner.plan import Placement, Plan, span_blocks
from app.services.explain import explain, fmt_day, names, plural
from tests.planner.factories import dep, quiet_night_traffic, req, snap

START = date(2026, 10, 19)  # a Monday


def P(i, day, offset, slots, section="A-B"):
    return Placement(i, section, day, offset, slots)


def make_plan(placements, deferred=None):
    plan = Plan({p.request_id: p for p in placements}, dict(deferred or {}))
    plan.blocks = span_blocks(placements)
    return plan


def by_code(drafts, code):
    return [d for d in drafts if d.code == code]


# ---------- helpers ----------


def test_names_and_plurals():
    assert names([1]) == "R1"
    assert names([2, 1]) == "R1 and R2"
    assert names([3, 1, 2]) == "R1, R2 and R3"
    assert plural(1, "day") == "1 day" and plural(2, "day") == "2 days" and plural(0, "day") == "0 days"


def test_fmt_day():
    assert fmt_day(START, 0) == "Mon 19 Oct"
    assert fmt_day(START, 3) == "Thu 22 Oct"


# ---------- MERGED ----------


def three_departments():
    return snap([req(1, dept="ENGG"), req(2, dept="TRD"), req(3, dept="SNT")])


def test_merged_numbers_are_counterfactual_and_computed():
    snapshot = three_departments()
    baseline = baseline_plan(snapshot)  # 3 separate closures of 2 hours each
    plan = make_plan([P(1, 0, 0, 4), P(2, 0, 0, 4), P(3, 0, 0, 4)])
    (merged,) = by_code(explain(snapshot, plan, baseline, START), "MERGED")
    assert merged.numbers["requests"] == [1, 2, 3]
    assert merged.numbers["closures_independent"] == 3
    assert merged.numbers["closures_avoided"] == 2
    assert merged.numbers["block_hours_independent"] == 6.0
    assert merged.numbers["block_hours_shared"] == 2.0
    assert merged.numbers["block_hours_saved"] == 4.0
    assert merged.block == ("A-B", 0)
    assert merged.text == (
        "R1, R2 and R3 share one block on A-B: 2 closures avoided, 4 block-hours saved "
        "versus independent planning."
    )


def test_merged_savings_reconcile_with_the_plan_metrics():
    from app.planner.metrics import compute_metrics

    snapshot = three_departments()
    baseline = baseline_plan(snapshot)
    plan = make_plan([P(1, 0, 0, 4), P(2, 0, 0, 4), P(3, 0, 0, 4)])
    (merged,) = by_code(explain(snapshot, plan, baseline, START), "MERGED")
    before, after = compute_metrics(snapshot, baseline), compute_metrics(snapshot, plan)
    assert merged.numbers["closures_avoided"] == before["closures"] - after["closures"]
    assert merged.numbers["block_hours_saved"] == round(before["block_hours"] - after["block_hours"], 2)


def test_no_merged_explanation_for_a_block_of_one():
    snapshot = snap([req(1)])
    plan = make_plan([P(1, 0, 0, 4)])
    assert by_code(explain(snapshot, plan, baseline_plan(snapshot), START), "MERGED") == []


# ---------- LOW_TRAFFIC ----------


def test_low_traffic_only_with_traffic_data_and_a_quiet_window():
    traffic = quiet_night_traffic("A-B", 7)
    snapshot = snap([req(1, deadline=2)], cost=traffic, trains=traffic)
    quiet = make_plan([P(1, 0, 0, 4)])
    busy = make_plan([P(1, 0, 30, 4)])
    baseline = baseline_plan(snapshot)
    (low,) = by_code(explain(snapshot, quiet, baseline, START), "LOW_TRAFFIC")
    assert low.numbers["window_cost"] == 0
    assert low.numbers["feasible_windows"] == 3 * 45  # three days, 45 start slots for 4 slots
    assert low.numbers["quietest_percent"] <= 25
    assert "quietest" in low.text and "A-B" in low.text
    assert by_code(explain(snapshot, busy, baseline, START), "LOW_TRAFFIC") == []


def test_no_low_traffic_without_traffic_data():
    snapshot = snap([req(1)])
    assert by_code(explain(snapshot, make_plan([P(1, 0, 0, 4)]), baseline_plan(snapshot), START), "LOW_TRAFFIC") == []


def test_low_traffic_numbers_come_from_the_arrays():
    traffic = {"A-B": {0: [0] * 10 + [5] * 38}}
    snapshot = snap([req(1, deadline=0)], days=1, cost=traffic, trains=traffic)
    plan = make_plan([P(1, 0, 2, 4)])
    (low,) = by_code(explain(snapshot, plan, baseline_plan(snapshot), START), "LOW_TRAFFIC")
    assert low.numbers["trains_in_window"] == 0
    assert low.numbers["median_cost"] == 20


# ---------- DEADLINE_DRIVEN ----------


def test_postponed_request_is_explained_with_numbers():
    snapshot = snap([req(1, earliest=0, deadline=3)])
    plan = make_plan([P(1, 2, 0, 4)])
    (late,) = by_code(explain(snapshot, plan, baseline_plan(snapshot), START), "DEADLINE_DRIVEN")
    assert late.request_id == 1
    assert late.numbers["days_postponed"] == 2
    assert late.numbers["slack_days"] == 1
    assert late.numbers["placed_day"] == "Wed 21 Oct"
    assert late.numbers["deadline_day"] == "Thu 22 Oct"
    assert "2 days after its earliest date" in late.text and "1 day of slack" in late.text


def test_postponement_to_share_a_block_is_named_as_the_cause():
    snapshot = snap([req(1, earliest=0, deadline=3), req(2, dept="TRD", earliest=2, deadline=3)])
    plan = make_plan([P(1, 2, 0, 4), P(2, 2, 0, 4)])
    (late,) = by_code(explain(snapshot, plan, baseline_plan(snapshot), START), "DEADLINE_DRIVEN")
    assert late.numbers["shares_block_with"] == 1
    assert "to share a block with 1 other request" in late.text


def test_postponement_to_avoid_traffic_is_named_with_the_numbers():
    day0, day2 = [4] * 48, [0] * 48
    snapshot = snap(
        [req(1, earliest=0, deadline=3)],
        cost={"A-B": {0: day0, 2: day2}},
        trains={"A-B": {0: day0, 2: day2}},
    )
    plan = make_plan([P(1, 2, 0, 4)])
    (late,) = by_code(explain(snapshot, plan, baseline_plan(snapshot), START), "DEADLINE_DRIVEN")
    assert late.numbers["trains_in_window"] == 0
    assert late.numbers["trains_same_hours_on_earliest_day"] == 16
    assert "avoids 16 trains" in late.text


def test_requests_on_their_earliest_day_get_no_deadline_explanation():
    snapshot = snap([req(1, earliest=1, deadline=3)])
    plan = make_plan([P(1, 1, 0, 4)])
    assert by_code(explain(snapshot, plan, baseline_plan(snapshot), START), "DEADLINE_DRIVEN") == []


# ---------- DEPENDENCY_ORDER ----------


def test_dependency_order_numbers():
    snapshot = snap([req(1), req(2, dept="TRD")], deps=[dep(1, 2, gap=30)])
    plan = make_plan([P(1, 0, 0, 4), P(2, 0, 6, 4)])
    (order,) = by_code(explain(snapshot, plan, baseline_plan(snapshot), START), "DEPENDENCY_ORDER")
    assert order.request_id == 2
    assert order.numbers == {
        "before": 1,
        "after": 2,
        "required_gap_minutes": 30,
        "actual_gap_minutes": 60,
    }
    assert "R2 starts at 03:00" in order.text and "after R1 finishes at 02:00" in order.text


def test_other_dependency_kinds_are_not_ordering_explanations():
    snapshot = snap(
        [req(1), req(2, dept="TRD")], deps=[dep(1, 2, "not_same_block")]
    )
    plan = make_plan([P(1, 0, 0, 4), P(2, 1, 0, 4)])
    assert by_code(explain(snapshot, plan, baseline_plan(snapshot), START), "DEPENDENCY_ORDER") == []


# ---------- DEFERRED ----------


def test_each_deferral_reason_is_explained_with_its_numbers():
    snapshot = snap(
        [
            req(1, deadline=30),
            req(2, minutes=480),
            req(3),
            req(4, dept="TRD"),
            req(5, dept="SNT"),
        ],
        deps=[dep(3, 4)],
    )
    plan = make_plan(
        [P(5, 0, 0, 4)],
        {1: "OUT_OF_HORIZON", 2: "TOO_LONG", 3: "NO_CAPACITY", 4: "DEPENDENCY_UNMET"},
    )
    drafts = {d.request_id: d for d in by_code(explain(snapshot, plan, baseline_plan(snapshot), START), "DEFERRED")}
    assert set(drafts) == {1, 2, 3, 4}
    assert drafts[1].numbers["reason"] == "OUT_OF_HORIZON" and "outside the planning horizon" in drafts[1].text
    assert drafts[2].numbers == {"reason": "TOO_LONG", "duration_minutes": 480, "limit_minutes": 360}
    assert "480 minutes" in drafts[2].text
    assert drafts[3].numbers["reason"] == "NO_CAPACITY"
    assert drafts[4].numbers["waiting_for"] == [3] and "must follow R3" in drafts[4].text


# ---------- OVERRIDE ----------


def test_override_explains_the_change_against_the_parent():
    traffic = {"A-B": {0: [2] * 48}}
    snapshot = snap([req(1, deadline=0), req(2, dept="TRD", deadline=0)], days=1, cost=traffic, trains=traffic)
    parent = make_plan([P(1, 0, 0, 4), P(2, 0, 0, 4)])
    moved = make_plan([P(1, 0, 0, 4), P(2, 0, 20, 4)])
    drafts = explain(snapshot, moved, baseline_plan(snapshot), START, parent=parent, overridden=frozenset({2}))
    (override,) = by_code(drafts, "OVERRIDE")
    assert override.request_id == 2
    # one closure now spans slots 0-24 instead of 0-4: (24 - 4) slots at 2 trains each
    assert override.numbers["trains_affected_change"] == 40
    assert override.numbers["moved_from"] == "Mon 19 Oct 00:00-02:00"
    assert override.numbers["moved_to"] == "Mon 19 Oct 10:00-12:00"
    assert "40 more trains affected" in override.text and "moved by a planner" in override.text


def test_nothing_is_explained_for_an_empty_plan():
    snapshot = snap([])
    assert explain(snapshot, make_plan([]), baseline_plan(snapshot), START) == []


def test_explanations_for_a_solved_plan_are_all_well_formed():
    traffic = quiet_night_traffic("A-B", 7)
    snapshot = snap(
        [req(1), req(2, dept="TRD"), req(3, dept="SNT", deadline=30), req(4, minutes=480)],
        deps=[dep(1, 2)],
        cost=traffic,
        trains=traffic,
    )
    result = solve(snapshot, time_limit_s=10, workers=1)
    drafts = explain(snapshot, result.plan, baseline_plan(snapshot), START)
    assert {d.code for d in drafts} <= {"MERGED", "LOW_TRAFFIC", "DEADLINE_DRIVEN", "DEPENDENCY_ORDER", "DEFERRED"}
    assert all(d.text and isinstance(d.numbers, dict) for d in drafts)
    assert {d.request_id for d in by_code(drafts, "DEFERRED")} == {3, 4}
