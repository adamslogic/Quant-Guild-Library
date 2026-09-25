"""Grid World Search -- an interactive pygame visualiser for graph search.

Run it::

    python main.py

What you see
------------
A grid on the left and an information panel on the right. Pick an algorithm,
press SPACE, and watch it explore. The colours tell the story:

* **frontier / open set**  -- cells queued but not yet expanded,
* **visited / closed set** -- cells already expanded,
* **path**                 -- the route the algorithm settled on,

plus the fixed start, goal and walls. The panel shows the selected algorithm's
theoretical **time** and **space** complexity, whether it guarantees the
shortest path, and **live** run statistics (cells expanded, path length, peak
frontier size, wall-clock time).

Design note
-----------
All rendering lives here; all algorithm logic lives in :mod:`algorithms`. pygame
is imported *inside* :func:`main` so that importing this module (e.g. for a smoke
test) never opens a window or requires pygame to be installed.
"""

from __future__ import annotations

import random
import sys
import time
from typing import Optional

import algorithms as A
import complexity as C
from grid import Cell, Grid

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
ROWS = 25
COLS = 25
CELL = 26            # pixel size of a grid cell
MARGIN = 16          # outer margin around the grid
PANEL_W = 400        # width of the right-hand information panel
# The information panel stacks several sections (complexity, live stats,
# legend, controls) and is taller than the grid. Size the window to whichever
# is taller so nothing is clipped off the bottom, then centre the grid in it.
MIN_WINDOW_H = 748
FPS = 60

# Speed presets: how many search steps to advance per rendered frame.
SPEED_LEVELS = [1, 2, 4, 8, 16, 32, 64]
DEFAULT_SPEED_IDX = 2

# ---------------------------------------------------------------------------
# Colour palette (R, G, B). Chosen for contrast and a calm, modern look.
# ---------------------------------------------------------------------------
COL_BG = (17, 22, 33)          # window background
COL_PANEL = (24, 31, 46)       # panel background
COL_GRID_LINE = (38, 47, 66)
COL_UNVISITED = (46, 57, 82)
COL_WALL = (12, 15, 23)
COL_FRONTIER = (46, 204, 164)   # teal-green (open set)
COL_VISITED = (86, 101, 176)    # muted indigo (closed set)
COL_PATH = (245, 197, 66)       # gold
COL_START = (63, 201, 96)       # green
COL_GOAL = (233, 78, 92)        # red
COL_CURRENT = (255, 255, 255)   # white flash for the just-expanded cell
COL_WEIGHT = (150, 110, 70)     # brown tint overlay for weighted terrain

COL_TEXT = (223, 230, 243)
COL_TEXT_DIM = (140, 152, 178)
COL_ACCENT = (245, 197, 66)
COL_GOOD = (63, 201, 96)
COL_BAD = (233, 78, 92)


class GridWorldApp:
    """Encapsulates the interactive visualiser state and pygame loop."""

    def __init__(self) -> None:
        import pygame  # local import: no window / dependency on module import

        self.pygame = pygame
        pygame.init()
        pygame.display.set_caption("Grid World Search - Quant Guild")

        self.grid = Grid(ROWS, COLS)
        self.width = MARGIN * 2 + COLS * CELL + PANEL_W
        self.height = max(MARGIN * 2 + ROWS * CELL, MIN_WINDOW_H)
        # Top-left of the grid; y is centred vertically when the window is taller
        # than the grid (i.e. when the panel is the limiting dimension).
        self.grid_x0 = MARGIN
        self.grid_y0 = (self.height - ROWS * CELL) // 2
        self.screen = pygame.display.set_mode((self.width, self.height))
        self.clock = pygame.time.Clock()

        self.font_sm = pygame.font.SysFont("consolas", 14)
        self.font_md = pygame.font.SysFont("consolas", 17)
        self.font_lg = pygame.font.SysFont("segoeui", 22, bold=True)
        self.font_xl = pygame.font.SysFont("segoeui", 28, bold=True)

        # Search / animation state.
        self.algo_key = "bfs"
        self.heuristic_name = "manhattan"
        self.speed_idx = DEFAULT_SPEED_IDX
        self.rng = random.Random()

        self._reset_search_state()

        # Interaction state.
        self.running_search = False
        self.paint_mode: Optional[str] = None  # 'wall', 'erase', 'start', 'goal', 'weight'
        self.weight_paint = False               # W toggles wall-paint vs weight-paint

    # ------------------------------------------------------------------
    # Search lifecycle
    # ------------------------------------------------------------------
    def _reset_search_state(self) -> None:
        """Clear any in-progress or finished search (keeps the grid/walls)."""
        self.gen = None
        self.frontier: list[Cell] = []
        self.visited: set[Cell] = set()
        self.current: Optional[Cell] = None
        self.path: list[Cell] = []
        self.done = False
        self.found = False
        self.expanded = 0
        self.frontier_max = 0
        self.wall_time = 0.0
        self._t_start = 0.0
        self.running_search = False

    def _heuristic(self):
        return A.manhattan if self.heuristic_name == "manhattan" else A.euclidean

    def _build_generator(self):
        """Instantiate the generator for the currently selected algorithm."""
        if self.algo_key == "astar":
            return A.astar(self.grid, heuristic=self._heuristic())
        if self.algo_key == "greedy":
            return A.greedy(self.grid, heuristic=self._heuristic())
        return A.make_search(self.algo_key, self.grid)

    def start_search(self) -> None:
        """(Re)start the animated search from scratch."""
        self._reset_search_state()
        self.gen = self._build_generator()
        self.running_search = True
        self._t_start = time.perf_counter()

    def toggle_run(self) -> None:
        """SPACE handler: start, pause, or resume."""
        if self.gen is None or self.done:
            self.start_search()
        else:
            self.running_search = not self.running_search
            if self.running_search:
                # resume: shift the clock so elapsed excludes the paused span
                self._t_start = time.perf_counter() - self.wall_time

    def _advance(self, steps: int) -> None:
        """Pull up to ``steps`` snapshots from the generator this frame."""
        if self.gen is None or self.done:
            return
        for _ in range(steps):
            try:
                state = next(self.gen)
            except StopIteration:
                self.done = True
                self.running_search = False
                break
            self.frontier = state.frontier
            self.visited = state.visited
            self.current = state.current
            self.expanded = state.expanded
            self.frontier_max = state.frontier_max
            if state.done:
                self.done = True
                self.found = state.found
                self.path = state.path or []
                self.running_search = False
                break
        self.wall_time = time.perf_counter() - self._t_start

    # ------------------------------------------------------------------
    # Coordinate helpers
    # ------------------------------------------------------------------
    def _cell_at(self, pos: tuple[int, int]) -> Optional[Cell]:
        """Convert a pixel position to a grid cell, or ``None`` if outside."""
        x, y = pos
        gx, gy = x - self.grid_x0, y - self.grid_y0
        if gx < 0 or gy < 0:
            return None
        c, r = gx // CELL, gy // CELL
        if 0 <= r < ROWS and 0 <= c < COLS:
            return (int(r), int(c))
        return None

    def _cell_rect(self, cell: Cell):
        r, c = cell
        return self.pygame.Rect(self.grid_x0 + c * CELL, self.grid_y0 + r * CELL, CELL, CELL)

    # ------------------------------------------------------------------
    # Event handling
    # ------------------------------------------------------------------
    def handle_event(self, event) -> bool:
        """Process one pygame event. Returns ``False`` to request quit."""
        pg = self.pygame
        if event.type == pg.QUIT:
            return False

        if event.type == pg.KEYDOWN:
            return self._handle_key(event)

        if event.type == pg.MOUSEBUTTONDOWN:
            self._handle_mouse_down(event)
        elif event.type == pg.MOUSEBUTTONUP:
            self.paint_mode = None
        elif event.type == pg.MOUSEMOTION and self.paint_mode:
            self._handle_mouse_drag(event)
        return True

    def _handle_key(self, event) -> bool:
        pg = self.pygame
        k = event.key
        keymap = {
            pg.K_1: "bfs", pg.K_2: "dfs", pg.K_3: "dijkstra",
            pg.K_4: "astar", pg.K_5: "greedy",
        }
        if k in keymap:
            self.algo_key = keymap[k]
            self._reset_search_state()
        elif k == pg.K_SPACE:
            self.toggle_run()
        elif k == pg.K_r:
            self._reset_search_state()
        elif k == pg.K_c:
            self.grid.clear_walls()
            self._reset_search_state()
        elif k == pg.K_m:
            self.grid.generate_maze(self.rng)
            self._reset_search_state()
        elif k == pg.K_g:
            self.grid.scatter_weights(rng=self.rng)
            self._reset_search_state()
        elif k == pg.K_w:
            self.weight_paint = not self.weight_paint
        elif k == pg.K_h:
            self.heuristic_name = (
                "euclidean" if self.heuristic_name == "manhattan" else "manhattan"
            )
            self._reset_search_state()
        elif k in (pg.K_UP, pg.K_EQUALS, pg.K_PLUS, pg.K_KP_PLUS):
            self.speed_idx = min(self.speed_idx + 1, len(SPEED_LEVELS) - 1)
        elif k in (pg.K_DOWN, pg.K_MINUS, pg.K_KP_MINUS):
            self.speed_idx = max(self.speed_idx - 1, 0)
        elif k == pg.K_ESCAPE:
            return False
        return True

    def _handle_mouse_down(self, event) -> None:
        cell = self._cell_at(event.pos)
        if cell is None:
            return
        # A fresh edit invalidates the current search visualisation.
        if self.gen is not None:
            self._reset_search_state()

        if cell == self.grid.start:
            self.paint_mode = "start"
        elif cell == self.grid.goal:
            self.paint_mode = "goal"
        elif event.button == 3:  # right-click erases
            self.paint_mode = "erase"
            self.grid.remove_wall(cell)
            self.grid.set_cost(cell, 1)
        elif self.weight_paint:
            self.paint_mode = "weight"
            self._paint_weight(cell)
        else:
            # Left click: paint walls, but toggle sense based on the first cell.
            if self.grid.is_wall(cell):
                self.paint_mode = "erase"
                self.grid.remove_wall(cell)
            else:
                self.paint_mode = "wall"
                self.grid.add_wall(cell)

    def _paint_weight(self, cell: Cell) -> None:
        if cell in (self.grid.start, self.grid.goal) or self.grid.is_wall(cell):
            return
        # Cycle 1 -> 3 -> 6 -> 9 -> 1 so repeated clicks build up terrain cost.
        cur = self.grid.cost(cell)
        nxt = {1: 3, 3: 6, 6: 9}.get(cur, 1)
        self.grid.set_cost(cell, nxt)

    def _handle_mouse_drag(self, event) -> None:
        cell = self._cell_at(event.pos)
        if cell is None:
            return
        mode = self.paint_mode
        if mode == "wall":
            self.grid.add_wall(cell)
        elif mode == "erase":
            self.grid.remove_wall(cell)
        elif mode == "start":
            self.grid.set_start(cell)
        elif mode == "goal":
            self.grid.set_goal(cell)
        elif mode == "weight":
            if self.grid.cost(cell) == 1:
                self._paint_weight(cell)

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------
    def draw(self) -> None:
        self.screen.fill(COL_BG)
        self._draw_grid()
        self._draw_panel()
        self.pygame.display.flip()

    def _blend(self, base, tint, alpha):
        return tuple(int(base[i] * (1 - alpha) + tint[i] * alpha) for i in range(3))

    def _draw_grid(self) -> None:
        pg = self.pygame
        frontier_set = set(self.frontier)
        path_set = set(self.path)

        for r in range(ROWS):
            for c in range(COLS):
                cell = (r, c)
                rect = self._cell_rect(cell)

                if self.grid.is_wall(cell):
                    color = COL_WALL
                elif cell in path_set:
                    color = COL_PATH
                elif cell in frontier_set:
                    color = COL_FRONTIER
                elif cell in self.visited:
                    color = COL_VISITED
                else:
                    color = COL_UNVISITED
                    w = self.grid.cost(cell)
                    if w > 1:
                        # tint unvisited weighted terrain toward brown
                        color = self._blend(color, COL_WEIGHT, min(0.6, 0.12 * w))

                pg.draw.rect(self.screen, color, rect)

                # weighted-cell cost label on open cells
                w = self.grid.cost(cell)
                if w > 1 and not self.grid.is_wall(cell) and cell not in (self.grid.start, self.grid.goal):
                    lbl = self.font_sm.render(str(w), True, COL_TEXT_DIM)
                    self.screen.blit(lbl, lbl.get_rect(center=rect.center))

                pg.draw.rect(self.screen, COL_GRID_LINE, rect, 1)

        # highlight the just-expanded cell
        if self.current and self.current not in (self.grid.start, self.grid.goal):
            pg.draw.rect(self.screen, COL_CURRENT, self._cell_rect(self.current), 2)

        # start & goal drawn last so they sit on top
        self._draw_marker(self.grid.start, COL_START, "S")
        self._draw_marker(self.grid.goal, COL_GOAL, "G")

    def _draw_marker(self, cell: Cell, color, letter: str) -> None:
        pg = self.pygame
        rect = self._cell_rect(cell)
        pg.draw.rect(self.screen, color, rect)
        pg.draw.rect(self.screen, COL_BG, rect, 2)
        lbl = self.font_md.render(letter, True, COL_BG)
        self.screen.blit(lbl, lbl.get_rect(center=rect.center))

    # ---- panel -------------------------------------------------------
    def _draw_panel(self) -> None:
        pg = self.pygame
        px = MARGIN * 2 + COLS * CELL
        panel = pg.Rect(px, 0, PANEL_W, self.height)
        pg.draw.rect(self.screen, COL_PANEL, panel)

        x = px + 20
        y = 18
        info = C.get(self.algo_key)

        # Title
        self.screen.blit(self.font_xl.render("Grid World Search", True, COL_TEXT), (x, y))
        y += 38

        # Selected algorithm
        self.screen.blit(self.font_lg.render(info.name, True, COL_ACCENT), (x, y))
        y += 28

        y = self._panel_kv(x, y, "Time", info.time)
        y = self._panel_kv(x, y, "Space", info.space)
        y = self._panel_kv(x, y, "Frontier", info.data_structure)
        opt_txt = "YES - shortest path" if info.optimal else "NO - may be suboptimal"
        opt_col = COL_GOOD if info.optimal else COL_BAD
        y = self._panel_kv(x, y, "Optimal", opt_txt, value_color=opt_col)
        if self.algo_key in ("astar", "greedy"):
            y = self._panel_kv(x, y, "Heuristic", self.heuristic_name)
        y += 6

        # summary text (wrapped)
        y = self._wrap_text(info.summary, x, y, PANEL_W - 40, self.font_sm, COL_TEXT_DIM)
        y += 12

        # Live stats box
        y = self._section(x, y, "LIVE RUN STATS")
        status = ("RUNNING" if self.running_search else
                  ("DONE - path found" if (self.done and self.found) else
                   ("DONE - no path" if self.done else "idle")))
        status_col = (COL_GOOD if self.running_search else
                      (COL_ACCENT if self.done and self.found else
                       (COL_BAD if self.done else COL_TEXT_DIM)))
        y = self._panel_kv(x, y, "Status", status, value_color=status_col)
        y = self._panel_kv(x, y, "Expanded", f"{self.expanded}")
        y = self._panel_kv(x, y, "Frontier max", f"{self.frontier_max}")
        path_len = f"{max(0, len(self.path) - 1)} steps" if self.path else "-"
        y = self._panel_kv(x, y, "Path length", path_len)
        if self.path:
            cost = A.path_cost(self.grid, self.path)
            y = self._panel_kv(x, y, "Path cost", f"{cost:g}")
        y = self._panel_kv(x, y, "Time", f"{self.wall_time * 1000:.1f} ms")
        y = self._panel_kv(x, y, "Open cells (V)", f"{self.grid.open_cells()}")
        y = self._panel_kv(x, y, "Speed", f"{SPEED_LEVELS[self.speed_idx]}x steps/frame")
        y += 8

        # Legend
        y = self._section(x, y, "LEGEND")
        y = self._legend_row(x, y, COL_START, "Start")
        y = self._legend_row(x, y, COL_GOAL, "Goal")
        y = self._legend_row(x, y, COL_WALL, "Wall")
        y = self._legend_row(x, y, COL_FRONTIER, "Frontier (open set)")
        y = self._legend_row(x, y, COL_VISITED, "Visited (closed set)")
        y = self._legend_row(x, y, COL_PATH, "Shortest path")
        y = self._legend_row(x, y, COL_WEIGHT, "Weighted terrain")
        y += 8

        # Controls (condensed so everything fits within the window)
        y = self._section(x, y, "CONTROLS")
        paint = "WEIGHT" if self.weight_paint else "WALL"
        controls = [
            "1-5  BFS / DFS / Dijkstra / A* / Greedy",
            "SPACE run/pause   R reset   C clear   M maze",
            f"G weights   W paint [{paint}]   H heuristic",
            "UP/DOWN speed   L-drag wall   R-drag erase",
            "drag S / G to move start / goal",
        ]
        for line in controls:
            self.screen.blit(self.font_sm.render(line, True, COL_TEXT_DIM), (x, y))
            y += 17

        # Bottom of the drawn panel content (used to verify it fits the window).
        self._panel_bottom = y

    def _panel_kv(self, x, y, key, value, value_color=COL_TEXT):
        self.screen.blit(self.font_sm.render(f"{key}", True, COL_TEXT_DIM), (x, y))
        self.screen.blit(self.font_md.render(str(value), True, value_color), (x + 120, y - 2))
        return y + 22

    def _section(self, x, y, title):
        self.screen.blit(self.font_sm.render(title, True, COL_ACCENT), (x, y))
        pg = self.pygame
        pg.draw.line(self.screen, COL_GRID_LINE, (x, y + 17), (x + PANEL_W - 40, y + 17), 1)
        return y + 24

    def _legend_row(self, x, y, color, label):
        pg = self.pygame
        pg.draw.rect(self.screen, color, pg.Rect(x, y + 2, 14, 14))
        pg.draw.rect(self.screen, COL_GRID_LINE, pg.Rect(x, y + 2, 14, 14), 1)
        self.screen.blit(self.font_sm.render(label, True, COL_TEXT), (x + 24, y))
        return y + 19

    def _wrap_text(self, text, x, y, max_w, font, color):
        words = text.split()
        line = ""
        for word in words:
            trial = f"{line} {word}".strip()
            if font.size(trial)[0] <= max_w:
                line = trial
            else:
                self.screen.blit(font.render(line, True, color), (x, y))
                y += 18
                line = word
        if line:
            self.screen.blit(font.render(line, True, color), (x, y))
            y += 18
        return y

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------
    def run(self) -> None:
        alive = True
        while alive:
            for event in self.pygame.event.get():
                alive = self.handle_event(event) and alive
            if self.running_search:
                self._advance(SPEED_LEVELS[self.speed_idx])
            self.draw()
            self.clock.tick(FPS)
        self.pygame.quit()


def main() -> None:
    """Entry point: create the app and run the loop."""
    app = GridWorldApp()
    app.run()


if __name__ == "__main__":
    # Guarded so that `import main` never opens a window (import-safe).
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
