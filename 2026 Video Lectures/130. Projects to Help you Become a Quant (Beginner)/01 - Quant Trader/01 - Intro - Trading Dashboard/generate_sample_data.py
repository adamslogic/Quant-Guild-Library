"""
generate_sample_data.py
========================

Creates a realistic ~3-year daily sample of portfolio and benchmark (SPY) returns
and writes it to ``sample_portfolio_returns.csv``.

Why a *simulated* dataset?
--------------------------
The dashboard needs to work out-of-the-box, offline, without asking the learner
to source their own returns file. We therefore simulate returns using a simple
one-factor market model, which is exactly the world that CAPM assumes:

    r_portfolio = alpha + beta * r_market + epsilon

* ``r_market`` (SPY) is drawn from a lognormal / GBM-style daily process with an
  annual drift of ~8% and annual volatility of ~16% -- broadly realistic for a
  broad US equity index.
* The portfolio is constructed to have a market **beta of ~1.1** (slightly more
  aggressive than the market) plus a small positive **alpha** (skill/edge) and
  idiosyncratic **noise** (diversifiable, stock-specific risk).

Because we *build in* a known alpha and beta, the analytics module should
recover values close to them -- a nice sanity check for learners.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Trading-day conventions used throughout the project.
TRADING_DAYS_PER_YEAR = 252


def generate_sample_returns(
    n_days: int = 756,           # ~3 years of trading days (3 * 252)
    start_date: str = "2023-01-03",
    market_mu_annual: float = 0.08,
    market_vol_annual: float = 0.16,
    portfolio_beta: float = 1.10,
    portfolio_alpha_annual: float = 0.02,   # ~2%/yr of skill-based excess return
    idiosyncratic_vol_annual: float = 0.08,
    seed: int = 75,
) -> pd.DataFrame:
    """Simulate daily SPY and portfolio simple returns via a one-factor model.

    Returns a DataFrame with columns ``date``, ``portfolio_return`` and ``SPY``.
    All returns are *simple* daily returns expressed as decimals.
    """
    rng = np.random.default_rng(seed)

    # Convert annualized parameters to their per-day equivalents. Drift scales
    # linearly with time; volatility scales with the square root of time.
    mkt_mu_daily = market_mu_annual / TRADING_DAYS_PER_YEAR
    mkt_vol_daily = market_vol_annual / np.sqrt(TRADING_DAYS_PER_YEAR)
    alpha_daily = portfolio_alpha_annual / TRADING_DAYS_PER_YEAR
    idio_vol_daily = idiosyncratic_vol_annual / np.sqrt(TRADING_DAYS_PER_YEAR)

    # Market (SPY) daily simple returns ~ Normal(mu, sigma). Using a normal for
    # daily *simple* returns is a standard, transparent teaching approximation.
    spy = rng.normal(loc=mkt_mu_daily, scale=mkt_vol_daily, size=n_days)

    # Portfolio via the market model: alpha + beta * market + idiosyncratic noise.
    epsilon = rng.normal(loc=0.0, scale=idio_vol_daily, size=n_days)
    portfolio = alpha_daily + portfolio_beta * spy + epsilon

    # Business-day calendar (Mon-Fri). This is a simplification -- it ignores
    # exchange holidays -- but is more than adequate for a teaching sample.
    dates = pd.bdate_range(start=start_date, periods=n_days)

    return pd.DataFrame(
        {
            "date": dates,
            "portfolio_return": np.round(portfolio, 6),
            "SPY": np.round(spy, 6),
        }
    )


def main() -> None:
    df = generate_sample_returns()
    out_path = "sample_portfolio_returns.csv"
    df.to_csv(out_path, index=False)
    print(f"Wrote {len(df)} rows to {out_path}")
    print(df.head())
    print(df.describe())


if __name__ == "__main__":
    main()
