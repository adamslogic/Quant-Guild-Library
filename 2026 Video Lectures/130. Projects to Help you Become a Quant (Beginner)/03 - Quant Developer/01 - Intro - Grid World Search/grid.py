"""Grid model for the Grid World Search visualiser.

This module is the *graph* the search algorithms run on. It is deliberately
free of any pygame / rendering concerns so that:

* the algorithms in :mod:`algorithms` can be unit-tested headlessly, and
* the rendering layer in ``main.py`` can treat the grid as a pure data source.

A grid is a 4-connected lattice of cells. Each cell is addressed by an
``(row, col)`` tuple. A cell is either passable or a wall. Passable cells may
carry an optional integer *weight* (>= 1) representing terrain cost -- this is
what makes Dijkstra and A* interesting versus BFS/DFS.
"""

from __future__ import annotations

import random
from typing import Iterator

#: A cell coordinate: ``(row, col)``.
Cell = tuple[int, int]

#: 4-connected neighbourhood offsets (up, down, left, right).
#: Order chosen so DFS/BFS tie-breaking looks natural on screen.
_NEIGHBOUR_OFFSETS: tuple[Cell, ...] = ((-1, 0), (1, 0), (0, -1), (0, 1))


class Grid:
    """A 4-connected weighted grid graph.

    Parameters
    ----------
    rows, cols:
        Grid dimensions.
    start:
        Start cell; defaults to the top-left-ish corner.
    goal:
        Goal cell; defaults to the bottom-right-ish corner.
    """

    def __init__(
        self,
        rows: int = 25,
        cols: int = 25,
        start: Cell | None = None,
        goal: Cell | None = None,
    ) -> None:
        if rows < 2 or cols < 2:
            raise ValueError("grid must be at least 2x2")
        self.rows = rows
        self.cols = cols
        # Walls stored as a set of blocked cells (sparse; most cells are open).
        self.walls: set[Cell] = set()
        # Optional per-cell movement cost (default 1). Only entries != 1 stored.
        self._weights: dict[Cell, int] = {}
        self.start: Cell = start if start is not None else (1, 1)
        self.goal: Cell = goal if goal is not None else (rows - 2, cols - 2)

    # ------------------------------------------------------------------
    # Basic queries
    # ------------------------------------------------------------------
    def in_bounds(self, cell: Cell) -> bool:
        """Return ``True`` if ``cell`` lies inside the grid."""
        r, c = cell
        return 0 <= r < self.rows and 0 <= c < self.cols

    def is_wall(self, cell: Cell) -> bool:
        """Return ``True`` if ``cell`` is a wall."""
        return cell in self.walls

    def passable(self, cell: Cell) -> bool:
        """Return ``True`` if ``cell`` is inside the grid and not a wall."""
        return self.in_bounds(cell) and cell not in self.walls

    def cost(self, cell: Cell) -> int:
        """Movement cost of *entering* ``cell`` (>= 1). Defaults to 1."""
        return self._weights.get(cell, 1)

    def set_cost(self, cell: Cell, weight: int) -> None:
        """Set the terrain weight for ``cell`` (weight 1 removes the override)."""
        if weight < 1:
            raise ValueError("weights must be >= 1 (non-negative edge costs)")
        if weight == 1:
            self._weights.pop(cell, None)
        else:
            self._weights[cell] = weight

    def neighbors(self, cell: Cell) -> Iterator[Cell]:
        """Yield the passable 4-connected neighbours of ``cell``.

        This is the graph's *adjacency function* -- the single place the search
        algorithms use to discover edges. Keeping it here means the algorithms
        never need to know how walls or bounds are represented.
        """
        r, c = cell
        for dr, dc in _NEIGHBOUR_OFFSETS:
            nxt = (r + dr, c + dc)
            if self.passable(nxt):
                yield nxt

    # ------------------------------------------------------------------
    # Mutation helpers (used by the UI)
    # ------------------------------------------------------------------
    def toggle_wall(self, cell: Cell) -> None:
        """Toggle a wall at ``cell`` (start/goal cells can never be walls)."""
        if cell in (self.start, self.goal) or not self.in_bounds(cell):
            return
        if cell in self.walls:
            self.walls.discard(cell)
        else:
            self.walls.add(cell)

    def add_wall(self, cell: Cell) -> None:
        """Add a wall at ``cell`` unless it is the start/goal."""
        if cell in (self.start, self.goal) or not self.in_bounds(cell):
            return
        self.walls.add(cell)

    def remove_wall(self, cell: Cell) -> None:
        """Remove a wall at ``cell`` if present."""
        self.walls.discard(cell)

    def set_start(self, cell: Cell) -> None:
        """Move the start cell (clearing any wall / goal collision)."""
        if not self.in_bounds(cell) or cell == self.goal:
            return
        self.walls.discard(cell)
        self.start = cell

    def set_goal(self, cell: Cell) -> None:
        """Move the goal cell (clearing any wall / start collision)."""
        if not self.in_bounds(cell) or cell == self.start:
            return
        self.walls.discard(cell)
        self.goal = cell

    def clear_walls(self) -> None:
        """Remove all walls and terrain weights."""
        self.walls.clear()
        self._weights.clear()

    # ------------------------------------------------------------------
    # Maze / terrain generation
    # ------------------------------------------------------------------
    def generate_maze(self, rng: random.Random | None = None) -> None:
        """Carve a random maze using randomized depth-first search (recursive backtracker).

        The algorithm treats odd-indexed cells as "rooms" and the even cells
        between them as removable "walls between rooms". It produces a *perfect*
        maze (exactly one path between any two cells), which is a great stress
        test for the search algorithms because dead-ends abound.
        """
        rng = rng or random.Random()

        # Start from a full grid of walls, then carve passages.
        self.walls = {
            (r, c) for r in range(self.rows) for c in range(self.cols)
        }
        self._weights.clear()

        # Recursive backtracker can exceed Python's recursion limit on big grids,
        # so we run it iteratively with an explicit stack.
        start_r, start_c = 1, 1
        self.walls.discard((start_r, start_c))
        stack: list[Cell] = [(start_r, start_c)]
        while stack:
            r, c = stack[-1]
            dirs = [(-2, 0), (2, 0), (0, -2), (0, 2)]
            rng.shuffle(dirs)
            carved = False
            for dr, dc in dirs:
                nr, nc = r + dr, c + dc
                if 0 <= nr < self.rows and 0 <= nc < self.cols and (nr, nc) in self.walls:
                    self.walls.discard((r + dr // 2, c + dc // 2))
                    self.walls.discard((nr, nc))
                    stack.append((nr, nc))
                    carved = True
                    break
            if not carved:
                stack.pop()

        # Guarantee start and goal are open and reachable-looking.
        self.walls.discard(self.start)
        self.walls.discard(self.goal)
        # Open up the immediate neighbourhood of start/goal so they are usable
        # even if they landed on an even (wall) coordinate.
        for cell in (self.start, self.goal):
            r, c = cell
            for dr, dc in _NEIGHBOUR_OFFSETS:
                nb = (r + dr, c + dc)
                if self.in_bounds(nb):
                    self.walls.discard(nb)

    def scatter_weights(
        self, fraction: float = 0.15, max_weight: int = 5, rng: random.Random | None = None
    ) -> None:
        """Randomly assign terrain weights to a ``fraction`` of open cells.

        This makes the difference between BFS (ignores weight) and
        Dijkstra/A* (respect weight) visible.
        """
        rng = rng or random.Random()
        for r in range(self.rows):
            for c in range(self.cols):
                cell = (r, c)
                if cell in self.walls or cell in (self.start, self.goal):
                    continue
                if rng.random() < fraction:
                    self.set_cost(cell, rng.randint(2, max_weight))

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------
    def open_cells(self) -> int:
        """Number of passable cells (the effective ``|V|``)."""
        return self.rows * self.cols - len(self.walls)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return (
            f"Grid(rows={self.rows}, cols={self.cols}, "
            f"start={self.start}, goal={self.goal}, walls={len(self.walls)})"
        )
