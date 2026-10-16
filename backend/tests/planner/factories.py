"""Helpers to build small planner instances by hand."""
from app.planner.snapshot import PlanDependency, PlanRequest, Snapshot


def req(
    id,
    dept="ENGG",
    section="A-B",
    minutes=120,
    earliest=0,
    deadline=3,
    priority=2,
    **extra,
) -> PlanRequest:
    return PlanRequest(
        id=id,
        dept=dept,
        section=section,
        duration_minutes=minutes,
        earliest_day=earliest,
        deadline_day=deadline,
        priority=priority,
        **extra,
    )


def dep(before, after, relation="finish_before_start", gap=0) -> PlanDependency:
    return PlanDependency(before=before, after=after, relation=relation, gap_minutes=gap)


def snap(requests, deps=(), days=7, slot_minutes=30, max_block_minutes=360, **extra) -> Snapshot:
    return Snapshot(
        days=days,
        slot_minutes=slot_minutes,
        max_block_minutes=max_block_minutes,
        requests=tuple(requests),
        dependencies=tuple(deps),
        **extra,
    )


def quiet_night_traffic(section, days, busy=3, night_slots=range(12)):
    """Traffic that is heavy all day except for a quiet night (slots 0-11 = 00:00-06:00)."""
    day_array = [0 if s in night_slots else busy for s in range(48)]
    return {section: {d: list(day_array) for d in range(days)}}
