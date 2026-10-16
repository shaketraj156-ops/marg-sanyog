"""A quick, always-valid starting plan for the solver.

The independent-planning baseline ignores crews, block limits and dependencies (that is what
independent planning means), so it is not a valid plan and the solver cannot start from it. On big
instances the solver then spends many seconds finding its first answer. This module builds a
valid plan greedily in a few milliseconds: it tries each request at its baseline time first, and
otherwise at the nearest time that breaks no rule. The solver starts from it and improves it, so
even a short time limit gives a usable plan.

The result is verified by the independent checker. If that ever fails (a bug), the fallback is the
plan that defers everything, which is always valid.
"""
from collections import defaultdict

from app.planner.baseline import default_offset
from app.planner.checker import check_plan
from app.planner.plan import Placement, Plan, span_blocks
from app.planner.snapshot import DEPENDENCY_UNMET, NO_CAPACITY, PlanRequest, Snapshot


def all_deferred(snapshot: Snapshot) -> Plan:
    """The trivially valid plan: nothing is placed."""
    forced = snapshot.forced_deferrals()
    plan = Plan()
    for request in snapshot.requests:
        plan.deferred[request.id] = forced.get(request.id, NO_CAPACITY)
    return plan


def _depths(snapshot: Snapshot) -> dict[int, int]:
    """How many requests must come before each one (so predecessors are placed first)."""
    before = defaultdict(list)
    for dep in snapshot.dependencies:
        before[dep.after].append(dep.before)
    depth: dict[int, int] = {}

    def visit(request_id: int, seen: frozenset[int]) -> int:
        if request_id in depth:
            return depth[request_id]
        if request_id in seen:  # cannot happen (cycles are refused), but never loop forever
            return 0
        depth[request_id] = 1 + max(
            (visit(b, seen | {request_id}) for b in before[request_id]), default=-1
        )
        return depth[request_id]

    for request in snapshot.requests:
        visit(request.id, frozenset())
    return depth


def greedy_plan(snapshot: Snapshot) -> Plan:
    per_day = snapshot.per_day
    forced = snapshot.forced_deferrals()
    depth = _depths(snapshot)

    needs_first = defaultdict(list)  # request -> [(predecessor, gap in slots)]
    apart = defaultdict(set)  # request -> requests it may not share a day with
    for dep in snapshot.dependencies:
        if dep.relation == "finish_before_start":
            needs_first[dep.after].append((dep.before, snapshot.gap_slots(dep)))
        elif dep.relation == "not_same_block":
            apart[dep.after].add(dep.before)
            apart[dep.before].add(dep.after)

    order = sorted(
        snapshot.requests,
        key=lambda r: (depth[r.id], -r.priority, snapshot.window(r)[0], r.id),
    )

    plan = Plan()
    crew_use: dict[tuple[str, int], int] = defaultdict(int)  # (department, slot) -> crews busy
    intervals: dict[tuple[str, str], list[tuple[int, int]]] = defaultdict(list)
    spans: dict[tuple[str, int], tuple[int, int]] = {}  # (section, day) -> (first slot, last slot)

    def fits(request: PlanRequest, slots: int, day: int, offset: int) -> bool:
        start = day * per_day + offset
        end = start + slots
        for before, gap in needs_first[request.id]:
            earlier = plan.placements[before]
            if earlier.day * per_day + earlier.end + gap > start:
                return False
        for other in apart[request.id]:
            placed = plan.placements.get(other)
            if placed is not None and placed.day == day:
                return False
        if any(s < end and start < e for s, e in intervals[request.dept, request.section]):
            return False
        limit = snapshot.crew_limit(request.dept)
        if any(crew_use[request.dept, slot] >= limit for slot in range(start, end)):
            return False
        first, last = spans.get((request.section, day), (offset, offset + slots))
        return max(last, offset + slots) - min(first, offset) <= snapshot.max_block_slots

    for request in order:
        if request.id in forced:
            plan.deferred[request.id] = forced[request.id]
            continue
        if any(before not in plan.placements for before, _ in needs_first[request.id]):
            plan.deferred[request.id] = DEPENDENCY_UNMET
            continue

        slots = snapshot.dur(request)
        lo, hi = snapshot.window(request)
        # Prefer a day where this section is already closed (merging), then the earliest day.
        days = sorted(range(lo, hi + 1), key=lambda d: ((request.section, d) not in spans, d))
        wanted = request.pref_offset
        if wanted is None:
            wanted = default_offset(request.dept, per_day)
        wanted = max(0, min(wanted, per_day - slots))
        offsets = sorted(range(per_day - slots + 1), key=lambda o: (abs(o - wanted), o))

        chosen = next(
            ((day, offset) for day in days for offset in offsets if fits(request, slots, day, offset)),
            None,
        )
        if chosen is None:
            plan.deferred[request.id] = NO_CAPACITY
            continue
        day, offset = chosen
        plan.placements[request.id] = Placement(request.id, request.section, day, offset, slots)
        start = day * per_day + offset
        for slot in range(start, start + slots):
            crew_use[request.dept, slot] += 1
        intervals[request.dept, request.section].append((start, start + slots))
        first, last = spans.get((request.section, day), (offset, offset + slots))
        spans[request.section, day] = (min(first, offset), max(last, offset + slots))

    plan.blocks = span_blocks(plan.placements.values())
    if check_plan(snapshot, plan):  # a bug, never expected: fall back to the plan that is always valid
        return all_deferred(snapshot)
    return plan
