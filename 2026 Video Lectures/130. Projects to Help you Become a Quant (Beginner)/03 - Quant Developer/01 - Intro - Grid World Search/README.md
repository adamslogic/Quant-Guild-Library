# Grid World Search — Quant Developer · Intro

> **The DS&A starting point.** A `pygame` grid world that *visualises* the four
> classic graph-search algorithms — **BFS, DFS, Dijkstra, and A\*** — exploring a
> grid from a start cell to a goal, around walls and weighted terrain, while
> displaying each algorithm's **time and space complexity** and **live run
> statistics**.

Every quant developer lives and dies by data structures and algorithms: order
books are heaps and trees, routing is shortest-path, backtesting is graph
traversal over time. This project makes the foundations *visible* — you can
literally watch BFS expand in rings, DFS plunge down a corridor, Dijkstra creep
outward by cost, and A\* march straight at the goal.

---

## Quick start

```bash
cd "03 - Quant Developer/01 - Intro - Grid World Search"
pip install -r requirements.txt
python main.py
```

Then: pick an algorithm with keys **1–5**, press **SPACE**, and watch it search.

> **Python 3.13 / 3.14 note.** The classic `pygame` wheel may not exist yet for
> the newest interpreters, so `requirements.txt` installs **`pygame-ce`** (the
> community edition) there. It is a drop-in replacement — the code still does
> `import pygame`. Nothing else changes.

### Run the tests (no window needed)

```bash
python test_algorithms.py            # built-in runner
# or, if you have pytest:
python -m pytest test_algorithms.py -v
```

---

## Controls

| Input | Action |
|-------|--------|
| `1` `2` `3` `4` `5` | Select **BFS / DFS / Dijkstra / A\* / Greedy** |
| `SPACE` | Run / pause / resume the animated search |
| `R` | Reset the search (keep the grid) |
| `C` | Clear all walls & weights |
| `M` | Generate a random maze |
| `G` | Scatter random terrain weights |
| `W` | Toggle paint mode between **walls** and **weights** |
| `H` | Toggle A\*/Greedy heuristic (Manhattan ↔ Euclidean) |
| `↑` / `↓` | Faster / slower animation |
| Left-drag | Paint walls (or weights in weight mode) |
| Right-drag | Erase walls / weights |
| Drag **S** / **G** | Move the start / goal cell |

The right-hand panel always shows the selected algorithm's complexity, whether
it guarantees a shortest path, and live stats: **cells expanded**, **peak
frontier size**, **path length/cost**, and **wall-clock time**.

### What the colours mean

| Colour | Meaning |
|--------|---------|
| Green **S** / Red **G** | Start / Goal |
| Dark | Wall (impassable) |
| Teal | **Frontier** — the *open set*, cells queued but not yet expanded |
| Indigo | **Visited** — the *closed set*, cells already expanded |
| Gold | The final path the algorithm chose |
| Brown tint + number | Weighted terrain (cost to *enter* that cell) |

---

## The computer science

### Graph search in one paragraph

A grid is just a **graph** `G = (V, E)`: each open cell is a vertex, and edges
connect 4-connected neighbours. "Find a route from start to goal" is the
**single-source shortest-path** (or reachability) problem. Every algorithm here
is the *same loop* — *pop a cell from the frontier, expand its neighbours,
repeat* — and they differ in **one thing only: which cell they pop next**. That
single choice (the frontier's data structure) is what produces their wildly
different behaviour and complexity.

```
frontier ← {start}
while frontier not empty:
    current ← REMOVE-BEST(frontier)     # <-- the only difference between algorithms
    if current == goal: return path
    for nb in neighbours(current):
        if nb not seen: add nb to frontier, record parent
```

### The algorithms

| Algorithm | Frontier | Pops next | Optimal? | Time | Space |
|-----------|----------|-----------|:--------:|------|-------|
| **BFS** | FIFO queue | oldest | ✅ (unit weights) | `O(V + E)` | `O(V)` |
| **DFS** | LIFO stack | newest | ❌ | `O(V + E)` | `O(V)` |
| **Dijkstra** | min-heap on `g` | cheapest so far | ✅ (non-neg weights) | `O((V + E) log V)` | `O(V)` |
| **A\*** | min-heap on `g + h` | best `f` estimate | ✅ (admissible `h`) | `O(b^d)` worst | `O(b^d)` |
| **Greedy** | min-heap on `h` | closest-looking | ❌ | `O(b^m)` worst | `O(b^m)` |

- **BFS (breadth-first search).** Uses a **FIFO queue**, so it always expands the
  shallowest unexpanded cell. It visits everything at distance `k` before
  anything at distance `k+1`, which is exactly why the first time it touches the
  goal it has found a **shortest path in hops**. It expands in visible *rings*.

- **DFS (depth-first search).** Uses a **LIFO stack** (or recursion), so it dives
  as deep as possible down one branch before backtracking. It is **not optimal**
  — the path it returns is whatever it stumbled into. Great for reachability and
  cheap on memory along a single branch; useless for shortest paths.

- **Dijkstra's algorithm.** Generalises BFS to **non-negative edge weights**. A
  **min-priority queue** keyed on `g(n)` (cheapest cumulative cost from the
  start) always expands the closest-by-cost cell. Optimal for any non-negative
  weights. With a binary heap, `V` extract-mins and up to `E` pushes each cost
  `O(log V)`, giving `O((V + E) log V)`. Turn on terrain weights (`G`/`W`) to see
  it prefer cheap detours over short-but-costly straight lines.

- **A\* search.** Dijkstra **guided by a heuristic**. It orders the frontier by
  `f(n) = g(n) + h(n)` — cost so far plus an *estimate* of the cost remaining.
  With an **admissible** heuristic (one that never overestimates) A\* is
  **optimal**; with a **consistent** heuristic it never needs to reopen a closed
  cell. It is dramatically more goal-directed than Dijkstra: watch it expand a
  narrow cone toward the goal instead of a full disc.

- **Greedy best-first (optional).** Orders the frontier by `h(n)` **alone**,
  ignoring the cost already paid. Very fast and pointed straight at the goal, but
  **not optimal** — obstacles can lead it badly astray.

### Admissible & consistent heuristics

A heuristic `h(n)` estimates the remaining cost from `n` to the goal.

- **Admissible:** `h(n) ≤ true remaining cost` for every `n` (it never
  *overestimates*). Admissibility is what guarantees A\* returns an optimal path.
- **Consistent (monotone):** `h(n) ≤ cost(n, n') + h(n')` for every edge. This is
  stronger than admissibility and means `f` never decreases along a path, so a
  cell is never reopened once closed.

On a 4-connected grid with unit steps, **Manhattan distance** (`|Δrow| + |Δcol|`)
is both admissible and consistent — it is the exact distance with no walls, and
walls only make the true distance larger. **Euclidean distance** is also
admissible but *looser* (it under-estimates more), so A\* with Euclidean explores
a few more cells. Press `H` to compare them live.

### Why the grid simplifies the big-O

Textbook bounds are stated for general graphs. On a 4-connected grid every cell
has at most 4 neighbours, so `E = O(V)` — the graph is **sparse**. That collapses
`O(V + E)` to `O(V)` for BFS/DFS, and `O((V + E) log V)` to `O(V log V)` for
Dijkstra, *in practice*. We still quote the general bounds because reasoning
about them is the actual skill; the grid is just the thing you can watch.

### Reading the live stats

- **Expanded** — number of cells popped from the frontier (the search's *work*).
  Compare A\* vs Dijkstra on the same maze: A\* should expand fewer.
- **Frontier max** — the largest the open set ever got, a concrete proxy for the
  `O(V)` / `O(b^d)` **space** term.
- **Path length / cost** — the optimal searches (BFS on unit grids; Dijkstra & A\*
  on weighted grids) will agree; DFS and Greedy usually won't.
- **Time** — wall-clock milliseconds for the whole animated run.

---

## Project structure

```
01 - Intro - Grid World Search/
├── main.py              # pygame entry point & rendering (import-safe: no window on import)
├── algorithms.py        # BFS/DFS/Dijkstra/A*/Greedy as animatable generators (pure, testable)
├── grid.py              # the grid/graph model (walls, weights, neighbours, maze gen)
├── complexity.py        # complexity metadata + plain-English explanations
├── test_algorithms.py   # headless correctness tests (no pygame, no window)
├── requirements.txt
└── README.md
```

The design keeps a **hard wall between logic and rendering**:

- `algorithms.py`, `grid.py`, and `complexity.py` import **no pygame** and can be
  unit-tested headlessly.
- Each algorithm is a **generator** that `yield`s a `SearchState` snapshot per
  step. `main.py` pulls one (or several) snapshots per frame to animate; the
  tests drive the same generators to completion with `run_to_completion`.
- `main.py` imports `pygame` **inside** its functions, so `import main` never
  opens a window or even requires pygame to be installed.

### Extending it

- Add a new algorithm: write a generator in `algorithms.py` that yields
  `SearchState`, register it in `ALGORITHMS`, and add its metadata to
  `complexity.py`. It shows up in the UI automatically once you map a key.
- Try 8-connected movement, jump-point search, or bidirectional search.

---

Built for the [Quant Guild](https://quantguild.com) by Roman Paolucci.
