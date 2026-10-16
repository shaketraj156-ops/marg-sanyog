"""Independent planning: every department picks its own time, nobody coordinates."""
from app.planner.plan import Placement, Plan, merged_blocks
from app.planner.snapshot import Snapshot

# Default start hour per department when a request has no preferred start.
DEFAULT_START_HOUR = {"ENGG": 10, "TRD": 4, "SNT": 7}
FALLBACK_START_HOUR = 10


def default_offset(dept: str, per_day: int) -> int:
    return DEFAULT_START_HOUR.get(dept, FALLBACK_START_HOUR) * per_day // 24


def baseline_plan(snapshot: Snapshot) -> Plan:
    """Each request goes at its preferred start, or at its department's default time on the
    first allowed day. Crews, block limits and dependencies are ignored: that is what
    independent planning means. Requests the planner would defer anyway stay deferred."""
    forced = snapshot.forced_deferrals()
    plan = Plan()
    for request in snapshot.requests:
        if request.id in forced:
            plan.deferred[request.id] = forced[request.id]
            continue
        lo, hi = snapshot.window(request)
        slots = snapshot.dur(request)
        if request.pref_day is not None:
            day = min(max(request.pref_day, lo), hi)
        else:
            day = lo
        if request.pref_offset is not None:
            offset = request.pref_offset
        else:
            offset = default_offset(request.dept, snapshot.per_day)
        offset = max(0, min(offset, snapshot.per_day - slots))
        plan.placements[request.id] = Placement(request.id, request.section, day, offset, slots)
    plan.blocks = merged_blocks(plan.placements.values())
    return plan
