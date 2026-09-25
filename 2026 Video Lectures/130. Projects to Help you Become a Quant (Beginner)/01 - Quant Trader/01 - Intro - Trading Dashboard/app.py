"""
app.py
======

Flask front-end for the **Trading Dashboard**.

Flow
----
* ``GET  /``          -> landing page (drag-and-drop upload + "Load sample data").
* ``POST /analyze``   -> accepts an uploaded CSV *or* ``sample=true``, runs the
  full analysis in :mod:`analytics`, builds Plotly charts in :mod:`charts`, and
  renders the results dashboard.

All heavy lifting lives in :mod:`analytics` and :mod:`charts`; this file is just
the web plumbing (routing, request parsing, error handling, formatting).
"""

from __future__ import annotations

import os

from flask import Flask, render_template, request

import analytics
import charts

app = Flask(__name__)
# Cap uploads at 10 MB -- a daily return series is tiny; this blocks abuse.
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SAMPLE_CSV = os.path.join(BASE_DIR, "sample_portfolio_returns.csv")

# Windows over which a rolling analysis is meaningful (offered in the UI).
ALLOWED_WINDOWS = {21, 42, 63, 126, 252}
DEFAULT_WINDOW = 63


# ---------------------------------------------------------------------------
# Presentation helpers -- format raw floats into human-friendly strings.
# ---------------------------------------------------------------------------

def _pct(x: float, digits: int = 2) -> str:
    return "N/A" if x is None or (isinstance(x, float) and x != x) else f"{x * 100:.{digits}f}%"


def _num(x: float, digits: int = 2) -> str:
    return "N/A" if x is None or (isinstance(x, float) and x != x) else f"{x:.{digits}f}"


def _build_metric_cards(res: analytics.AnalysisResult) -> list[dict]:
    """Assemble the headline metric cards shown at the top of the dashboard."""
    p = res.perf_portfolio
    beta = res.capm.loading("Beta (Market)")
    return [
        {"label": "Annualized Alpha", "value": _pct(res.capm.alpha_annualized),
         "hint": "CAPM intercept vs SPY", "positive": res.capm.alpha_annualized >= 0},
        {"label": "Beta", "value": _num(beta.coef, 3),
         "hint": "Market exposure vs SPY", "positive": None},
        {"label": "Sharpe", "value": _num(p.sharpe),
         "hint": "Risk-adjusted return", "positive": p.sharpe >= 0},
        {"label": "Sortino", "value": _num(p.sortino),
         "hint": "Downside risk-adjusted", "positive": p.sortino >= 0},
        {"label": "CAGR", "value": _pct(p.cagr),
         "hint": "Annualized growth", "positive": p.cagr >= 0},
        {"label": "Volatility", "value": _pct(p.ann_vol),
         "hint": "Annualized std dev", "positive": None},
        {"label": "Max Drawdown", "value": _pct(p.max_drawdown),
         "hint": "Worst peak-to-trough", "positive": False},
        {"label": "R² (CAPM)", "value": _num(res.capm.r_squared, 3),
         "hint": "Variance explained by market", "positive": None},
    ]


def _build_factor_table(reg: analytics.RegressionResult) -> list[dict]:
    """Rows for the factor-loading table (one per coefficient)."""
    rows = []
    for l in reg.loadings:
        rows.append({
            "name": l.name,
            "coef": f"{l.coef:+.4f}",
            "annualized": _pct(l.annualized) if l.annualized is not None else "—",
            "tstat": _num(l.tstat),
            "pvalue": f"{l.pvalue:.3f}",
            "significant": l.significant,
            "description": analytics.FACTOR_DESCRIPTIONS.get(
                l.name, "Intercept (unexplained excess return)" if l.name == "Alpha" else ""),
        })
    return rows


def _run_and_render(returns, window: int, is_sample: bool = False):
    """Shared path: run analysis, build charts, render the dashboard template."""
    res = analytics.run_full_analysis(returns, window=window)
    chart_html = charts.build_all_charts(res)

    return render_template(
        "dashboard.html",
        is_sample=is_sample,
        cards=_build_metric_cards(res),
        chart_html=chart_html,
        ff5_rows=_build_factor_table(res.ff5),
        ff3_rows=_build_factor_table(res.ff3),
        capm_rows=_build_factor_table(res.capm),
        ff5_r2=res.ff5.r_squared,
        ff3_r2=res.ff3.r_squared,
        factor_source=res.factor_source,
        factor_is_synthetic=res.factor_is_synthetic,
        window=window,
        allowed_windows=sorted(ALLOWED_WINDOWS),
        n_obs=len(returns),
        start_date=returns.index.min().strftime("%Y-%m-%d"),
        end_date=returns.index.max().strftime("%Y-%m-%d"),
        spy_stats={
            "cagr": _pct(res.perf_spy.cagr),
            "vol": _pct(res.perf_spy.ann_vol),
            "sharpe": _num(res.perf_spy.sharpe),
            "mdd": _pct(res.perf_spy.max_drawdown),
        },
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html", sample_available=os.path.exists(SAMPLE_CSV))


@app.route("/analyze", methods=["POST"])
def analyze():
    # Parse the requested rolling window, falling back to the default.
    try:
        window = int(request.form.get("window", DEFAULT_WINDOW))
    except (TypeError, ValueError):
        window = DEFAULT_WINDOW
    if window not in ALLOWED_WINDOWS:
        window = DEFAULT_WINDOW

    use_sample = request.form.get("sample") == "true"

    try:
        if use_sample:
            if not os.path.exists(SAMPLE_CSV):
                raise FileNotFoundError("Sample data file is missing.")
            returns = analytics.load_returns(SAMPLE_CSV)
        else:
            file = request.files.get("file")
            if file is None or file.filename == "":
                return render_template(
                    "index.html", sample_available=os.path.exists(SAMPLE_CSV),
                    error="Please choose a CSV file or click 'Load sample data'."), 400
            returns = analytics.load_returns(file.read())

        return _run_and_render(returns, window, is_sample=use_sample)

    except Exception as exc:  # Surface a friendly message rather than a 500 trace.
        return render_template(
            "index.html", sample_available=os.path.exists(SAMPLE_CSV),
            error=f"Could not analyze that file: {exc}"), 400


if __name__ == "__main__":
    app.run(debug=True, port=5000)
