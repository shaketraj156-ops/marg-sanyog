from collections.abc import Iterable


def find_cycle(start: int, new_targets: Iterable[int], edges: dict[int, set[int]]) -> list[int] | None:
    """Would giving `start` the dependencies `new_targets` create a cycle?

    edges[x] is the set of requests x depends on (without start's own old edges).
    A cycle exists exactly when `start` is reachable from one of the new targets.
    Depth-first search; returns the cycle as a list of ids, or None.
    """
    stack = [(target, [start, target]) for target in new_targets]
    seen: set[int] = set()
    while stack:
        node, path = stack.pop()
        if node == start:
            return path
        if node in seen:
            continue
        seen.add(node)
        for nxt in edges.get(node, ()):
            stack.append((nxt, [*path, nxt]))
    return None
