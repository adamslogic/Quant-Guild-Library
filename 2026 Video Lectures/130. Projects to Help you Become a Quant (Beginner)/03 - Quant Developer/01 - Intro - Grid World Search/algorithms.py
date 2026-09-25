r"""Graph-search algorithms as animatable, testable generators.

This is the heart of the project. Every algorithm is written as a **generator**
that yields a :class:`SearchState` snapshot after each expansion. That single
design choice buys us two things at once:

1. **Visualisation** -- ``main.py`` can pull one snapshot per animation frame and
   colour the frontier, the visited/closed set, and (once found) the path.
2. **Testability** -- the exact same generators can be driven to completion in a
   headless unit test (no pygame, no window) to assert correctness.

Nothing in this module imports pygame. The only dependency is :mod:`grid`.

The four core algorithms and how they differ
--------------------------------------------
All of them are the *same* skeleton -- "pop a cell from the frontier, expand its
neighbours, repeat" -- and differ only in **which cell they pop next**:

* **BFS**       pops the *oldest* cell (FIFO queue)          -> explores in rings.
* **DFS**       pops the *newest* cell (LIFO stack)          -> plunges deep.
* **Dijkstra**  pops the cell with least cost-so-far g(n)    -> expands by cost.
* **A\***       pops the cell with least f(n) = g(n) + h(n)  -> heads for the goal.
* **Greedy**    pops the cell with least heuristic h(n)      -> heads for the goal, ignores g.

Seeing that "only the frontier data structure changes" is the whole lesson.
"""

from __future__ import annotations

import heapq
import itertools
import math
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Iterator

from grid import Cell, Grid

# A generator of search snapshots.
SearchGen = Iterator["SearchState"]


# ---------------------------------------------------------------------------
# Snapshot + final-result data structures
# ---------------------------------------------------------------------------
@dataclass
class SearchState:
    """One frame of a running search, handed to the visualiser each step.

    Attributes
    ----------
    current:
        The cell just popped from the frontier and expanded this step
        (``None`` on the terminal frame).
    frontier:
        Cells currently waiting to be expanded (the "open set").
    visited:
        Cells already expanded (the "closed set").
    path:
        The reconstructed path once the goal is reached; ``None`` until then.
    found:
        ``True`` on the terminal frame iff the goal was reached.
    done:
        ``True`` on the terminal frame (goal found *or* frontier exhausted).
    expanded:
        Running count of cells expanded (pops).
    frontier_max:
        Largest frontier size seen so far (a proxy for peak memory / space).
    """

    current: Cell | None
    frontier: list[Cell]
    visited: set[Cell]
    path: list[Cell] | None = None
    found: bool = False
    done: bool = False
    expanded: int = 0
    frontier_max: int = 0


@dataclass
class SearchResult:
    """Summary of a completed search (produced by :func:`run_to_completion`)."""

    found: bool
    path: list[Cell] = field(default_factory=list)
    expanded: int = 0
    frontier_max: int = 0
    path_cost: float = math.inf
    elapsed: float = 0.0

    @property
    def path_length(self) -> int:
        """Number of cells in the path (0 if no path)."""
        return len(self.path)

    @property
    def steps(self) -> int:
        """Number of moves in the path (path_length - 1, or 0)."""
        return max(0, len(self.path) - 1)


# ---------------------------------------------------------------------------
# Heuristics (for informed search)
# ---------------------------------------------------------------------------
def manhattan(a: Cell, b: Cell) -> float:
    """L1 distance -- admissible on a 4-connected grid with unit steps."""
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def euclidean(a: Cell, b: Cell) -> float:
    """L2 distance -- admissible but weaker (looser) on a 4-connected grid."""
    return math.hypot(a[0] - b[0], a[1] - b[1])


Heuristic = Callable[[Cell, Cell], float]


# ---------------------------------------------------------------------------
# Path reconstruction
# ---------------------------------------------------------------------------
def reconstruct_path(came_from: dict[Cell, Cell], start: Cell, goal: Cell) -> list[Cell]:
    """Walk the ``came_from`` back-pointers from ``goal`` to ``start``.

    Returns the path as a list ``[start, ..., goal]``. If ``goal`` was never
    reached, returns an empty list.
    """
    if goal not in came_from and goal != start:
        return []
    path: list[Cell] = [goal]
    node = goal
    while node != start:
        node = came_from[node]
        path.append(node)
    path.reverse()
    return path


# ---------------------------------------------------------------------------
# Uninformed search: BFS and DFS
# ---------------------------------------------------------------------------
def bfs(grid: Grid) -> SearchGen:
    """Breadth-first search. FIFO frontier -> shortest path on UNIT weights.

    Time O(V + E), space O(V). We mark cells visited *when enqueued* so each
    cell enters the queue at most once.
    """
    start, goal = grid.start, grid.goal
    frontier: deque[Cell] = deque([start])
    came_from: dict[Cell, Cell] = {}
    visited: set[Cell] = {start}
    expanded = 0
    frontier_max = 1

    while frontier:
        current = frontier.popleft()
        expanded += 1

        if current == goal:
            path = reconstruct_path(came_from, start, goal)
            yield SearchState(None, list(frontier), visited, path, True, True,
                              expanded, frontier_max)
            return

        for nb in grid.neighbors(current):
            if nb not in visited:
                visited.add(nb)
                came_from[nb] = current
                frontier.append(nb)
        frontier_max = max(frontier_max, len(frontier))

        yield SearchState(current, list(frontier), visited, None, False, False,
                          expanded, frontier_max)

    # Frontier exhausted without reaching the goal.
    yield SearchState(None, [], visited, [], False, True, expanded, frontier_max)


def dfs(grid: Grid) -> SearchGen:
    """Depth-first search. LIFO frontier -> deep-diving, NOT optimal.

    Time O(V + E), space O(V). We only mark a cell visited when it is popped, so
    the stack mirrors a genuine recursive DFS.
    """
    start, goal = grid.start, grid.goal
    frontier: list[Cell] = [start]
    came_from: dict[Cell, Cell] = {}
    visited: set[Cell] = set()
    expanded = 0
    frontier_max = 1

    while frontier:
        current = frontier.pop()
        if current in visited:
            continue
        visited.add(current)
        expanded += 1

        if current == goal:
            path = reconstruct_path(came_from, start, goal)
            yield SearchState(None, list(frontier), visited, path, True, True,
                              expanded, frontier_max)
            return

        for nb in grid.neighbors(current):
            if nb not in visited:
                # Record the first parent that reaches nb; if a later expansion
                # supersedes it, the came_from will be overwritten when popped.
                came_from.setdefault(nb, current)
                frontier.append(nb)
        frontier_max = max(frontier_max, len(frontier))

        yield SearchState(current, list(frontier), visited, None, False, False,
                          expanded, frontier_max)

    yield SearchState(None, [], visited, [], False, True, expanded, frontier_max)


# ---------------------------------------------------------------------------
# Informed / weighted search: Dijkstra, A*, Greedy
# ---------------------------------------------------------------------------
def _best_first(grid: Grid, priority: Callable[[Cell, float], float]) -> SearchGen:
    """Shared skeleton for Dijkstra / A* / Greedy.

    ``priority(cell, g)`` maps a cell and its cost-so-far ``g`` to the key used
    to order the min-heap. This is the single knob that turns one algorithm into
    another:

    * Dijkstra: ``priority = g``
    * A*:       ``priority = g + h(cell, goal)``
    * Greedy:   ``priority = h(cell, goal)``

    ``g`` accumulates ``grid.cost(cell)`` (terrain weight) along the path, so
    Dijkstra and A* respect weighted terrain while BFS/DFS do not.
    """
    start, goal = grid.start, grid.goal
    # A tie-breaking counter keeps the heap deterministic and avoids comparing
    # Cell tuples when priorities are equal.
    counter = itertools.count()
    g_score: dict[Cell, float] = {start: 0.0}
    came_from: dict[Cell, Cell] = {}
    heap: list[tuple[float, int, Cell]] = [(priority(start, 0.0), next(counter), start)]
    in_heap: set[Cell] = {start}
    closed: set[Cell] = set()
    expanded = 0
    frontier_max = 1

    while heap:
        _, _, current = heapq.heappop(heap)
        in_heap.discard(current)
        if current in closed:
            continue
        closed.add(current)
        expanded += 1

        if current == goal:
            path = reconstruct_path(came_from, start, goal)
            yield SearchState(None, sorted(in_heap), closed, path, True, True,
                              expanded, frontier_max)
            return

        base_g = g_score[current]
        for nb in grid.neighbors(current):
            if nb in closed:
                continue
            tentative_g = base_g + grid.cost(nb)
            if tentative_g < g_score.get(nb, math.inf):
                g_score[nb] = tentative_g
                came_from[nb] = current
                heapq.heappush(heap, (priority(nb, tentative_g), next(counter), nb))
                in_heap.add(nb)
        frontier_max = max(frontier_max, len(heap))

        yield SearchState(current, sorted(in_heap), closed, None, False, False,
                          expanded, frontier_max)

    yield SearchState(None, [], closed, [], False, True, expanded, frontier_max)


def dijkstra(grid: Grid) -> SearchGen:
    """Dijkstra's algorithm: expand by least cumulative cost g(n).

    Optimal for non-negative edge weights. Time O((V + E) log V) with a binary
    heap; space O(V).
    """
    return _best_first(grid, priority=lambda cell, g: g)


def astar(grid: Grid, heuristic: Heuristic = manhattan) -> SearchGen:
    """A* search: expand by f(n) = g(n) + h(n).

    Optimal with an admissible heuristic. On a unit grid ``manhattan`` is
    admissible *and* consistent, so no node is ever reopened.
    """
    goal = grid.goal
    return _best_first(grid, priority=lambda cell, g: g + heuristic(cell, goal))


def greedy(grid: Grid, heuristic: Heuristic = manhattan) -> SearchGen:
    """Greedy best-first search: expand by heuristic h(n) alone.

    Fast and goal-directed but NOT optimal -- it ignores the cost already paid.
    """
    goal = grid.goal
    return _best_first(grid, priority=lambda cell, g: heuristic(cell, goal))


# ---------------------------------------------------------------------------
# Registry + driver
# ---------------------------------------------------------------------------
#: Maps a stable key (see :mod:`complexity`) to a generator factory.
ALGORITHMS: dict[str, Callable[[Grid], SearchGen]] = {
    "bfs": bfs,
    "dfs": dfs,
    "dijkstra": dijkstra,
    "astar": astar,
    "greedy": greedy,
}


def make_search(key: str, grid: Grid) -> SearchGen:
    """Return the generator for algorithm ``key`` running on ``grid``."""
    try:
        factory = ALGORITHMS[key]
    except KeyError as exc:  # pragma: no cover - defensive
        raise KeyError(f"unknown algorithm {key!r}; choose from {list(ALGORITHMS)}") from exc
    return factory(grid)


def path_cost(grid: Grid, path: list[Cell]) -> float:
    """Total terrain cost of following ``path`` (sum of entered-cell weights).

    The start cell is not "entered", so its weight is excluded -- this matches
    the ``g`` accumulation in :func:`_best_first`.
    """
    if not path:
        return math.inf
    return float(sum(grid.cost(cell) for cell in path[1:]))


def run_to_completion(key: str, grid: Grid) -> SearchResult:
    """Drive an algorithm generator to the end and summarise the result.

    This is what the headless tests call. It never touches pygame.
    """
    gen = make_search(key, grid)
    last: SearchState | None = None
    t0 = time.perf_counter()
    for state in gen:
        last = state
    elapsed = time.perf_counter() - t0

    if last is None:  # start == goal edge case handled below anyway
        return SearchResult(found=False, elapsed=elapsed)

    found = last.found
    path = last.path or []
    return SearchResult(
        found=found,
        path=path,
        expanded=last.expanded,
        frontier_max=last.frontier_max,
        path_cost=path_cost(grid, path) if found else math.inf,
        elapsed=elapsed,
    )
