"""
charts.py
=========

Turns the numbers produced by :mod:`analytics` into beautiful, interactive
Plotly figures rendered as self-contained HTML fragments for the dashboard.

Design notes
------------
* A single shared dark "Quant Guild terminal" theme keeps every chart visually
  consistent with the surrounding UI.
* Each ``build_*`` function returns an HTML *fragment* (``full_html=False``)
  with ``include_plotlyjs=False`` -- Plotly's JS is loaded once from a CDN in
  the base template, which keeps the page lightweight.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from analytics import AnalysisResult, wealth_index, drawdown_series

# Brand palette for the dark terminal aesthetic.
_ACCENT = "#4ade80"      # portfolio (green)
_ACCENT_2 = "#60a5fa"    # benchmark (blue)
_DANGER = "#f87171"      # drawdowns (red)
_GRID = "rgba(148,163,184,0.12)"
_PAPER = "rgba(0,0,0,0)"
_FONT = "Inter, 'Segoe UI', system-ui, sans-serif"

# Distinct colors for the five Fama-French factor beta lines.
_FACTOR_COLORS = {
    "Mkt-RF": "#60a5fa",
    "SMB": "#4ade80",
    "HML": "#fbbf24",
    "RMW": "#c084fc",
    "CMA": "#f472b6",
}

_CONFIG = {"displayModeBar": False, "responsive": True}


def _base_layout(title: str, height: int = 340) -> dict:
    """Shared layout options giving every chart the same dark styling."""
    return dict(
        title=dict(text=title, font=dict(size=15, color="#e2e8f0"), x=0.01, xanchor="left"),
        template="plotly_dark",
        paper_bgcolor=_PAPER,
        plot_bgcolor=_PAPER,
        font=dict(family=_FONT, color="#94a3b8", size=12),
        margin=dict(l=50, r=20, t=44, b=40),
        height=height,
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="right", x=1.0,
                    bgcolor=_PAPER, font=dict(size=11)),
        xaxis=dict(gridcolor=_GRID, zeroline=False),
        yaxis=dict(gridcolor=_GRID, zeroline=False),
    )


def _to_html(fig: go.Figure, div_id: str) -> str:
    return fig.to_html(full_html=False, include_plotlyjs=False,
                       config=_CONFIG, div_id=div_id)


def build_equity_curve(res: AnalysisResult) -> str:
    """Wealth index (growth of $1) for the portfolio vs SPY."""
    port = wealth_index(res.returns["portfolio_return"])
    spy = wealth_index(res.returns["SPY"])

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=port.index, y=port.values, name="Portfolio", mode="lines",
        line=dict(color=_ACCENT, width=2.2),
        fill="tozeroy", fillcolor="rgba(74,222,128,0.08)"))
    fig.add_trace(go.Scatter(
        x=spy.index, y=spy.values, name="SPY", mode="lines",
        line=dict(color=_ACCENT_2, width=1.8, dash="dot")))
    fig.update_layout(**_base_layout("Equity Curve — Growth of $1"))
    fig.update_yaxes(tickprefix="$")
    return _to_html(fig, "chart-equity")


def build_drawdown(res: AnalysisResult) -> str:
    """Underwater curve: percentage drawdown from the running peak."""
    dd = drawdown_series(res.returns["portfolio_return"]) * 100.0

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=dd.index, y=dd.values, name="Drawdown", mode="lines",
        line=dict(color=_DANGER, width=1.4),
        fill="tozeroy", fillcolor="rgba(248,113,113,0.20)"))
    fig.update_layout(**_base_layout("Underwater Plot — Drawdown from Peak"))
    fig.update_yaxes(ticksuffix="%")
    return _to_html(fig, "chart-drawdown")


def build_rolling_sharpe(res: AnalysisResult) -> str:
    """Rolling annualized Sharpe ratio over the selected window."""
    rs = res.rolling_sharpe.dropna()

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=rs.index, y=rs.values, name="Rolling Sharpe", mode="lines",
        line=dict(color="#fbbf24", width=1.8),
        fill="tozeroy", fillcolor="rgba(251,191,36,0.08)"))
    # Reference line at Sharpe = 1, a common "good" threshold.
    fig.add_hline(y=1.0, line=dict(color="rgba(148,163,184,0.5)", width=1, dash="dash"))
    fig.update_layout(**_base_layout(f"Rolling Sharpe Ratio ({res.window}-day window)"))
    return _to_html(fig, "chart-rollsharpe")


def build_rolling_attribution(res: AnalysisResult) -> str:
    """Rolling factor betas over time -- the style-attribution chart."""
    betas = res.rolling_betas
    fig = go.Figure()
    if not betas.empty:
        for col in betas.columns:
            fig.add_trace(go.Scatter(
                x=betas.index, y=betas[col], name=col, mode="lines",
                line=dict(color=_FACTOR_COLORS.get(col, "#94a3b8"), width=1.8),
                stackgroup=None))
    fig.add_hline(y=0.0, line=dict(color="rgba(148,163,184,0.4)", width=1))
    fig.update_layout(**_base_layout(
        f"Rolling Fama-French Factor Betas ({res.window}-day window)", height=380))
    return _to_html(fig, "chart-attribution")


def build_factor_loadings_bar(res: AnalysisResult) -> str:
    """Bar chart of the FF5 factor loadings, colored by statistical significance."""
    loadings = [l for l in res.ff5.loadings if l.name != "Alpha"]
    names = [l.name for l in loadings]
    coefs = [l.coef for l in loadings]
    # Significant loadings are solid; insignificant ones are muted/translucent.
    colors = [_FACTOR_COLORS.get(n, "#94a3b8") for n in names]
    opacity = [1.0 if l.significant else 0.35 for l in loadings]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=names, y=coefs, marker=dict(color=colors, opacity=opacity),
        text=[f"{c:+.2f}" for c in coefs], textposition="outside",
        hovertext=[f"t={l.tstat:.2f}, p={l.pvalue:.3f}" for l in loadings]))
    fig.add_hline(y=0.0, line=dict(color="rgba(148,163,184,0.4)", width=1))
    fig.update_layout(**_base_layout("Fama-French 5-Factor Loadings (β)"))
    return _to_html(fig, "chart-loadings")


def build_all_charts(res: AnalysisResult) -> dict[str, str]:
    """Convenience wrapper returning every chart fragment keyed by name."""
    return {
        "equity": build_equity_curve(res),
        "drawdown": build_drawdown(res),
        "rolling_sharpe": build_rolling_sharpe(res),
        "attribution": build_rolling_attribution(res),
        "loadings": build_factor_loadings_bar(res),
    }
