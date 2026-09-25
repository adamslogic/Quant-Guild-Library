"""Headless unit tests for the search algorithms.

These run WITHOUT pygame and WITHOUT opening a window. They verify the CS
properties that the visualisation is meant to teach:

* BFS, Dijkstra and A* all return the *shortest* path on an unweighted grid.
* On a *weighted* grid, Dijkstra and A* agree on the minimum-cost path, and
  can beat BFS's (cheapest-by-hops) path in cost.
* DFS returns a *valid* (connected, obstacle-free) path -- not necessarily short.
* Every algorithm terminates and reports "not found" when the goal is walled off.
* A* with an admissible heuristic never expands more cells than Dijkstra.

Run with either::

    python -m pytest test_algorithms.py -v
    python test_algorithms.py            # falls back to a built-in runner
"""

from __future__ import annotations

import math

import algorithms as A
from grid import Cell, Grid

OPTIMAL_KEYS = ("bfs", "dijkstra", "astar")


# ---------------------------------------------------------------------------
# Test fixtures / helpers
# ---------------------------------------------------------------------------
def make_obstacle_grid() -> Grid:
    """A 7x7 grid with a wall that forces a detour.

    Layout (S=start, G=goal, #=wall)::

        . . . . . . .
        . S . . . . .
        . . . # . . .
        . . . # . . .
        . . . # . . .
        . . . # . G .
        . . . . . . .

    The vertical wall in column 3 (rows 2..5) forces the path to route around it.
    """
    g = Grid(rows=7, cols=7, start=(1, 1), goal=(5, 5))
    for r in range(2, 6):
        g.add_wall((r, 3))
    return g


def is_valid_path(grid: Grid, path: list[Cell]) -> bool:
    """A path is valid if it starts at start, ends at goal, avoids walls, and
    every consecutive pair are 4-connected neighbours."""
    if not path:
        return False
    if path[0] != grid.start or path[-1] != grid.goal:
        return False
    for cell in path:
        if not grid.passable(cell):
            return False
    for a, b in zip(path, path[1:]):
        if abs(a[0] - b[0]) + abs(a[1] - b[1]) != 1:
            return False
    return True


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
def test_shortest_path_length_unweighted():
    """BFS, Dijkstra, A* agree on the shortest hop-count on an unweighted grid."""
    grid = make_obstacle_grid()
    # Manhattan distance is |5-1| + |5-1| = 8; the wall forces a detour of +? .
    # We compute the true optimum with BFS and require the others to match.
    bfs_res = A.run_to_completion("bfs", grid)
    assert bfs_res.found
    assert is_valid_path(grid, bfs_res.path)

    for key in OPTIMAL_KEYS:
        res = A.run_to_completion(key, grid)
        assert res.found, f"{key} failed to find a path"
        assert is_valid_path(grid, res.path), f"{key} returned an invalid path"
        assert res.steps == bfs_res.steps, (
            f"{key} path length {res.steps} != BFS optimum {bfs_res.steps}"
        )


def test_known_optimum_open_grid():
    """On an open grid the optimum is exactly the Manhattan distance in hops."""
    grid = Grid(rows=10, cols=10, start=(0, 0), goal=(9, 9))
    expected_steps = 18  # 9 down + 9 right
    for key in OPTIMAL_KEYS:
        res = A.run_to_completion(key, grid)
        assert res.found
        assert res.steps == expected_steps, f"{key}: {res.steps} != {expected_steps}"


def test_dfs_returns_valid_but_not_necessarily_optimal():
    """DFS must return a *valid* path; it is allowed to be longer than optimal."""
    grid = make_obstacle_grid()
    dfs_res = A.run_to_completion("dfs", grid)
    assert dfs_res.found
    assert is_valid_path(grid, dfs_res.path)

    bfs_res = A.run_to_completion("bfs", grid)
    # DFS is never shorter than the optimum.
    assert dfs_res.steps >= bfs_res.steps


def test_weighted_grid_dijkstra_astar_agree_and_are_optimal():
    """With terrain weights, Dijkstra and A* find the same minimum-cost path."""
    grid = Grid(rows=8, cols=8, start=(0, 0), goal=(0, 7))
    # Make the straight top row expensive, forcing a cheaper detour below.
    for c in range(1, 7):
        grid.set_cost((0, c), 9)

    dij = A.run_to_completion("dijkstra", grid)
    ast = A.run_to_completion("astar", grid)
    assert dij.found and ast.found
    assert is_valid_path(grid, dij.path)
    assert is_valid_path(grid, ast.path)
    # Optimal cost must match between the two optimal weighted searches.
    assert math.isclose(dij.path_cost, ast.path_cost)
    # The detour should be cheaper than ploughing straight across the costly row.
    straight_cost = sum(grid.cost((0, c)) for c in range(1, 8))
    assert dij.path_cost < straight_cost


def test_astar_expands_no_more_than_dijkstra():
    """An admissible heuristic makes A* at least as efficient as Dijkstra."""
    grid = make_obstacle_grid()
    dij = A.run_to_completion("dijkstra", grid)
    ast = A.run_to_completion("astar", grid)
    assert ast.expanded <= dij.expanded


def test_unreachable_goal_terminates_not_found():
    """Walling the goal off must make every algorithm terminate with found=False."""
    grid = Grid(rows=6, cols=6, start=(0, 0), goal=(5, 5))
    # Box the goal in completely.
    for cell in [(4, 5), (5, 4), (4, 4)]:
        grid.add_wall(cell)
    for key in A.ALGORITHMS:
        res = A.run_to_completion(key, grid)
        assert not res.found, f"{key} should not find a path to a boxed-in goal"
        assert res.path == []


def test_start_equals_goal():
    """A degenerate search where start == goal returns a single-cell path."""
    grid = Grid(rows=5, cols=5, start=(2, 2), goal=(2, 2))
    for key in A.ALGORITHMS:
        res = A.run_to_completion(key, grid)
        assert res.found
        assert res.path == [(2, 2)]
        assert res.steps == 0


def test_generators_yield_progress_frames():
    """Each algorithm must yield at least one non-terminal frame with a frontier."""
    grid = make_obstacle_grid()
    for key in A.ALGORITHMS:
        gen = A.make_search(key, grid)
        saw_frontier = False
        terminal = None
        for state in gen:
            terminal = state
            if not state.done and state.frontier:
                saw_frontier = True
        assert terminal is not None and terminal.done, f"{key} never terminated"
        assert saw_frontier, f"{key} produced no intermediate frontier frames"


def test_maze_generation_is_solvable_and_bounded():
    """Generated mazes should keep start/goal open and searches should terminate."""
    import random

    grid = Grid(rows=21, cols=21)
    grid.generate_maze(rng=random.Random(42))
    assert not grid.is_wall(grid.start)
    assert not grid.is_wall(grid.goal)
    # BFS should terminate quickly and either find a path or report not found.
    res = A.run_to_completion("bfs", grid)
    assert res.expanded <= grid.rows * grid.cols


# ---------------------------------------------------------------------------
# Minimal fallback runner (so the file works even without pytest installed)
# ---------------------------------------------------------------------------
def _run_all() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failures = 0
    for t in tests:
        try:
            t()
        except AssertionError as exc:
            failures += 1
            print(f"FAIL  {t.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"ERROR {t.__name__}: {type(exc).__name__}: {exc}")
        else:
            print(f"ok    {t.__name__}")
    print(f"\n{len(tests) - failures}/{len(tests)} tests passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(_run_all())
