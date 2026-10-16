"""Output of the planner: where each request goes and which closures result."""
from collections import defaultdict
from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class Placement:
    request_id: int
    section: str
    day: int
    offset: int  # start slot within the day
    slots: int  # duration in slots

    @property
    def end(self) -> int:
        return self.offset + self.slots


@dataclass(frozen=True)
class Block:
    """One closure of a section: slots [start, end) of one day."""

    section: str
    day: int
    start: int
    end: int
    request_ids: tuple[int, ...]


@dataclass
class Plan:
    placements: dict[int, Placement] = field(default_factory=dict)
    deferred: dict[int, str] = field(default_factory=dict)  # request id -> reason code
    blocks: list[Block] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "placements": [asdict(p) for p in self.placements.values()],
            "deferred": {str(k): v for k, v in self.deferred.items()},
            "blocks": [asdict(b) for b in self.blocks],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Plan":
        placements = {p["request_id"]: Placement(**p) for p in data["placements"]}
        blocks = [Block(**{**b, "request_ids": tuple(b["request_ids"])}) for b in data["blocks"]]
        return cls(placements, {int(k): v for k, v in data["deferred"].items()}, blocks)


def _groups(placements) -> dict[tuple[str, int], list[Placement]]:
    groups: dict[tuple[str, int], list[Placement]] = defaultdict(list)
    for placement in placements:
        groups[(placement.section, placement.day)].append(placement)
    return groups


def span_blocks(placements) -> list[Block]:
    """Integrated plan: one closure per section and day, from the first start to the last end."""
    blocks = []
    for (section, day), group in sorted(_groups(placements).items()):
        blocks.append(
            Block(
                section,
                day,
                min(p.offset for p in group),
                max(p.end for p in group),
                tuple(sorted(p.request_id for p in group)),
            )
        )
    return blocks


def merged_blocks(placements) -> list[Block]:
    """Independent plan: each request closes the section by itself (each block application is
    granted separately). Only requests that truly overlap in time share a closure; work that
    merely touches end to start is still two closures."""
    blocks = []
    for (section, day), group in sorted(_groups(placements).items()):
        group.sort(key=lambda p: (p.offset, p.end))
        current = [group[0]]
        for placement in group[1:]:
            if placement.offset < max(p.end for p in current):
                current.append(placement)
            else:
                blocks.append(_block(section, day, current))
                current = [placement]
        blocks.append(_block(section, day, current))
    return blocks


def _block(section: str, day: int, group: list[Placement]) -> Block:
    return Block(
        section,
        day,
        min(p.offset for p in group),
        max(p.end for p in group),
        tuple(sorted(p.request_id for p in group)),
    )
