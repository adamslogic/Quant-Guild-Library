# 130. Projects to Help you Become a Quant (by Role and Level)

A curated set of **9 hands-on projects** designed to build the specific skills each
quant role demands, laddered across three levels of difficulty. Each project is
self-contained: it has its own `README.md`, `requirements.txt`, and runnable code.

> The goal is not just to *use* these tools, but to *understand* the mathematics,
> data structures, and market microstructure underneath them.

---

## How the projects map to roles & levels

| Level | Quant Trader | Quant Researcher | Quant Developer |
|-------|--------------|------------------|-----------------|
| **Intro** | Trading Dashboard | Binomial Tree Pricer | Grid World Search |
| **Intermediate** | Market Making Simulator | PDE Solver | Order Book Simulator |
| **Advanced** | Algorithmic Trading System | Pricing Library | Latency & Cythonization |

### 01 — Quant Trader
Turning market views into risk-managed positions and P/L.

1. **Intro · Trading Dashboard** *(Flask + Plotly)* — Drop in a CSV of portfolio
   returns and get alpha/beta regressions, rolling Fama–French factor attribution,
   Sharpe, max drawdown, and more in a beautiful web dashboard.
2. **Intermediate · Market Making Simulator** *(Flask + animated Plotly)* — Make an
   options market when you *don't* know the true underlying dynamics. Pick a pricing
   model and a (different) market-path model and watch P/L evolve tick by tick.
3. **Advanced · Algorithmic Trading System** *(IBAPI + tkinter)* — A desktop trading
   cockpit: add strategies to a table with per-strategy parameters and on/off toggles,
   with live portfolio readouts (net liq, exposure, P/L).

### 02 — Quant Researcher
The pricing theory pipeline, from discrete trees to frontier rough-volatility research.

4. **Intro · Binomial Tree Pricer** *(Flask + Plotly)* — A visual guide to
   risk-neutral pricing: build the tree, watch it converge to Black–Scholes.
5. **Intermediate · PDE Solver** *(Flask + Plotly)* — Finite-difference solvers for a
   family of pricing PDEs (Black–Scholes, barriers, and more), validated against
   Monte Carlo.
6. **Advanced · Pricing Library** *(Flask + Plotly + LaTeX)* — Path signatures,
   model-free pricing, and Markovian lifting of rough volatility models, explained.

### 03 — Quant Developer
Data structures, algorithms, and performance — the engineering backbone.

7. **Intro · Grid World Search** *(pygame)* — Visualize BFS, DFS, Dijkstra, and A*
   with their theoretical time & space complexity.
8. **Intermediate · Order Book Simulator** *(tkinter)* — A price-time-priority
   matching engine built from first principles, visualized live.
9. **Advanced · Latency & Cythonization** — Benchmark algorithm latency and speed up
   a Monte Carlo pricing kernel with Cython, with a clear before/after comparison.

---

## Getting started

Each project directory is independent. To run one:

```bash
cd "<role>/<project>"
pip install -r requirements.txt
# then follow that project's README.md
```

Built for the [Quant Guild](https://quantguild.com) by Roman Paolucci.
