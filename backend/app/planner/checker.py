"""Independent verifier. It never calls the solver, so a model bug cannot hide itself."""
from collections import Counter, defaultdict
from itertools import pairwise

from app.planner.plan import Plan
from app.planner.snapshot import (
    DEPENDENCY_UNMET,
    NO_CAPACITY,
    OUT_OF_HORIZON,
    TOO_LONG,
    Snapshot,
)

REASON_CODES = {OUT_OF_HORIZON, TOO_LONG, DEPENDENCY_UNMET, NO_CAPACITY}


def check_plan(snapshot: Snapshot, plan: Plan) -> list[str]:
    """Returns a list of violations; an empty list means the plan is valid."""
    problems: list[str] = []
    requests = {r.id: r for r in snapshot.requests}
    forced = snapshot.forced_deferrals()
    per_day = snapshot.per_day

    # Every request is either placed or deferred, exactly once.
    placed_ids, deferred_ids = set(plan.placements), set(plan.deferred)
    if placed_ids & deferred_ids:
        problems.append(f"requests both placed and deferred: {sorted(placed_ids & deferred_ids)}")
    if (placed_ids | deferred_ids) != set(requests):
        problems.append("plan does not cover exactly the requests of the run")
    for request_id, reason in plan.deferred.items():
        if reason not in REASON_CODES:
            problems.append(f"request {request_id} deferred with unknown reason {reason!r}")
        if request_id in forced and reason != forced[request_id]:
            problems.append(f"request {request_id} should be deferred as {forced[request_id]}")

    # Each placement: allowed, inside its day, on its own section.
    for request_id, placement in plan.placements.items():
        request = requests.get(request_id)
        if request is None:
            continue
        lo, hi = snapshot.window(request)
        if request_id in forced:
            problems.append(f"request {request_id} must be deferred ({forced[request_id]})")
        if not lo <= placement.day <= hi:
            problems.append(f"request {request_id} placed on day {placement.day}, outside {lo}..{hi}")
        if placement.slots != snapshot.dur(request):
            problems.append(f"request {request_id} has the wrong duration")
        if placement.section != request.section:
            problems.append(f"request {request_id} placed on the wrong section")
        if placement.offset < 0 or placement.end > per_day:
            problems.append(f"request {request_id} does not fit inside day {placement.day}")

    problems += _check_blocks(snapshot, plan)
    problems += _check_crews(snapshot, plan, requests)
    problems += _check_dependencies(snapshot, plan, requests)
    return problems


def _check_blocks(snapshot: Snapshot, plan: Plan) -> list[str]:
    problems = []
    by_key = {}
    for block in plan.blocks:
        key = (block.section, block.day)
        if key in by_key:
            problems.append(f"two closures on section {block.section}, day {block.day}")
        by_key[key] = block
        if not 0 <= block.start < block.end <= snapshot.per_day:
            problems.append(f"closure {key} has an invalid window")
        if block.end - block.start > snapshot.max_block_slots:
            problems.append(f"closure {key} is longer than the block maximum")
    members: dict[tuple[str, int], set[int]] = defaultdict(set)
    for request_id, placement in plan.placements.items():
        key = (placement.section, placement.day)
        members[key].add(request_id)
        block = by_key.get(key)
        if block is None:
            problems.append(f"request {request_id} has no closure on {key}")
        elif not (block.start <= placement.offset and placement.end <= block.end):
            problems.append(f"request {request_id} lies outside its closure")
    for key, block in by_key.items():
        if set(block.request_ids) != members.get(key, set()):
            problems.append(f"closure {key} lists the wrong requests")
    return problems


def _check_crews(snapshot: Snapshot, plan: Plan, requests) -> list[str]:
    problems = []
    busy: dict[str, Counter] = defaultdict(Counter)
    same_place: dict[tuple[str, str, int], list] = defaultdict(list)
    for request_id, placement in plan.placements.items():
        request = requests.get(request_id)
        if request is None:
            continue
        start = placement.day * snapshot.per_day + placement.offset
        for slot in range(start, start + placement.slots):
            busy[request.dept][slot] += 1
        same_place[(request.dept, placement.section, placement.day)].append(placement)
    for dept, counter in busy.items():
        limit = snapshot.crew_limit(dept)
        worst = max(counter.values(), default=0)
        if worst > limit:
            problems.append(f"department {dept} needs {worst} crews at once, only {limit} available")
    for (dept, section, day), group in same_place.items():
        group.sort(key=lambda p: p.offset)
        for earlier, later in pairwise(group):
            if later.offset < earlier.end:
                problems.append(
                    f"department {dept} has overlapping work on {section}, day {day} "
                    f"(requests {earlier.request_id} and {later.request_id})"
                )
    return problems


def _check_dependencies(snapshot: Snapshot, plan: Plan, requests) -> list[str]:
    problems = []
    for dep in snapshot.dependencies:
        before, after = plan.placements.get(dep.before), plan.placements.get(dep.after)
        if dep.relation == "finish_before_start":
            if after and not before:
                problems.append(
                    f"request {dep.after} is placed but request {dep.before} it depends on is not"
                )
            elif before and after:
                end_of_before = before.day * snapshot.per_day + before.end
                start_of_after = after.day * snapshot.per_day + after.offset
                if end_of_before + snapshot.gap_slots(dep) > start_of_after:
                    problems.append(
                        f"request {dep.after} starts before request {dep.before} has finished "
                        f"(plus gap)"
                    )
        elif dep.relation == "not_same_block" and before and after and before.day == after.day:
            problems.append(f"requests {dep.before} and {dep.after} must not share a day")
    return problems
