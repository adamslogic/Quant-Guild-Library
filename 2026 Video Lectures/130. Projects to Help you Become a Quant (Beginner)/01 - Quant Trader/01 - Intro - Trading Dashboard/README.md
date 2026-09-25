# Trading Dashboard — Portfolio Performance & Factor Analysis

> **Quant Trader · Intro level** — a self-contained teaching project from the Quant Guild library.

Upload a CSV of daily portfolio returns and instantly get a full **quant
tearsheet**: CAPM alpha & beta, Fama-French 3- and 5-factor regressions,
rolling factor attribution, and a complete performance / risk breakdown against
SPY — all rendered as a beautiful, interactive dark "Quant Guild terminal" dashboard
built with Flask and Plotly.

The app runs **out-of-the-box, offline**: it ships with realistic sample data
and gracefully falls back to synthetic factors if it can't reach the internet.

---

## Quick start

```bash
# 1. (optional) create a virtual environment
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# macOS / Linux:
# source .venv/bin/activate

# 2. install dependencies
pip install -r requirements.txt

# 3. (optional) regenerate the bundled sample CSV
python generate_sample_data.py

# 4. run the app
python app.py
```

Then open <http://127.0.0.1:5000> in your browser. Click **“Load sample data”**
to see the dashboard immediately, or drag-and-drop your own CSV.

To sanity-check the math without the web server:

```bash
python analytics.py     # runs the full pipeline on the sample CSV and prints results
```

---

## The CSV format

A `date` column plus daily **simple** returns (decimals, e.g. `0.001` = 0.1%):

```csv
date,portfolio_return,SPY
2023-01-03,-0.0008,0.0034
2023-01-04,-0.0068,-0.0102
2023-01-05,0.0120,0.0079
```

Column names are matched **flexibly** and case-insensitively:

| Concept          | Accepted names (any of)                                              |
|------------------|----------------------------------------------------------------------|
| Date             | `date`, `dates`, `datetime`, `timestamp`, `day`                      |
| Portfolio return | `portfolio_return`, `portfolio`, `returns`, `strategy`, ...          |
| Benchmark return | `SPY`, `spy`, `spy_return`, `benchmark`, `market`, `mkt`, ...        |

---

## The finance, explained

This project is built to *teach*, so here is the intuition behind every number
on the dashboard.

### CAPM: alpha and beta

The **Capital Asset Pricing Model** says a portfolio's excess return should be
explained by its exposure to the overall market. We estimate it by OLS
regression:

$$ (r_p - r_f) = \alpha + \beta\,(r_m - r_f) + \varepsilon $$

- **Beta (β)** — sensitivity to the market. β = 1 moves with the market,
  β = 1.1 is 10% more volatile, β < 1 is defensive. It measures *systematic*
  (undiversifiable) risk.
- **Alpha (α)** — average return *above* what beta-driven market exposure
  explains. Positive, statistically significant alpha is the classic (if
  hotly debated) signature of **skill**. We annualize the daily intercept by
  multiplying by 252.
- **R²** — the fraction of the portfolio's variance explained by the market.

### Fama-French factor models

CAPM's single market factor is famously incomplete. **Fama-French** adds
systematic style factors that historically earn premia. We run both the
3-factor and 5-factor regressions of excess returns:

$$ (r_p - r_f) = \alpha + \sum_i \beta_i\,F_i + \varepsilon $$

| Factor    | Meaning                                                                 |
|-----------|-------------------------------------------------------------------------|
| **Mkt-RF**| Market excess return (the equity risk premium).                         |
| **SMB**   | *Small Minus Big* — small-cap minus large-cap (the **size** factor).    |
| **HML**   | *High Minus Low* — value minus growth (the **value** factor).           |
| **RMW**   | *Robust Minus Weak* — high minus low profitability.                     |
| **CMA**   | *Conservative Minus Aggressive* — low minus high investment.            |

The **factor loadings (βᵢ)** tell you what kind of strategy this really is: a
large positive HML loading behaves like a value strategy, a positive SMB
loading tilts small-cap, and so on. A loading is flagged significant when its
p-value < 0.05.

### Rolling factor attribution (style drift)

Factor exposures aren't static. We re-estimate the factor betas over a moving
window (default **63 trading days ≈ one quarter**) and plot them through time.
Wandering lines reveal **style drift** — the strategy quietly changing its bets.

### Performance & risk statistics

- **Total return / CAGR** — cumulative and annualized (geometric) growth.
- **Annualized volatility** — standard deviation of daily returns scaled by
  √252 (the square-root-of-time rule).
- **Sharpe ratio** — annualized excess return per unit of *total* volatility.
  Rf comes from the Fama-French RF series (or 0 if unavailable).
- **Sortino ratio** — like Sharpe, but only penalizes *downside* volatility,
  since investors don't fear upside surprises.
- **Maximum drawdown (MDD)** — the worst peak-to-trough decline. The
  **underwater plot** shows how deep and how long every drawdown was.
- **Equity curve** — the wealth index (growth of \$1), portfolio vs SPY.
- **Rolling Sharpe** — how the risk-adjusted return has evolved over time.

---

## Where the factor data comes from

On each analysis the app tries three sources, in order:

1. **`getFamaFrenchFactors`** — cleanest API to Ken French's data library.
2. **`pandas_datareader`** — pulls the same data directly from the library.
3. **Synthetic fallback** — if there's no internet, a clearly-labeled random
   (but plausible) factor panel so the whole pipeline still runs. When this
   happens the dashboard shows a prominent warning banner.

---

## Project structure

```
.
├── app.py                       # Flask web app (routes, request handling, formatting)
├── analytics.py                 # All quant math: parsing, stats, CAPM, Fama-French, rolling betas
├── charts.py                    # Plotly figure builders (dark theme)
├── generate_sample_data.py      # Simulates the bundled sample returns
├── sample_portfolio_returns.csv # ~3 years of daily portfolio + SPY returns
├── requirements.txt
├── templates/                   # Jinja2 HTML (base, landing, dashboard)
└── static/                      # CSS + JS (drag-and-drop upload)
```

### About the sample data

`sample_portfolio_returns.csv` is simulated with a one-factor market model —
exactly the world CAPM assumes:

$$ r_p = \alpha + \beta\,r_{SPY} + \varepsilon $$

SPY is drawn with ≈8%/yr drift and ≈16%/yr volatility; the portfolio is built
with a **beta of ~1.1**, a small positive alpha, and idiosyncratic noise. Because
these values are baked in, the CAPM regression should *recover* a beta near 1.1
and a positive alpha — a satisfying sanity check.

> **Disclaimer:** This is an educational project. Nothing here is investment
> advice, and the sample data is simulated, not real market history.
