"""Complexity metadata for the search algorithms.

This module is intentionally *pure data* (plus a couple of tiny helpers) so the
theory can be presented cleanly in the UI, in the README, and in tests without
dragging in pygame or the grid model.

Notation used below
-------------------
For a graph ``G = (V, E)`` explored by a search:

* ``V`` -- number of vertices (grid cells that are not walls).
* ``E`` -- number of edges (neighbour connections; on a 4-connected grid every
  cell has at most 4 edges, so ``E = O(V)`` here -- the grid is *sparse*).
* ``b`` -- the branching factor (<= 4 on a 4-connected grid).
* ``d`` -- the depth of the shallowest goal (length of the optimal path).

Why the grid matters: because a grid is a sparse graph with ``E = O(V)``, the
textbook ``O(V + E)`` bounds collapse to ``O(V)`` in practice. We still quote
the general graph bounds because that is what you are expected to reason about
as a quant developer -- the grid is just the thing we can *see*.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AlgorithmInfo:
    """Static, human-facing description of a search algorithm.

    Attributes
    ----------
    key:
        Stable identifier used by :mod:`algorithms` and the UI.
    name:
        Display name.
    time:
        Worst-case time complexity in big-O.
    space:
        Worst-case space (auxiliary memory) complexity in big-O.
    optimal:
        Whether the algorithm is guaranteed to return a shortest path on this
        grid (unit or non-negative weights, as noted).
    data_structure:
        The frontier data structure that gives the algorithm its behaviour.
    summary:
        One-sentence intuition for *how* it explores.
    notes:
        Longer explanation of the complexity and the trade-offs.
    """

    key: str
    name: str
    time: str
    space: str
    optimal: bool
    data_structure: str
    summary: str
    notes: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# The metadata table.  Keep the wording tight -- this text is rendered inside
# the pygame side panel, so it needs to stay readable at a glance.
# ---------------------------------------------------------------------------

ALGORITHMS: dict[str, AlgorithmInfo] = {
    "bfs": AlgorithmInfo(
        key="bfs",
        name="Breadth-First Search",
        time="O(V + E)",
        space="O(V)",
        optimal=True,  # optimal for UNIT edge weights
        data_structure="FIFO queue",
        summary="Expands the frontier outward in rings, one 'distance layer' at a time.",
        notes=(
            "BFS visits every cell at distance k before any cell at distance k+1, "
            "so on an unweighted grid the first time it reaches the goal it has "
            "found a shortest path. Every vertex is enqueued once (O(V)) and each "
            "edge is examined once (O(E)); on a 4-connected grid E = O(V). Space "
            "is dominated by the queue, which can hold O(V) cells."
        ),
        tags=("unweighted-optimal", "complete"),
    ),
    "dfs": AlgorithmInfo(
        key="dfs",
        name="Depth-First Search",
        time="O(V + E)",
        space="O(V)",
        optimal=False,
        data_structure="LIFO stack (or recursion)",
        summary="Plunges as deep as possible along one path before backtracking.",
        notes=(
            "DFS follows a single branch to exhaustion, then backtracks. It touches "
            "every vertex and edge in the worst case (O(V + E)). The stack depth is "
            "bounded by the longest simple path, i.e. O(V) in the worst case. DFS is "
            "NOT optimal: the path it returns is whatever it happened to reach the "
            "goal along, which is usually far from shortest."
        ),
        tags=("not-optimal", "complete-finite"),
    ),
    "dijkstra": AlgorithmInfo(
        key="dijkstra",
        name="Dijkstra's Algorithm",
        time="O((V + E) log V)",
        space="O(V)",
        optimal=True,
        data_structure="min-priority queue (binary heap)",
        summary="Expands cells in order of cheapest cumulative cost g(n) from the start.",
        notes=(
            "Dijkstra generalises BFS to non-negative edge weights. With a binary "
            "heap, each of the V extract-min operations costs O(log V) and each of "
            "the E edges can trigger a decrease-key / push costing O(log V), giving "
            "O((V + E) log V). It is optimal for any non-negative weights. On a unit-"
            "weight grid it behaves like BFS but pays the log factor for the heap."
        ),
        tags=("weighted-optimal", "complete"),
    ),
    "astar": AlgorithmInfo(
        key="astar",
        name="A* Search",
        time="O(b^d) worst case",
        space="O(b^d)",
        optimal=True,  # with an admissible (and, for graph search, consistent) heuristic
        data_structure="min-priority queue keyed on f = g + h",
        summary="Dijkstra guided toward the goal by a heuristic estimate h(n).",
        notes=(
            "A* orders the frontier by f(n) = g(n) + h(n): known cost so far plus an "
            "estimate of the cost to the goal. With an ADMISSIBLE heuristic (never "
            "overestimates) it is optimal; with a CONSISTENT heuristic it never needs "
            "to reopen a closed node. Its running time is heuristic-dependent: a "
            "perfect heuristic explores a near-straight line, while h = 0 degrades it "
            "exactly to Dijkstra. The classic worst-case bound is O(b^d)."
        ),
        tags=("weighted-optimal", "informed", "heuristic"),
    ),
    "greedy": AlgorithmInfo(
        key="greedy",
        name="Greedy Best-First Search",
        time="O(b^m) worst case",
        space="O(b^m)",
        optimal=False,
        data_structure="min-priority queue keyed on h(n) only",
        summary="Always steps toward whatever cell looks closest to the goal (h only).",
        notes=(
            "Greedy best-first ignores the cost already paid (g) and expands the "
            "frontier cell with the smallest heuristic h(n). This makes it fast and "
            "very goal-directed, but it is NOT optimal and can be led badly astray by "
            "obstacles. m is the maximum depth of the search space."
        ),
        tags=("not-optimal", "informed", "heuristic"),
    ),
}


#: Display order for menus / cycling in the UI.
ORDER: tuple[str, ...] = ("bfs", "dfs", "dijkstra", "astar", "greedy")


def get(key: str) -> AlgorithmInfo:
    """Return the :class:`AlgorithmInfo` for ``key`` (raises ``KeyError`` if absent)."""
    return ALGORITHMS[key]


def optimal_algorithms() -> tuple[str, ...]:
    """Keys of algorithms that guarantee a shortest path on a non-negative grid."""
    return tuple(k for k, v in ALGORITHMS.items() if v.optimal)


if __name__ == "__main__":  # pragma: no cover - manual inspection helper
    for _key in ORDER:
        _info = ALGORITHMS[_key]
        print(f"{_info.name}")
        print(f"  time : {_info.time}")
        print(f"  space: {_info.space}")
        print(f"  optimal shortest path: {_info.optimal}")
        print(f"  frontier: {_info.data_structure}")
        print(f"  {_info.summary}")
        print()
