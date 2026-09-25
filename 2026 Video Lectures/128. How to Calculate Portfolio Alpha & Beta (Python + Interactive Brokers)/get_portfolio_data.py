from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
from ibapi.client import EClient
from ibapi.contract import Contract
from ibapi.wrapper import EWrapper


# -----------------------------
# Configuration
# -----------------------------
HOST = "127.0.0.1"
PORT = 7497          # 7497 is commonly paper TWS; use your configured socket port
CLIENT_ID = 17       # Must be unique among connected API clients

DURATION = "10 Y"
BAR_SIZE = "1 day"
WHAT_TO_SHOW = "ADJUSTED_LAST"  # Total-return-like stock history: splits + dividends
USE_RTH = 1

CONNECT_TIMEOUT = 20
POSITIONS_TIMEOUT = 40
HISTORICAL_TIMEOUT = 120
REQUEST_PAUSE_SECONDS = 0.25

TRADING_DAYS_PER_YEAR = 252


@dataclass
class PositionRecord:
    account: str
    symbol: str
    con_id: int
    sec_type: str
    currency: str
    exchange: str
    primary_exchange: str
    multiplier: float
    quantity: float
    avg_cost: float


class IBKRPortfolioApp(EWrapper, EClient):
    """Small synchronous facade around IBKR's callback-driven API."""

    BENIGN_ERROR_CODES = {2104, 2106, 2158}
    HISTORICAL_FATAL_CODES = {
        162, 165, 166, 200, 321, 354, 366, 420, 10167, 10168
    }

    def __init__(self) -> None:
        EClient.__init__(self, self)

        self.api_ready = threading.Event()
        self.positions_complete = threading.Event()
        self.connection_closed = threading.Event()

        self._lock = threading.Lock()
        self._raw_positions: List[PositionRecord] = []
        self._historical_data: Dict[int, List[Tuple[str, float]]] = {}
        self._historical_events: Dict[int, threading.Event] = {}
        self._historical_errors: Dict[int, str] = {}
        self._req_id_to_label: Dict[int, str] = {}
        self._error_log: List[str] = []

    # ---------- Connection callbacks ----------

    def nextValidId(self, orderId: int) -> None:
        self.api_ready.set()

    def connectionClosed(self) -> None:
        self.connection_closed.set()

    # Compatible with both pre-10.33 and 10.33+ Python API error signatures.
    def error(self, reqId: int, *args) -> None:
        error_time: Optional[int] = None
        advanced = ""

        # Newer signature:
        # error(reqId, errorTime, errorCode, errorString, advancedOrderRejectJson)
        if len(args) >= 3 and isinstance(args[1], int):
            error_time = int(args[0])
            error_code = int(args[1])
            error_string = str(args[2])
            if len(args) >= 4:
                advanced = str(args[3] or "")
        # Older signature:
        # error(reqId, errorCode, errorString, advancedOrderRejectJson="")
        elif len(args) >= 2:
            error_code = int(args[0])
            error_string = str(args[1])
            if len(args) >= 3:
                advanced = str(args[2] or "")
        else:
            print(f"IBKR error callback with unexpected arguments: reqId={reqId}, args={args}")
            return

        if error_code in self.BENIGN_ERROR_CODES:
            return

        timestamp_text = f", time={error_time}" if error_time is not None else ""
        advanced_text = f", details={advanced}" if advanced else ""
        message = (
            f"IBKR ERROR reqId={reqId}{timestamp_text}, code={error_code}: "
            f"{error_string}{advanced_text}"
        )
        print(message)

        with self._lock:
            self._error_log.append(message)
            if reqId in self._historical_events and error_code in self.HISTORICAL_FATAL_CODES:
                self._historical_errors[reqId] = message
                self._historical_events[reqId].set()

    # ---------- Position callbacks ----------

    def position(self, account, contract, pos, avgCost) -> None:
        quantity = float(pos)
        if quantity == 0:
            return

        multiplier_text = getattr(contract, "multiplier", "") or "1"
        try:
            multiplier = float(multiplier_text)
        except (TypeError, ValueError):
            multiplier = 1.0

        record = PositionRecord(
            account=str(account),
            symbol=str(contract.symbol),
            con_id=int(contract.conId),
            sec_type=str(contract.secType),
            currency=str(contract.currency or "USD"),
            exchange=str(contract.exchange or ""),
            primary_exchange=str(getattr(contract, "primaryExchange", "") or ""),
            multiplier=multiplier,
            quantity=quantity,
            avg_cost=float(avgCost),
        )

        with self._lock:
            self._raw_positions.append(record)

    def positionEnd(self) -> None:
        self.positions_complete.set()

    # ---------- Historical-data callbacks ----------

    def historicalData(self, reqId, bar) -> None:
        with self._lock:
            self._historical_data.setdefault(reqId, []).append(
                (str(bar.date), float(bar.close))
            )

    def historicalDataEnd(self, reqId: int, start: str, end: str) -> None:
        label = self._req_id_to_label.get(reqId, str(reqId))
        with self._lock:
            count = len(self._historical_data.get(reqId, []))
        print(f"  Completed {label}: {count:,} daily bars")

        event = self._historical_events.get(reqId)
        if event is not None:
            event.set()

    # ---------- Synchronous helper methods ----------

    def start(self) -> threading.Thread:
        print(f"Connecting to IB Gateway / TWS at {HOST}:{PORT}...")
        self.connect(HOST, PORT, CLIENT_ID)

        thread = threading.Thread(target=self.run, name="ibkr-api-loop", daemon=False)
        thread.start()

        if not self.api_ready.wait(CONNECT_TIMEOUT):
            self.disconnect()
            thread.join(timeout=5)
            raise TimeoutError(
                "Timed out waiting for nextValidId. Check that TWS/IB Gateway is running, "
                "API socket access is enabled, and HOST/PORT/CLIENT_ID are correct."
            )

        print("IBKR API connection is ready.")
        return thread

    def get_position_snapshot(self) -> List[PositionRecord]:
        with self._lock:
            self._raw_positions.clear()
        self.positions_complete.clear()

        print("Requesting position snapshot...")
        self.reqPositions()

        if not self.positions_complete.wait(POSITIONS_TIMEOUT):
            self.cancelPositions()
            raise TimeoutError("Timed out waiting for positionEnd().")

        # reqPositions is a subscription, so stop it after the initial snapshot.
        self.cancelPositions()

        with self._lock:
            snapshot = list(self._raw_positions)

        print(f"Received {len(snapshot)} non-zero position records.")
        return snapshot

    def get_daily_history(
        self,
        req_id: int,
        label: str,
        contract: Contract,
    ) -> pd.Series:
        event = threading.Event()
        with self._lock:
            self._historical_data[req_id] = []
            self._historical_events[req_id] = event
            self._req_id_to_label[req_id] = label
            self._historical_errors.pop(req_id, None)

        print(f"Requesting {DURATION} of {BAR_SIZE} data for {label} (reqId={req_id})...")
        self.reqHistoricalData(
            req_id,
            contract,
            "",                 # Empty means now; required/recommended for ADJUSTED_LAST
            DURATION,
            BAR_SIZE,
            WHAT_TO_SHOW,
            USE_RTH,
            1,                  # Daily bars are returned as YYYYMMDD
            False,
            [],
        )

        if not event.wait(HISTORICAL_TIMEOUT):
            self.cancelHistoricalData(req_id)
            raise TimeoutError(
                f"Timed out waiting for historicalDataEnd() for {label} "
                f"after {HISTORICAL_TIMEOUT} seconds."
            )

        with self._lock:
            request_error = self._historical_errors.get(req_id)
            bars = list(self._historical_data.get(req_id, []))

        if request_error:
            raise RuntimeError(request_error)
        if not bars:
            raise RuntimeError(f"IBKR returned no historical bars for {label}.")

        frame = pd.DataFrame(bars, columns=["date", "close"])
        frame["date"] = pd.to_datetime(frame["date"], format="%Y%m%d", errors="coerce")
        frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
        frame = (
            frame.dropna(subset=["date", "close"])
            .loc[lambda x: x["close"] > 0]
            .drop_duplicates(subset="date", keep="last")
            .sort_values("date")
        )

        if len(frame) < 2:
            raise RuntimeError(f"Not enough valid historical bars for {label}.")

        return frame.set_index("date")["close"].rename(label)


def aggregate_positions(records: List[PositionRecord]) -> List[PositionRecord]:
    """Aggregate the same IB contract across accounts without using quantity as a key."""
    grouped: Dict[Tuple, List[PositionRecord]] = {}

    for record in records:
        key = (
            record.con_id if record.con_id > 0 else None,
            record.symbol,
            record.sec_type,
            record.currency,
        )
        grouped.setdefault(key, []).append(record)

    aggregated: List[PositionRecord] = []
    for group in grouped.values():
        first = group[0]
        quantity = sum(item.quantity for item in group)
        if math.isclose(quantity, 0.0, abs_tol=1e-12):
            continue

        accounts = ",".join(sorted({item.account for item in group}))
        aggregated.append(
            PositionRecord(
                account=accounts,
                symbol=first.symbol,
                con_id=first.con_id,
                sec_type=first.sec_type,
                currency=first.currency,
                exchange=first.exchange,
                primary_exchange=first.primary_exchange,
                multiplier=first.multiplier,
                quantity=quantity,
                avg_cost=first.avg_cost,
            )
        )

    return sorted(aggregated, key=lambda x: (x.symbol, x.con_id))


def make_historical_contract(position: PositionRecord) -> Contract:
    contract = Contract()
    contract.conId = position.con_id
    contract.symbol = position.symbol
    contract.secType = position.sec_type
    contract.currency = position.currency

    # For stocks, SMART + conId is generally the least ambiguous request.
    contract.exchange = "SMART" if position.sec_type == "STK" else (position.exchange or "SMART")
    if position.primary_exchange:
        contract.primaryExchange = position.primary_exchange
    return contract

def make_spy_contract() -> Contract:
    contract = Contract()
    contract.symbol = "SPY"
    contract.secType = "STK"
    contract.exchange = "SMART"
    contract.currency = "USD"
    contract.primaryExchange = "ARCA"  # ARCA is a primary listing for SPY
    # conId can be left out for a generic SPY
    return contract

def unique_labels(positions: List[PositionRecord]) -> Dict[int, str]:
    symbol_counts: Dict[str, int] = {}
    for position in positions:
        symbol_counts[position.symbol] = symbol_counts.get(position.symbol, 0) + 1

    labels: Dict[int, str] = {}
    for position in positions:
        labels[position.con_id] = (
            position.symbol
            if symbol_counts[position.symbol] == 1
            else f"{position.symbol}_{position.con_id}"
        )
    return labels


def calculate_portfolio_returns(
    positions: List[PositionRecord],
    prices: pd.DataFrame,
    labels: Dict[int, str],
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Build signed gross-exposure weights from the latest common close:

        signed market value_i = quantity_i * multiplier_i * latest price_i
        weight_i = signed market value_i / sum(abs(signed market values))
        portfolio return_t = sum(weight_i * asset return_i,t)

    Positive quantities create positive weights; shorts create negative weights.
    Sum(abs(weights)) = 1. This avoids unstable net-denominator math for
    market-neutral or nearly market-neutral portfolios.
    """
    prices = prices.sort_index().dropna(how="any")
    if prices.empty or len(prices) < 2:
        raise RuntimeError("Fewer than two common price dates remain after alignment.")

    latest_date = prices.index[-1]
    latest_prices = prices.iloc[-1]

    rows = []
    for position in positions:
        label = labels[position.con_id]
        latest_price = float(latest_prices[label])
        signed_market_value = position.quantity * position.multiplier * latest_price
        rows.append(
            {
                "account": position.account,
                "symbol": position.symbol,
                "label": label,
                "con_id": position.con_id,
                "currency": position.currency,
                "quantity": position.quantity,
                "multiplier": position.multiplier,
                "side": "LONG" if position.quantity > 0 else "SHORT",
                "latest_common_date": latest_date.date().isoformat(),
                "latest_price": latest_price,
                "signed_market_value": signed_market_value,
                "absolute_market_value": abs(signed_market_value),
            }
        )

    weights = pd.DataFrame(rows).set_index("label")
    gross_exposure = float(weights["absolute_market_value"].sum())
    if gross_exposure <= 0:
        raise RuntimeError("Gross exposure is zero; portfolio weights cannot be calculated.")

    weights["weight"] = weights["signed_market_value"] / gross_exposure
    weights["weight_pct"] = weights["weight"] * 100.0

    asset_returns = prices.pct_change(fill_method=None).dropna(how="any")
    ordered_weights = weights.loc[asset_returns.columns, "weight"]
    portfolio_return = asset_returns.mul(ordered_weights, axis="columns").sum(axis=1)

    portfolio = pd.DataFrame({"portfolio_return": portfolio_return})
    portfolio["wealth_index"] = (1.0 + portfolio["portfolio_return"]).cumprod()
    portfolio["cumulative_return"] = portfolio["wealth_index"] - 1.0
    portfolio["drawdown"] = portfolio["wealth_index"] / portfolio["wealth_index"].cummax() - 1.0

    contributions = asset_returns.mul(ordered_weights, axis="columns")
    contributions.columns = [f"{column}_contribution" for column in contributions.columns]
    portfolio = portfolio.join(contributions)

    return weights.reset_index(), asset_returns, portfolio


def print_summary(weights: pd.DataFrame, portfolio: pd.DataFrame) -> None:
    returns = portfolio["portfolio_return"]
    observations = len(returns)
    total_return = float(portfolio["cumulative_return"].iloc[-1])
    volatility = float(returns.std(ddof=1) * math.sqrt(TRADING_DAYS_PER_YEAR))
    annualized_return = (
        (1.0 + total_return) ** (TRADING_DAYS_PER_YEAR / observations) - 1.0
        if observations > 0 and 1.0 + total_return > 0
        else float("nan")
    )
    sharpe_zero_rf = (
        float(returns.mean() / returns.std(ddof=1) * math.sqrt(TRADING_DAYS_PER_YEAR))
        if returns.std(ddof=1) > 0
        else float("nan")
    )
    max_drawdown = float(portfolio["drawdown"].min())

    long_exposure = float(weights.loc[weights["weight"] > 0, "weight"].sum())
    short_exposure = float(weights.loc[weights["weight"] < 0, "weight"].sum())
    net_exposure = float(weights["weight"].sum())

    print("\nSigned portfolio weights (gross-normalized):")
    display_columns = [
        "symbol", "side", "quantity", "latest_price",
        "signed_market_value", "weight_pct",
    ]
    print(weights[display_columns].to_string(index=False, float_format=lambda x: f"{x:,.4f}"))

    print("\nPortfolio return summary:")
    print(f"  Return period:      {returns.index[0].date()} through {returns.index[-1].date()}")
    print(f"  Daily observations: {observations:,}")
    print(f"  Long exposure:      {long_exposure:,.2%}")
    print(f"  Short exposure:     {short_exposure:,.2%}")
    print(f"  Net exposure:       {net_exposure:,.2%}")
    print(f"  Total return:       {total_return:,.2%}")
    print(f"  Annualized return:  {annualized_return:,.2%}")
    print(f"  Annualized vol:     {volatility:,.2%}")
    print(f"  Sharpe (0% RF):     {sharpe_zero_rf:,.3f}")
    print(f"  Max drawdown:       {max_drawdown:,.2%}")


def main() -> None:
    app = IBKRPortfolioApp()
    api_thread: Optional[threading.Thread] = None

    try:
        api_thread = app.start()
        raw_positions = app.get_position_snapshot()
        if not raw_positions:
            print("No non-zero positions were returned.")
            return

        positions = aggregate_positions(raw_positions)
        if not positions:
            print("All positions netted to zero after aggregation.")
            return

        unsupported = [p for p in positions if p.sec_type != "STK"]
        if unsupported:
            details = ", ".join(f"{p.symbol} ({p.sec_type})" for p in unsupported)
            raise NotImplementedError(
                "This version intentionally supports stock/ETF positions only because "
                "cross-asset multipliers, expiries, and pricing conventions require separate "
                f"handling. Unsupported positions: {details}"
            )

        currencies = sorted({p.currency for p in positions})
        if len(currencies) != 1:
            raise NotImplementedError(
                "The portfolio contains multiple currencies. Correct weights require FX conversion "
                f"to one base currency first. Currencies found: {currencies}"
            )

        labels = unique_labels(positions)
        series_list: List[pd.Series] = []

        print(f"Fetching history for {len(positions)} aggregated positions...")
        for offset, position in enumerate(positions):
            req_id = 1000 + offset
            label = labels[position.con_id]
            contract = make_historical_contract(position)
            series_list.append(app.get_daily_history(req_id, label, contract))
            time.sleep(REQUEST_PAUSE_SECONDS)

        # Fetch SPY returns for benchmarking
        spy_req_id = 9999
        spy_label = "SPY"
        spy_contract = make_spy_contract()
        spy_series = app.get_daily_history(spy_req_id, spy_label, spy_contract)
        time.sleep(REQUEST_PAUSE_SECONDS)

        # Align the portfolio's prices and SPY to the same date range (inner join)
        prices = pd.concat(series_list, axis=1, join="inner").sort_index()
        # Join SPY series to the same dates, preserving only dates common to all
        joined = pd.concat([prices, spy_series], axis=1, join="inner").sort_index()
        # All further calculations (returns, weights) use only dates common to all assets and SPY

        # Remove SPY from asset columns for weight/portfolio-return calcs, but keep for output
        prices_only = joined.drop(columns=[spy_label])
        spy_only = joined[spy_label]

        weights, asset_returns, portfolio = calculate_portfolio_returns(
            positions, prices_only, labels
        )

        # Add SPY benchmark returns to asset_returns and portfolio
        spy_returns = spy_only.pct_change(fill_method=None).dropna(how="any")
        # Re-align/restrict to portfolio dates
        spy_returns = spy_returns.reindex(portfolio.index).dropna()
        # Re-restrict project to intersection (should always be intersection already)
        portfolio = portfolio.loc[spy_returns.index]
        asset_returns = asset_returns.loc[spy_returns.index]
        weights = weights.copy()
        # Add SPY return to asset_returns and as a column in portfolio returns as benchmark
        asset_returns["SPY"] = spy_returns
        portfolio["spy_return"] = spy_returns

        # Save results to CSV in the current folder (where this script resides)
        out_dir = Path(__file__).parent.resolve()
        weights.to_csv(out_dir / "portfolio_weights.csv", index=False)
        # All dates and all assets, including SPY
        joined.to_csv(out_dir / "adjusted_close_prices.csv", index_label="date")
        asset_returns.to_csv(out_dir / "asset_returns.csv", index_label="date")
        # Portfolio returns with a 'spy_return' benchmark column
        portfolio.to_csv(out_dir / "portfolio_returns.csv", index_label="date")

        print_summary(weights, portfolio)
        print(f"\nSaved results to the folder containing this script:")
        print("  - portfolio_weights.csv")
        print("  - adjusted_close_prices.csv")
        print("  - asset_returns.csv")
        print("  - portfolio_returns.csv")
        print(
            "\nImportant: this is a backcast of the CURRENT position quantities/weights over "
            "the historical period. It is not the account's actual historical performance, "
            "because IBKR's position snapshot does not contain historical trades or past weights."
        )
        print("\nNote: 'portfolio_returns.csv' includes a 'spy_return' column for SPY ETF as benchmark.")

    except KeyboardInterrupt:
        print("\nInterrupted by user.")
    except Exception as exc:
        print(f"\nFAILED: {type(exc).__name__}: {exc}")
        raise
    finally:
        if app.isConnected():
            app.disconnect()
        if api_thread is not None and api_thread.is_alive():
            api_thread.join(timeout=5)
        print("Disconnected from IBKR.")


if __name__ == "__main__":
    main()