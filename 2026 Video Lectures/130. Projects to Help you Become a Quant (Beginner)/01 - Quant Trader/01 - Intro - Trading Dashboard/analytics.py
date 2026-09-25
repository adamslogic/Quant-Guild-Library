"""
analytics.py
============

All of the quantitative machinery behind the Trading Dashboard, deliberately
kept separate from the Flask/plumbing code so it can be read, tested and reused
on its own.

The module answers four questions a quant trader always asks about a track
record:

1. **How did it perform?**  -> return, risk and risk-adjusted stats
   (CAGR, volatility, Sharpe, Sortino, max drawdown).
2. **Is there skill, or just market exposure?**  -> CAPM alpha & beta vs SPY.
3. **What is really driving the returns?**  -> Fama-French 3- and 5-factor
   regressions (value, size, profitability, investment, momentum-adjacent).
4. **Has the style drifted over time?**  -> rolling factor betas (attribution).

Everything is computed on *simple daily returns* (decimals, e.g. 0.001 = 0.1%).
"""

from __future__ import annotations

import io
import warnings
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd
import statsmodels.api as sm

TRADING_DAYS_PER_YEAR = 252


# ---------------------------------------------------------------------------
# 1. Input parsing / cleaning
# ---------------------------------------------------------------------------

# Accepted column-name variants (all compared case-insensitively / stripped).
# We are liberal in what we accept so learners don't have to fight the parser.
_PORTFOLIO_ALIASES = {
    "portfolio_return", "portfolio", "portfolio_returns", "port",
    "port_return", "returns", "return", "strategy", "strategy_return",
}
_SPY_ALIASES = {
    "spy", "spy_return", "spy_returns", "benchmark", "benchmark_return",
    "market", "market_return", "mkt",
}
_DATE_ALIASES = {"date", "dates", "datetime", "timestamp", "day"}


def _normalize(name: str) -> str:
    return str(name).strip().lower().replace(" ", "_")


def load_returns(source) -> pd.DataFrame:
    """Read and normalize an uploaded returns CSV.

    ``source`` may be a file path, a file-like object, or a raw bytes/str
    payload (as delivered by a Flask upload). The result is a tidy DataFrame
    indexed by a proper DatetimeIndex with exactly two columns:
    ``portfolio_return`` and ``SPY``.

    Robustness is intentional here: real users mis-name columns constantly, so
    we map a range of common aliases rather than demanding an exact schema.
    """
    if isinstance(source, bytes):
        source = io.BytesIO(source)
    elif isinstance(source, str) and ("\n" in source or "," in source):
        # Looks like raw CSV text rather than a path.
        source = io.StringIO(source)

    df = pd.read_csv(source)
    if df.empty:
        raise ValueError("The uploaded CSV appears to be empty.")

    # Build a lookup from normalized name -> original column name.
    lookup = {_normalize(c): c for c in df.columns}

    def _find(aliases: set[str], what: str) -> str:
        for alias in aliases:
            if alias in lookup:
                return lookup[alias]
        raise ValueError(
            f"Could not find a {what} column. Looked for any of: "
            f"{sorted(aliases)}. Found columns: {list(df.columns)}."
        )

    date_col = _find(_DATE_ALIASES, "date")
    port_col = _find(_PORTFOLIO_ALIASES, "portfolio return")
    spy_col = _find(_SPY_ALIASES, "SPY / benchmark return")

    out = pd.DataFrame(
        {
            "portfolio_return": pd.to_numeric(df[port_col], errors="coerce"),
            "SPY": pd.to_numeric(df[spy_col], errors="coerce"),
        }
    )
    out.index = pd.to_datetime(df[date_col], errors="coerce")
    out.index.name = "date"

    # Drop rows with unparseable dates or NaN returns, then sort chronologically.
    out = out[~out.index.isna()].dropna().sort_index()
    if len(out) < 30:
        raise ValueError(
            "Need at least ~30 valid daily observations to compute meaningful "
            f"statistics; only found {len(out)}."
        )

    # Guard against percent-encoded data (e.g. 1.5 meaning 1.5%). If the typical
    # absolute daily move is implausibly large for decimals, warn but proceed.
    if out[["portfolio_return", "SPY"]].abs().median().median() > 1.0:
        warnings.warn(
            "Returns look large for decimals -- did you upload percentages? "
            "Values are used as-is; divide by 100 if needed."
        )
    return out


# ---------------------------------------------------------------------------
# 2. Core performance statistics
# ---------------------------------------------------------------------------

def wealth_index(returns: pd.Series, initial: float = 1.0) -> pd.Series:
    """Cumulative growth of $1 (the equity curve / wealth index)."""
    return initial * (1.0 + returns).cumprod()


def drawdown_series(returns: pd.Series) -> pd.Series:
    """Percentage drawdown from the running peak (the 'underwater' curve)."""
    wealth = wealth_index(returns)
    running_peak = wealth.cummax()
    return wealth / running_peak - 1.0


def max_drawdown(returns: pd.Series) -> float:
    """Worst peak-to-trough decline (a negative number, e.g. -0.23)."""
    return float(drawdown_series(returns).min())


def annualized_return(returns: pd.Series) -> float:
    """CAGR implied by the realized cumulative return over the sample."""
    n = len(returns)
    if n == 0:
        return float("nan")
    total_growth = float((1.0 + returns).prod())
    years = n / TRADING_DAYS_PER_YEAR
    # Geometric annualization; handles the (rare) case of total wipeout safely.
    if total_growth <= 0:
        return -1.0
    return total_growth ** (1.0 / years) - 1.0


def annualized_volatility(returns: pd.Series) -> float:
    """Annualized standard deviation of daily returns (sqrt-of-time rule)."""
    return float(returns.std(ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR))


def sharpe_ratio(returns: pd.Series, rf_daily: float | pd.Series = 0.0) -> float:
    """Annualized Sharpe ratio: excess return per unit of total volatility."""
    excess = returns - rf_daily
    sd = excess.std(ddof=1)
    if sd == 0 or np.isnan(sd):
        return float("nan")
    return float(excess.mean() / sd * np.sqrt(TRADING_DAYS_PER_YEAR))


def sortino_ratio(returns: pd.Series, rf_daily: float | pd.Series = 0.0) -> float:
    """Annualized Sortino ratio.

    Like Sharpe, but penalizes only *downside* deviation -- volatility of
    negative excess returns -- because investors don't mind upside surprises.
    """
    excess = returns - rf_daily
    downside = excess[excess < 0]
    dd = downside.std(ddof=1)
    if dd == 0 or np.isnan(dd) or len(downside) == 0:
        return float("nan")
    return float(excess.mean() / dd * np.sqrt(TRADING_DAYS_PER_YEAR))


def rolling_sharpe(returns: pd.Series, window: int = 63,
                   rf_daily: float | pd.Series = 0.0) -> pd.Series:
    """Rolling annualized Sharpe over a trailing window (default ~1 quarter)."""
    excess = returns - rf_daily
    mean = excess.rolling(window).mean()
    std = excess.rolling(window).std(ddof=1)
    return (mean / std) * np.sqrt(TRADING_DAYS_PER_YEAR)


@dataclass
class PerformanceStats:
    total_return: float
    cagr: float
    ann_vol: float
    sharpe: float
    sortino: float
    max_drawdown: float

    def as_dict(self) -> dict:
        return {
            "total_return": self.total_return,
            "cagr": self.cagr,
            "ann_vol": self.ann_vol,
            "sharpe": self.sharpe,
            "sortino": self.sortino,
            "max_drawdown": self.max_drawdown,
        }


def performance_stats(returns: pd.Series,
                      rf_daily: float | pd.Series = 0.0) -> PerformanceStats:
    """Bundle the headline performance metrics for a return series."""
    return PerformanceStats(
        total_return=float((1.0 + returns).prod() - 1.0),
        cagr=annualized_return(returns),
        ann_vol=annualized_volatility(returns),
        sharpe=sharpe_ratio(returns, rf_daily),
        sortino=sortino_ratio(returns, rf_daily),
        max_drawdown=max_drawdown(returns),
    )


# ---------------------------------------------------------------------------
# 3. Regression helpers (CAPM + Fama-French share the same OLS engine)
# ---------------------------------------------------------------------------

@dataclass
class FactorLoading:
    name: str
    coef: float
    tstat: float
    pvalue: float
    annualized: Optional[float] = None   # only meaningful for the intercept

    @property
    def significant(self) -> bool:
        return self.pvalue < 0.05


@dataclass
class RegressionResult:
    """A tidy, template-friendly view of an OLS factor regression."""
    label: str
    loadings: list[FactorLoading]
    r_squared: float
    adj_r_squared: float
    nobs: int
    alpha_annualized: float = field(default=float("nan"))

    def loading(self, name: str) -> Optional[FactorLoading]:
        for l in self.loadings:
            if l.name.lower() == name.lower():
                return l
        return None


def _ols(y: pd.Series, X: pd.DataFrame, label: str) -> RegressionResult:
    """Run an OLS of ``y`` on ``X`` (a constant is added automatically).

    Alpha (the intercept) is annualized by multiplying the *daily* intercept by
    252 -- the standard convention for daily-frequency factor regressions.
    """
    X = sm.add_constant(X, has_constant="add")
    model = sm.OLS(y, X, missing="drop").fit()

    loadings: list[FactorLoading] = []
    for name in X.columns:
        coef = float(model.params[name])
        ann = coef * TRADING_DAYS_PER_YEAR if name == "const" else None
        loadings.append(
            FactorLoading(
                name="Alpha" if name == "const" else name,
                coef=coef,
                tstat=float(model.tvalues[name]),
                pvalue=float(model.pvalues[name]),
                annualized=ann,
            )
        )

    alpha_ann = float(model.params["const"] * TRADING_DAYS_PER_YEAR)
    return RegressionResult(
        label=label,
        loadings=loadings,
        r_squared=float(model.rsquared),
        adj_r_squared=float(model.rsquared_adj),
        nobs=int(model.nobs),
        alpha_annualized=alpha_ann,
    )


def capm_regression(portfolio: pd.Series, spy: pd.Series,
                    rf_daily: float | pd.Series = 0.0) -> RegressionResult:
    """CAPM regression of portfolio *excess* returns on market *excess* returns.

        (r_p - rf) = alpha + beta * (r_mkt - rf) + epsilon

    * **beta** measures market exposure (systematic risk). beta > 1 => more
      volatile than the market.
    * **alpha** is the average excess return *not* explained by market
      exposure -- the classic (if contested) proxy for manager skill.
    """
    y = (portfolio - rf_daily).rename("excess_portfolio")
    x = (spy - rf_daily).rename("MKT")
    data = pd.concat([y, x], axis=1).dropna()
    result = _ols(data["excess_portfolio"], data[["MKT"]], label="CAPM")
    # Rename the market loading to the more intuitive "Beta" for the UI.
    for l in result.loadings:
        if l.name == "MKT":
            l.name = "Beta (Market)"
    return result


# ---------------------------------------------------------------------------
# 4. Fama-French factors (with graceful offline fallbacks)
# ---------------------------------------------------------------------------

# The 5 Fama-French factors plus the risk-free rate. Descriptions are surfaced
# in the UI so learners understand what each loading means.
FF5_FACTORS = ["Mkt-RF", "SMB", "HML", "RMW", "CMA"]
FF3_FACTORS = ["Mkt-RF", "SMB", "HML"]

FACTOR_DESCRIPTIONS = {
    "Mkt-RF": "Market excess return (the equity market premium).",
    "SMB": "Small Minus Big: small-cap minus large-cap stock returns (size).",
    "HML": "High Minus Low: value minus growth stock returns (value).",
    "RMW": "Robust Minus Weak: high minus low profitability firms (profitability).",
    "CMA": "Conservative Minus Aggressive: low minus high investment firms (investment).",
    "RF": "Daily risk-free rate.",
}


@dataclass
class FactorData:
    """Container for a factor panel plus provenance for the UI banner."""
    factors: pd.DataFrame          # columns include the factors + 'RF' (decimals)
    source: str                    # human-readable provenance
    is_synthetic: bool = False


def _scale_ff_percent(df: pd.DataFrame) -> pd.DataFrame:
    """Fama-French data ships in *percent*; convert to decimals (÷100)."""
    return df / 100.0


def fetch_fama_french(start, end, five_factor: bool = True) -> FactorData:
    """Obtain daily Fama-French factors, trying three sources in order.

    1. ``getFamaFrenchFactors`` package (cleanest API).
    2. ``pandas_datareader`` hitting the Ken French data library directly.
    3. A clearly-labeled **synthetic** factor set so the app still runs with no
       internet at all. Synthetic factors are random but plausible, letting the
       whole pipeline execute end-to-end offline.

    ``start``/``end`` are timestamps used to align/trim the factor panel to the
    user's return series.
    """
    start = pd.Timestamp(start)
    end = pd.Timestamp(end)

    # --- Source 1: getFamaFrenchFactors -----------------------------------
    try:
        import getFamaFrenchFactors as gff  # type: ignore

        func = gff.famaFrench5Factor if five_factor else gff.famaFrench3Factor
        raw = func(frequency="d")
        # The package returns a 'date_ff_factors' column plus factor columns.
        raw = raw.rename(columns={"date_ff_factors": "date"})
        raw["date"] = pd.to_datetime(raw["date"])
        raw = raw.set_index("date").sort_index()
        # Package already returns decimals; standardize column names.
        raw = raw.rename(columns={"Mkt-RF": "Mkt-RF", "RF": "RF"})
        panel = raw.loc[(raw.index >= start) & (raw.index <= end)]
        if not panel.empty:
            return FactorData(panel, source="getFamaFrenchFactors (Ken French library)")
    except Exception:
        pass

    # --- Source 2: pandas_datareader --------------------------------------
    try:
        from pandas_datareader import data as pdr  # type: ignore

        name = ("F-F_Research_Data_5_Factors_2x3_daily" if five_factor
                else "F-F_Research_Data_Factors_daily")
        raw = pdr.DataReader(name, "famafrench", start, end)[0]
        raw.index = pd.to_datetime(raw.index.astype(str))
        panel = _scale_ff_percent(raw)
        if not panel.empty:
            return FactorData(panel, source="pandas_datareader (Ken French library)")
    except Exception:
        pass

    # --- Source 3: synthetic fallback -------------------------------------
    return _synthetic_factors(start, end, five_factor)


def _synthetic_factors(start, end, five_factor: bool) -> FactorData:
    """Generate a plausible, clearly-labeled synthetic factor panel.

    Used only when both live sources fail (e.g. no internet). The factors are
    independent Gaussian noise with realistic daily volatilities; they are NOT
    real market data and are flagged as synthetic throughout the UI.
    """
    rng = np.random.default_rng(7)
    dates = pd.bdate_range(start=start, end=end)
    cols = FF5_FACTORS if five_factor else FF3_FACTORS

    # Roughly realistic daily factor vols (annualized ~16% for Mkt-RF, less
    # for the long/short style factors which are largely market-neutral).
    daily_vols = {
        "Mkt-RF": 0.010, "SMB": 0.005, "HML": 0.005,
        "RMW": 0.004, "CMA": 0.004,
    }
    data = {c: rng.normal(0.0002 if c == "Mkt-RF" else 0.0,
                          daily_vols[c], size=len(dates)) for c in cols}
    data["RF"] = np.full(len(dates), 0.02 / TRADING_DAYS_PER_YEAR)  # ~2%/yr
    panel = pd.DataFrame(data, index=dates)
    panel.index.name = "date"
    return FactorData(panel, source="SYNTHETIC (offline fallback -- not real data)",
                      is_synthetic=True)


def fama_french_regression(portfolio: pd.Series, factor_data: FactorData,
                           factors: list[str]) -> RegressionResult:
    """Regress portfolio *excess* returns on a set of Fama-French factors.

        (r_p - RF) = alpha + sum_i beta_i * Factor_i + epsilon

    Each beta_i is the portfolio's loading (exposure) to that style factor.
    A positive, significant HML loading, for example, means the strategy
    behaves like a value strategy.
    """
    df = factor_data.factors
    merged = pd.concat([portfolio.rename("portfolio"), df], axis=1, join="inner").dropna()
    if len(merged) < 30:
        raise ValueError(
            "Too few overlapping dates between returns and factors "
            f"({len(merged)}) to run the factor regression."
        )
    excess = merged["portfolio"] - merged["RF"]
    label = f"Fama-French {len(factors)}-Factor"
    return _ols(excess, merged[factors], label=label)


def rolling_factor_betas(portfolio: pd.Series, factor_data: FactorData,
                         factors: list[str], window: int = 63) -> pd.DataFrame:
    """Rolling-window OLS betas to each factor -- the attribution time series.

    For each trailing ``window`` (default 63 trading days ~ one quarter) we
    re-estimate the factor loadings. Plotting these over time reveals **style
    drift**: whether the strategy's exposures are stable or wandering.
    """
    df = factor_data.factors
    merged = pd.concat([portfolio.rename("portfolio"), df], axis=1, join="inner").dropna()
    excess = merged["portfolio"] - merged["RF"]
    X = sm.add_constant(merged[factors], has_constant="add")

    idx = merged.index
    records = []
    for i in range(window, len(merged) + 1):
        sl = slice(i - window, i)
        y_win = excess.iloc[sl]
        x_win = X.iloc[sl]
        try:
            betas = sm.OLS(y_win, x_win).fit().params
        except Exception:
            continue
        row = {f: float(betas.get(f, np.nan)) for f in factors}
        records.append((idx[i - 1], row))

    if not records:
        return pd.DataFrame(columns=factors)
    out = pd.DataFrame([r for _, r in records], index=[d for d, _ in records])
    out.index.name = "date"
    return out


# ---------------------------------------------------------------------------
# 5. Top-level orchestration
# ---------------------------------------------------------------------------

@dataclass
class AnalysisResult:
    """Everything the dashboard needs, computed once from a returns frame."""
    returns: pd.DataFrame
    rf_daily: pd.Series
    perf_portfolio: PerformanceStats
    perf_spy: PerformanceStats
    capm: RegressionResult
    ff5: RegressionResult
    ff3: RegressionResult
    rolling_betas: pd.DataFrame
    rolling_sharpe: pd.Series
    factor_source: str
    factor_is_synthetic: bool
    window: int


def run_full_analysis(returns: pd.DataFrame, window: int = 63) -> AnalysisResult:
    """Compute the complete analysis bundle from a cleaned returns frame.

    This is the single entry point the Flask app calls. It wires together the
    performance stats, CAPM, Fama-French 3/5-factor regressions and rolling
    attribution, sharing one aligned risk-free-rate series throughout.
    """
    portfolio = returns["portfolio_return"]
    spy = returns["SPY"]

    # Pull factors first so we can borrow the FF risk-free rate for Sharpe etc.
    factor_data = fetch_fama_french(returns.index.min(), returns.index.max(),
                                    five_factor=True)

    # Align RF to our return dates; fall back to 0 where unavailable.
    rf_daily = factor_data.factors.get("RF")
    if rf_daily is not None:
        rf_daily = rf_daily.reindex(returns.index).ffill().fillna(0.0)
    else:
        rf_daily = pd.Series(0.0, index=returns.index)

    perf_portfolio = performance_stats(portfolio, rf_daily)
    perf_spy = performance_stats(spy, rf_daily)
    capm = capm_regression(portfolio, spy, rf_daily)

    ff5 = fama_french_regression(portfolio, factor_data, FF5_FACTORS)

    # For the 3-factor model, reuse a 5-factor panel (it already contains the
    # 3-factor columns) so we don't hit the network twice.
    ff3 = fama_french_regression(portfolio, factor_data, FF3_FACTORS)

    rolling_betas = rolling_factor_betas(portfolio, factor_data, FF5_FACTORS, window)
    roll_sharpe = rolling_sharpe(portfolio, window, rf_daily)

    return AnalysisResult(
        returns=returns,
        rf_daily=rf_daily,
        perf_portfolio=perf_portfolio,
        perf_spy=perf_spy,
        capm=capm,
        ff5=ff5,
        ff3=ff3,
        rolling_betas=rolling_betas,
        rolling_sharpe=roll_sharpe,
        factor_source=factor_data.source,
        factor_is_synthetic=factor_data.is_synthetic,
        window=window,
    )


if __name__ == "__main__":
    # Headless smoke test: run the full pipeline on the bundled sample CSV.
    import os

    here = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(here, "sample_portfolio_returns.csv")
    rets = load_returns(csv_path)
    res = run_full_analysis(rets, window=63)

    print(f"Loaded {len(rets)} rows from {csv_path}")
    print(f"Factor source: {res.factor_source} (synthetic={res.factor_is_synthetic})")
    print("\n-- Portfolio performance --")
    for k, v in res.perf_portfolio.as_dict().items():
        print(f"  {k:>14}: {v: .4f}")
    print("\n-- CAPM --")
    beta = res.capm.loading("Beta (Market)")
    print(f"  Annualized alpha: {res.capm.alpha_annualized: .4%}")
    print(f"  Beta:             {beta.coef: .3f} (t={beta.tstat:.2f})")
    print(f"  R^2:              {res.capm.r_squared: .3f}")
    print("\n-- Fama-French 5-Factor loadings --")
    for l in res.ff5.loadings:
        print(f"  {l.name:>14}: {l.coef: .4f}  t={l.tstat: .2f}  p={l.pvalue:.3f}")
    print(f"\n  FF5 R^2: {res.ff5.r_squared:.3f}")
    print(f"  Rolling betas shape: {res.rolling_betas.shape}")
