import json

import pytest

from app.planner.baseline import baseline_plan, default_offset
from app.planner.plan import Block, Placement, Plan, merged_blocks, span_blocks
from app.planner.slots import duration_slots, hhmm, prefix_sums, slots_per_day
from app.planner.snapshot import (
    DEPENDENCY_UNMET,
    OUT_OF_HORIZON,
    TOO_LONG,
    Snapshot,
)
from tests.planner.factories import dep, quiet_night_traffic, req, snap

# ---------- slots ----------


def test_slots_per_day():
    assert slots_per_day(30) == 48
    assert slots_per_day(60) == 24
    assert slots_per_day(15) == 96


@pytest.mark.parametrize(("minutes", "expected"), [(15, 1), (30, 1), (31, 2), (180, 6), (181, 7)])
def test_durations_round_up(minutes, expected):
    assert duration_slots(minutes, 30) == expected


def test_prefix_sums_give_window_totals():
    cum = prefix_sums([1, 2, 3, 4])
    assert cum == [0, 1, 3, 6, 10]
    assert cum[4] - cum[1] == 9


def test_hhmm():
    assert hhmm(0, 30) == "00:00"
    assert hhmm(7, 30) == "03:30"
    assert hhmm(48, 30) == "24:00"


# ---------- snapshot ----------


def test_window_is_clamped_into_the_horizon():
    snapshot = snap([req(1, earliest=-3, deadline=2)], days=7)
    assert snapshot.window(snapshot.requests[0]) == (0, 2)


def test_forced_deferrals_out_of_horizon_and_too_long():
    snapshot = snap(
        [
            req(1, deadline=2),
            req(2, deadline=7),  # deadline after the last day (index 6)
            req(3, earliest=-5, deadline=-1),  # deadline before the horizon
            req(4, minutes=390),  # longer than the 360 minute block maximum
        ],
        days=7,
    )
    assert snapshot.forced_deferrals() == {2: OUT_OF_HORIZON, 3: OUT_OF_HORIZON, 4: TOO_LONG}


def test_follow_up_work_of_a_deferred_request_is_deferred_too():
    snapshot = snap(
        [req(1, deadline=9), req(2), req(3), req(4)],
        deps=[dep(1, 2), dep(2, 3), dep(1, 4, "not_same_block")],
    )
    forced = snapshot.forced_deferrals()
    assert forced == {1: OUT_OF_HORIZON, 2: DEPENDENCY_UNMET, 3: DEPENDENCY_UNMET}


def test_snapshot_round_trips_through_json():
    snapshot = snap(
        [req(1), req(2, section="B-C")],
        deps=[dep(1, 2, gap=30)],
        crews={"ENGG": 1},
        cost=quiet_night_traffic("A-B", 7),
    )
    again = Snapshot.from_dict(json.loads(json.dumps(snapshot.to_dict())))
    assert again == snapshot
    assert again.input_hash() == snapshot.input_hash()


def test_input_hash_changes_with_the_input():
    assert snap([req(1)]).input_hash() != snap([req(1, minutes=180)]).input_hash()
    assert snap([req(1)]).input_hash() == snap([req(1)]).input_hash()


def test_missing_traffic_means_zero():
    snapshot = snap([req(1)])
    assert snapshot.cost_at("A-B", 0) == [0] * 48
    assert snapshot.trains_at("Z-Z", 3) == [0] * 48


# ---------- blocks ----------


def _p(i, day, offset, slots, section="A-B"):
    return Placement(i, section, day, offset, slots)


def test_span_blocks_make_one_closure_per_section_and_day():
    blocks = span_blocks([_p(1, 0, 0, 6), _p(2, 0, 20, 4), _p(3, 1, 0, 2), _p(4, 0, 0, 2, "B-C")])
    assert [(b.section, b.day, b.start, b.end) for b in blocks] == [
        ("A-B", 0, 0, 24),
        ("A-B", 1, 0, 2),
        ("B-C", 0, 0, 2),
    ]
    assert blocks[0].request_ids == (1, 2)


def test_merged_blocks_only_join_work_that_overlaps():
    blocks = merged_blocks([_p(1, 0, 0, 6), _p(2, 0, 4, 4), _p(3, 0, 8, 2), _p(4, 0, 20, 4)])
    # 1 and 2 overlap; 3 only touches 2 (a separate block application); 4 is far away
    assert [(b.start, b.end, b.request_ids) for b in blocks] == [
        (0, 8, (1, 2)),
        (8, 10, (3,)),
        (20, 24, (4,)),
    ]


def test_plan_round_trips_through_json():
    plan = Plan({1: _p(1, 0, 2, 4)}, {2: TOO_LONG}, [Block("A-B", 0, 2, 6, (1,))])
    assert Plan.from_dict(json.loads(json.dumps(plan.to_dict()))) == plan


# ---------- baseline ----------


def test_baseline_uses_department_defaults_on_the_first_day():
    snapshot = snap([req(1, dept="ENGG"), req(2, dept="TRD", earliest=2)])
    plan = baseline_plan(snapshot)
    assert (plan.placements[1].day, plan.placements[1].offset) == (0, default_offset("ENGG", 48))
    assert (plan.placements[2].day, plan.placements[2].offset) == (2, default_offset("TRD", 48))


def test_baseline_honours_the_preferred_start():
    snapshot = snap([req(1, pref_day=1, pref_offset=6)])
    placement = baseline_plan(snapshot).placements[1]
    assert (placement.day, placement.offset) == (1, 6)


def test_baseline_clamps_preference_into_the_window_and_the_day():
    snapshot = snap([req(1, deadline=2, pref_day=6, pref_offset=47, minutes=180)])
    placement = baseline_plan(snapshot).placements[1]
    assert placement.day == 2
    assert placement.end <= 48


def test_baseline_does_not_coordinate_requests():
    snapshot = snap([req(i, dept=d) for i, d in enumerate(["ENGG", "TRD", "SNT"], start=1)])
    plan = baseline_plan(snapshot)
    assert len(plan.blocks) == 3  # three departments, three separate closures


def test_baseline_keeps_forced_deferrals():
    snapshot = snap([req(1, deadline=9), req(2)])
    plan = baseline_plan(snapshot)
    assert plan.deferred == {1: OUT_OF_HORIZON}
    assert set(plan.placements) == {2}
