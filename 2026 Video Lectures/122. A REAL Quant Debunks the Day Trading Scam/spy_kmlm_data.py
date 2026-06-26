"""
Fetch daily OHLCV for SPY and KMLM from IBKR and merge into one CSV by date (2021-2022 only).

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

SYMBOLS = ("SPY", "KMLM")  # Only SPY and KMLM

HOST = "127.0.0.1"
PORT = 7497
CLIENT_ID = 114
REQUEST_TIMEOUT_S = 90
PACING_SLEEP_S = 2.0

SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_CSV = SCRIPT_DIR / "spy_kmlm_prices_2021_2022.csv"

START_DATE = pd.Timestamp("2021-01-01")
END_DATE = pd.Timestamp("2022-12-31")


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


def fetch_daily_bars(
    app: IBKRHistoricalApp,
    req_id: int,
    symbol: str,
) -> pd.DataFrame:
    duration_str = "2 Y"  # 2021-2022
    endDateTime = "20221231 23:59:59"  # Format: YYYYMMDD HH:MM:SS

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

    # Filter to 2021-01-01 through 2022-12-31
    df["date"] = pd.to_datetime(df["date"])
    mask = (df["date"] >= START_DATE) & (df["date"] <= END_DATE)
    df = df.loc[mask]
    return df.sort_values("date").drop_duplicates(subset=["date"]).reset_index(drop=True)


def merge_closes_by_date(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    merged: pd.DataFrame | None = None
    for symbol, df in frames.items():
        if df.empty:
            continue
        piece = df[["date", "close"]].rename(columns={"close": symbol})
        merged = piece if merged is None else merged.merge(piece, on="date", how="outer")

    if merged is None:
        return pd.DataFrame()

    merged = merged.sort_values("date").reset_index(drop=True)
    merged = merged.rename(columns={"date": "Date"})
    return merged


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

    frames: dict[str, pd.DataFrame] = {}
    try:
        for i, symbol in enumerate(SYMBOLS, start=1):
            print(f"[{i}/{len(SYMBOLS)}] Fetching {symbol}…", flush=True)
            df = fetch_daily_bars(app, req_id=i, symbol=symbol)
            if df.empty:
                err = app._errors[-1] if app._errors else "no bars returned"
                print(f"  skipped {symbol}: {err}", flush=True)
            else:
                frames[symbol] = df
                print(
                    f"  {len(df)} rows ({df['date'].min().date()} to {df['date'].max().date()})",
                    flush=True,
                )
            if i < len(SYMBOLS):
                time.sleep(PACING_SLEEP_S)
    finally:
        app.disconnect()

    merged = merge_closes_by_date(frames)
    if merged.empty:
        print("No data retrieved; check TWS/Gateway and market data subscriptions.")
        return merged

    merged.to_csv(output_path, index=False)
    print(f"Wrote {len(merged)} rows, {len(merged.columns)} columns -> {output_path}")
    return merged


if __name__ == "__main__":
    fetch_and_save()
