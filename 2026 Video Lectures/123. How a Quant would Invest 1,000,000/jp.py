"""
Fetch monthly OHLCV for EWJ from IBKR going back as far as possible and save to CSV.

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

SYMBOL = "EWJ"  # iShares MSCI Japan ETF

HOST = "127.0.0.1"
PORT = 7497
CLIENT_ID = 115
REQUEST_TIMEOUT_S = 120
PACING_SLEEP_S = 2.0


OUTPUT_CSV = "ewj_monthly_bars.csv"


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
        if errorCode in (2104, 2106, 2158, 2119):
            return
        self._errors.append((errorCode, errorString))
        if reqId >= 0:
            self.finished = True


def fetch_monthly_bars(
    app: IBKRHistoricalApp,
    req_id: int,
    symbol: str,
    end_date: str = "",   # "" means "now"
    duration_str: str = "30 Y"  # Try for 30 years of data, adjust as needed
) -> pd.DataFrame:
    app.data = []
    app.finished = False
    app._errors.clear()

    app.reqHistoricalData(
        reqId=req_id,
        contract=stock_contract(symbol),
        endDateTime=end_date,  # "" means current
        durationStr=duration_str,
        barSizeSetting="1 month",
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
        print(f"Error fetching bars: {app._errors}")
        return pd.DataFrame()

    df = pd.DataFrame(app.data)
    if df.empty:
        return df

    # Ensure datetime, sort, drop duplicate months
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").drop_duplicates(subset=["date"]).reset_index(drop=True)
    return df


def fetch_and_save_ewj_monthly(
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
        print("Fetching EWJ monthly bars as far back as possible...", flush=True)
        df = fetch_monthly_bars(app, req_id=1, symbol=SYMBOL)
        if df.empty:
            err = app._errors[-1] if app._errors else "no bars returned"
            print(f"  Failed to fetch EWJ: {err}", flush=True)
            return df
        print(
            f"  {len(df)} rows ({df['date'].min().date()} to {df['date'].max().date()})",
            flush=True,
        )
    finally:
        app.disconnect()

    df = df.rename(columns={"date": "Date"})
    df.to_csv(output_path, index=False)
    print(f"Wrote {len(df)} EWJ monthly bars -> {output_path}")
    return df


if __name__ == "__main__":
    import sys
    import os

    # Defensive: Allow user to run this even if path contains spaces/commas by quoting path (for Windows users)
    # THE SCRIPT ITSELF IS LOCATED AT:
    # '2026 Video Lectures/123. What I would do with $1,000,000 if I was/jp.py'
    # The filename and directory names containing spaces, commas, and $ are valid for Python execution.
    # Windows PowerShell and Command Prompt require the full path quoted.
    # Example usage:
    #   python "2026 Video Lectures/123. What I would do with $1,000,000 if I was/jp.py"
    # If you see "can't open file", check for typos and ensure you are quoting the full path!

    # Run main
    fetch_and_save_ewj_monthly()
