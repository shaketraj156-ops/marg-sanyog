"""Explanations: reason codes with text built from numbers computed in code.

Nothing here is generated prose about the data. Every number comes from the snapshot, the plan
and the baseline, so the text reconciles with the metrics. Savings are counterfactual: the
requests of a block are compared with the same requests at their independent-plan placements,
using the same metrics function on both."""
import math
from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.timeutil import to_ist
from app.db.models import Block, Explanation, PlanRun, Section
from app.planner.metrics import compute_metrics
from app.planner.plan import Plan, merged_blocks
from app.planner.slots import hhmm, prefix_sums
from app.planner.snapshot import (
    DEPENDENCY_UNMET,
    NO_CAPACITY,
    OUT_OF_HORIZON,
    TOO_LONG,
    Snapshot,
)
from app.services.plan_service import horizon_start_date

LOW_TRAFFIC_PERCENT = 25


@dataclass
class Draft:
    code: str
    text: str
    numbers: dict = field(default_factory=dict)
    block: tuple[str, int] | None = None  # (section code, day index)
    request_id: int | None = None


def label(request_id: int) -> str:
    return f"R{request_id}"


def names(ids) -> str:
    items = [label(i) for i in sorted(ids)]
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def plural(count: int, word: str) -> str:
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def fmt_day(start_date: date, day: int) -> str:
    moment = start_date + timedelta(days=day)
    return f"{moment:%a} {moment.day} {moment:%b}"


def _trains_phrase(delta: int) -> str:
    if delta == 0:
        return "no change in trains affected"
    return f"{abs(delta)} {'more' if delta > 0 else 'fewer'} trains affected"


def explain(
    snapshot: Snapshot,
    plan: Plan,
    baseline: Plan,
    start_date: date,
    parent: Plan | None = None,
    overridden: frozenset[int] = frozenset(),
) -> list[Draft]:
    requests = {r.id: r for r in snapshot.requests}
    drafts: list[Draft] = []
    for block in plan.blocks:
        members = list(block.request_ids)
        if len(members) >= 2:
            drafts.append(_merged(snapshot, baseline, block, members))
        low = _low_traffic(snapshot, requests, block, members, start_date)
        if low:
            drafts.append(low)
    for request_id, placement in sorted(plan.placements.items()):
        late = _deadline_driven(snapshot, plan, requests[request_id], placement, start_date)
        if late:
            drafts.append(late)
    drafts += _dependency_order(snapshot, plan, start_date)
    for request_id, reason in sorted(plan.deferred.items()):
        drafts.append(_deferred(snapshot, plan, requests[request_id], reason, start_date))
    if parent is not None:
        drafts += _overrides(snapshot, plan, parent, overridden, start_date)
    return drafts


# ---------- one explanation per reason code ----------


def _subset_metrics(snapshot: Snapshot, plan: Plan, ids) -> dict:
    subset = {i: plan.placements[i] for i in ids if i in plan.placements}
    return compute_metrics(snapshot, Plan(subset, {}, merged_blocks(subset.values())))


def _merged(snapshot: Snapshot, baseline: Plan, block, members: list[int]) -> Draft:
    independent = _subset_metrics(snapshot, baseline, members)
    shared_slots = block.end - block.start
    shared_hours = round(shared_slots * snapshot.slot_minutes / 60, 2)
    shared_trains = sum(snapshot.trains_at(block.section, block.day)[block.start : block.end])
    avoided = independent["closures"] - 1
    saved_hours = round(independent["block_hours"] - shared_hours, 2)
    saved_trains = independent["trains_affected"] - shared_trains
    return Draft(
        "MERGED",
        f"{names(members)} share one block on {block.section}: {plural(avoided, 'closure')} "
        f"avoided, {saved_hours:g} block-hours saved versus independent planning.",
        {
            "requests": members,
            "closures_independent": independent["closures"],
            "closures_avoided": avoided,
            "block_hours_independent": independent["block_hours"],
            "block_hours_shared": shared_hours,
            "block_hours_saved": saved_hours,
            "trains_saved": saved_trains,
        },
        block=(block.section, block.day),
    )


def _low_traffic(snapshot: Snapshot, requests, block, members, start_date: date) -> Draft | None:
    width = block.end - block.start
    first = max(snapshot.window(requests[i])[0] for i in members)
    last = min(snapshot.window(requests[i])[1] for i in members)
    costs = []
    for day in range(first, last + 1):
        cum = prefix_sums(snapshot.cost_at(block.section, day))
        costs += [cum[s + width] - cum[s] for s in range(snapshot.per_day - width + 1)]
    if not costs or not any(costs):
        return None  # no traffic data: nothing to say
    chosen_cum = prefix_sums(snapshot.cost_at(block.section, block.day))
    chosen = chosen_cum[block.end] - chosen_cum[block.start]
    quieter = sum(1 for c in costs if c < chosen)
    percent = math.ceil(100 * (quieter + 1) / len(costs))
    if percent > LOW_TRAFFIC_PERCENT:
        return None
    trains = sum(snapshot.trains_at(block.section, block.day)[block.start : block.end])
    ordered = sorted(costs)
    median = ordered[len(ordered) // 2]
    when = f"{hhmm(block.start, snapshot.slot_minutes)}-{hhmm(block.end, snapshot.slot_minutes)}"
    return Draft(
        "LOW_TRAFFIC",
        f"The window {when} on {fmt_day(start_date, block.day)} is in the quietest {percent} "
        f"percent of {len(costs)} feasible windows for {block.section} "
        f"({trains} trains affected; the median window costs {median} against {chosen}).",
        {
            "quietest_percent": percent,
            "feasible_windows": len(costs),
            "window_cost": chosen,
            "median_cost": median,
            "trains_in_window": trains,
        },
        block=(block.section, block.day),
    )


def _deadline_driven(snapshot: Snapshot, plan: Plan, request, placement, start_date) -> Draft | None:
    lo, hi = snapshot.window(request)
    if placement.day <= lo:
        return None
    postponed = placement.day - lo
    slack = hi - placement.day
    block_members = [
        i for i, p in plan.placements.items() if (p.section, p.day) == (placement.section, placement.day)
    ]
    shared_with = len(block_members) - 1
    window = (placement.offset, placement.end)
    trains_now = sum(snapshot.trains_at(request.section, placement.day)[window[0] : window[1]])
    trains_then = sum(snapshot.trains_at(request.section, lo)[window[0] : window[1]])
    text = (
        f"{label(request.id)} was placed on {fmt_day(start_date, placement.day)}, "
        f"{plural(postponed, 'day')} after its earliest date; its deadline is "
        f"{fmt_day(start_date, hi)} ({plural(slack, 'day')} of slack)"
    )
    if shared_with > 0:
        text += f", to share a block with {plural(shared_with, 'other request')}."
    elif trains_then > trains_now:
        text += f", which avoids {trains_then - trains_now} trains compared with the same hours on {fmt_day(start_date, lo)}."
    else:
        text += "."
    return Draft(
        "DEADLINE_DRIVEN",
        text,
        {
            "earliest_day": fmt_day(start_date, lo),
            "placed_day": fmt_day(start_date, placement.day),
            "deadline_day": fmt_day(start_date, hi),
            "days_postponed": postponed,
            "slack_days": slack,
            "shares_block_with": shared_with,
            "trains_in_window": trains_now,
            "trains_same_hours_on_earliest_day": trains_then,
        },
        block=(placement.section, placement.day),
        request_id=request.id,
    )


def _dependency_order(snapshot: Snapshot, plan: Plan, start_date: date) -> list[Draft]:
    drafts = []
    per_day = snapshot.per_day
    for dep in snapshot.dependencies:
        if dep.relation != "finish_before_start":
            continue
        before, after = plan.placements.get(dep.before), plan.placements.get(dep.after)
        if before is None or after is None:
            continue
        before_end = before.day * per_day + before.end
        after_start = after.day * per_day + after.offset
        slack = (after_start - before_end) * snapshot.slot_minutes
        drafts.append(
            Draft(
                "DEPENDENCY_ORDER",
                f"{label(dep.after)} starts at {hhmm(after.offset, snapshot.slot_minutes)} on "
                f"{fmt_day(start_date, after.day)}, after {label(dep.before)} finishes at "
                f"{hhmm(before.end, snapshot.slot_minutes)} on {fmt_day(start_date, before.day)} "
                f"(required gap {dep.gap_minutes} minutes, actual {slack}).",
                {
                    "before": dep.before,
                    "after": dep.after,
                    "required_gap_minutes": dep.gap_minutes,
                    "actual_gap_minutes": slack,
                },
                block=(after.section, after.day),
                request_id=dep.after,
            )
        )
    return drafts


def _deferred(snapshot: Snapshot, plan: Plan, request, reason: str, start_date: date) -> Draft:
    who = label(request.id)
    numbers: dict = {"reason": reason}
    if reason == TOO_LONG:
        numbers |= {
            "duration_minutes": request.duration_minutes,
            "limit_minutes": min(snapshot.max_block_minutes, snapshot.per_day * snapshot.slot_minutes),
        }
        text = (
            f"{who} was not placed: it needs {request.duration_minutes} minutes, more than the "
            f"{numbers['limit_minutes']}-minute block maximum ({reason})."
        )
    elif reason == OUT_OF_HORIZON:
        numbers["deadline_day"] = fmt_day(start_date, request.deadline_day)
        text = (
            f"{who} was not placed: its deadline {numbers['deadline_day']} is outside the "
            f"planning horizon ({reason})."
        )
    elif reason == DEPENDENCY_UNMET:
        missing = sorted(
            d.before
            for d in snapshot.dependencies
            if d.after == request.id
            and d.relation == "finish_before_start"
            and d.before not in plan.placements
        )
        numbers["waiting_for"] = missing
        text = (
            f"{who} was not placed: it must follow {names(missing)}, which could not be placed "
            f"({reason})."
        )
    else:
        assert reason == NO_CAPACITY
        text = (
            f"{who} was not placed: crews, the block maximum and other work left no room "
            f"within its dates ({reason})."
        )
    return Draft("DEFERRED", text, numbers, request_id=request.id)


def _overrides(
    snapshot: Snapshot, plan: Plan, parent: Plan, overridden: frozenset[int], start_date: date
) -> list[Draft]:
    now, before = compute_metrics(snapshot, plan), compute_metrics(snapshot, parent)
    trains = now["trains_affected"] - before["trains_affected"]
    closures = now["closures"] - before["closures"]
    hours = round(now["block_hours"] - before["block_hours"], 2)
    drafts = []
    for request_id in sorted(overridden):
        placement = plan.placements[request_id]
        old = parent.placements.get(request_id)
        where = (
            f"{fmt_day(start_date, placement.day)} "
            f"{hhmm(placement.offset, snapshot.slot_minutes)}-{hhmm(placement.end, snapshot.slot_minutes)}"
        )
        drafts.append(
            Draft(
                "OVERRIDE",
                f"{label(request_id)} was moved by a planner to {where}: "
                f"{_trains_phrase(trains)}, {closures:+d} closures, {hours:+g} block-hours "
                f"compared with the original plan.",
                {
                    "moved_to": where,
                    "moved_from": (
                        f"{fmt_day(start_date, old.day)} "
                        f"{hhmm(old.offset, snapshot.slot_minutes)}-{hhmm(old.end, snapshot.slot_minutes)}"
                        if old
                        else None
                    ),
                    "trains_affected_change": trains,
                    "closures_change": closures,
                    "block_hours_change": hours,
                },
                block=(placement.section, placement.day),
                request_id=request_id,
            )
        )
    return drafts


# ---------- saving ----------


def save(db: Session, run: PlanRun, drafts: list[Draft]) -> None:
    """Write explanations in the caller's transaction (the same one that saves the plan)."""
    sections = {s.id: s.code for s in db.scalars(select(Section))}
    start_date = horizon_start_date(run)
    block_ids = {}
    for row in db.scalars(select(Block).where(Block.plan_run_id == run.id)):
        day = (to_ist(row.start_ts).date() - start_date).days
        block_ids[sections[row.section_id], day] = row.id
    for draft in drafts:
        db.add(
            Explanation(
                plan_run_id=run.id,
                block_id=block_ids.get(draft.block) if draft.block else None,
                request_id=draft.request_id,
                code=draft.code,
                text=draft.text,
                numbers=draft.numbers,
            )
        )
