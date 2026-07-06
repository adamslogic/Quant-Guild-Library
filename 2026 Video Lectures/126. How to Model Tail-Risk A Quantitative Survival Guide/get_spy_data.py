"""
Fetch daily OHLCV for SPY ETF from IBKR from 1999-present (to 2026),
saving to one CSV by date.

Requires TWS or IB Gateway on 127.0.0.1 with API enabled (default TWS port 7497).
"""

from __future__ import annotations

import time
from pathlib import Path
from threading import Thread

import pandas as pd
from ibapi.client import EClient
from ibapi.contract import Contract
from ibapi.wrapper import EWrapper

# Universe: SPY only
SYMBOL = "SPY"   # S&P 500 ETF

HOST = "127.0.0.1"
PORT = 7497
CLIENT_ID = 114
REQUEST_TIMEOUT_S = 90
PACING_SLEEP_S = 2.0

SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_CSV = SCRIPT_DIR / "spy_1999_2026.csv"

START_DATE = pd.Timestamp("1999-01-01")
END_DATE = pd.Timestamp("2026-12-31")


def _parse_bar_date(s: str) -> pd.Timestamp:
    if isinstance(s, str) and len(s) == 8 and s.isdigit():
        return pd.Timestamp(s)
    return pd.to_datetime(s)


def run_loop(app: EClient) -> None:
    app.run()


def stock_contract(symbol: str) -> Contract:
    c = Contract()
    c.symbol = symbol
    c.secType = "STK"
    c.exchange = "SMART"
    c.currency = "USD"
    return c


class IBKRHistoricalApp(EWrapper, EClient):
    def __init__(self) -> None:
        EClient.__init__(self, self)
        self.data: list[dict] = []
        self.finished = False
        self._errors: list[tuple[int, str]] = []

    def historicalData(self, reqId, bar) -> None:
        self.data.append(
            {
                "date": _parse_bar_date(bar.date),
                "open": float(bar.open),
                "high": float(bar.high),
                "low": float(bar.low),
                "close": float(bar.close),
                "volume": float(bar.volume),
            }
        )

    def historicalDataEnd(self, reqId, start, end) -> None:
        self.finished = True

    def error(self, reqId, errorCode, errorString, advancedOrderReject="") -> None:
        if errorCode in (2104, 2106, 2158, 2119, 2174):  # common warnings, can ignore
            return
        self._errors.append((errorCode, errorString))
        if reqId >= 0:
            self.finished = True


def fetch_daily_bars(
    app: IBKRHistoricalApp,
    req_id: int,
    symbol: str,
    start_date: pd.Timestamp,
    end_date: pd.Timestamp
) -> pd.DataFrame:
    # IBKR max duration (typically 1 year per request), so may need to page. We'll grab as much as possible (27 Y)
    duration_str = "27 Y"
    # Use explicit UTC time zone per IB API warning
    endDateTime = end_date.strftime("%Y%m%d 23:59:59 UTC")

    app.data = []
    app.finished = False
    app._errors.clear()

    app.reqHistoricalData(
        reqId=req_id,
        contract=stock_contract(symbol),
        endDateTime=endDateTime,
        durationStr=duration_str,
        barSizeSetting="1 day",
        whatToShow="TRADES",
        useRTH=1,
        formatDate=1,
        keepUpToDate=False,
        chartOptions=[],
    )

    deadline = time.time() + REQUEST_TIMEOUT_S
    while not app.finished and time.time() < deadline:
        time.sleep(0.25)

    if not app.finished:
        try:
            app.cancelHistoricalData(req_id)
        except Exception:
            pass
        return pd.DataFrame()

    if app._errors and not app.data:
        return pd.DataFrame()

    df = pd.DataFrame(app.data)
    if df.empty:
        return df

    # Filter to 1999-01-01 through 2026-12-31
    df["date"] = pd.to_datetime(df["date"])
    mask = (df["date"] >= start_date) & (df["date"] <= end_date)
    df = df.loc[mask]
    return df.sort_values("date").drop_duplicates(subset=["date"]).reset_index(drop=True)


def fetch_and_save(
    host: str = HOST,
    port: int = PORT,
    client_id: int = CLIENT_ID,
    output_path: Path = OUTPUT_CSV,
) -> pd.DataFrame:
    app = IBKRHistoricalApp()
    app.connect(host, port, client_id)
    thread = Thread(target=run_loop, args=(app,), daemon=True)
    thread.start()
    time.sleep(1)

    try:
        print(f"Fetching {SYMBOL} from IBKR...", flush=True)
        df = fetch_daily_bars(app, req_id=1, symbol=SYMBOL, start_date=START_DATE, end_date=END_DATE)
        if df.empty:
            err = app._errors[-1] if app._errors else "no bars returned"
            print(f"  skipped {SYMBOL}: {err}", flush=True)
        else:
            print(
                f"  {len(df)} rows ({df['date'].min().date()} to {df['date'].max().date()})",
                flush=True,
            )
    finally:
        app.disconnect()

    if df.empty:
        print("No data retrieved; check TWS/Gateway and market data subscriptions.")
        return df

    df = df.rename(columns={"date": "Date", "open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"})
    df = df[["Date", "Open", "High", "Low", "Close", "Volume"]]
    df.to_csv(output_path, index=False)
    print(f"Wrote {len(df)} rows, {len(df.columns)} columns -> {output_path}")
    return df


if __name__ == "__main__":
    fetch_and_save()
