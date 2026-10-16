"""The solver never calls a model during search. A CostProvider produces integer arrays
before solving, and the model reads them through prefix sums and element constraints."""
from typing import Protocol

from app.planner.snapshot import Snapshot


class CostProvider(Protocol):
    def cost(self, section: str, day: int) -> list[int]:
        """Cost of closing the section during each slot of the day."""


class TrafficCountCost:
    """MVP provider: weighted trains in each slot (premium trains weigh more than goods)."""

    def __init__(self, snapshot: Snapshot):
        self.snapshot = snapshot

    def cost(self, section: str, day: int) -> list[int]:
        return self.snapshot.cost_at(section, day)
