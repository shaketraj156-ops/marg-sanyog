"""One metrics function scores every plan, so the baseline comparison is fair."""
from app.planner.plan import Plan, span_blocks
from app.planner.slots import prefix_sums
from app.planner.snapshot import Snapshot


def _window_total(arrays_at, snapshot: Snapshot, blocks) -> int:
    total = 0
    for block in blocks:
        cum = prefix_sums(arrays_at(block.section, block.day))
        total += cum[block.end] - cum[block.start]
    return total


def postponement_days(snapshot: Snapshot, plan: Plan) -> int:
    """Priority-weighted days between the earliest allowed day and the chosen day."""
    requests = {r.id: r for r in snapshot.requests}
    total = 0
    for placement in plan.placements.values():
        request = requests[placement.request_id]
        total += request.priority * (placement.day - snapshot.window(request)[0])
    return total


def compute_metrics(snapshot: Snapshot, plan: Plan) -> dict:
    """Closures, block hours and trains affected, plus the numbers behind the objective."""
    block_slots = sum(b.end - b.start for b in plan.blocks)
    return {
        "closures": len(plan.blocks),
        "block_hours": round(block_slots * snapshot.slot_minutes / 60, 2),
        "trains_affected": _window_total(snapshot.trains_at, snapshot, plan.blocks),
        "traffic_cost": _window_total(snapshot.cost_at, snapshot, plan.blocks),
        "weighted_postponement_days": postponement_days(snapshot, plan),
        "deferred": len(plan.deferred),
    }


def objective(snapshot: Snapshot, plan: Plan) -> int:
    """The solver's objective evaluated on a plan (one closure window per section and day)."""
    blocks = span_blocks(plan.placements.values())
    requests = {r.id: r for r in snapshot.requests}
    window_slots = sum(b.end - b.start for b in blocks)
    deferral = sum(requests[i].priority for i in plan.deferred)
    return (
        snapshot.weight("block") * len(blocks)
        + snapshot.weight("traffic") * _window_total(snapshot.cost_at, snapshot, blocks)
        + snapshot.weight("delay") * postponement_days(snapshot, plan)
        + window_slots
        + snapshot.weight("defer") * deferral
    )
