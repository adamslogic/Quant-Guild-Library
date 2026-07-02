import time
import pandas as pd
import numpy as np
from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract
from threading import Thread

# Script to fetch and save SPY and VRT stocks' daily returns for last 10 years to CSV

class IBKRApp(EWrapper, EClient):
    def __init__(self):
        EClient.__init__(self, self)
        EWrapper.__init__(self)
        self.spy_data = []
        self.vrt_data = []
        self.done = False
        self.req_error = False
        self.mode = None  # "spy" or "vrt"

    def error(self, reqId, errorCode, errorString):
        print(f"IBKR ERROR {reqId} {errorCode} {errorString}")
        if errorCode in [10314, 200]:
            self.done = True
            self.req_error = True

    def historicalData(self, reqId, bar):
        if self.mode == "spy":
            self.spy_data.append({
                "date": bar.date,
                "close": bar.close
            })
        elif self.mode == "vrt":
            self.vrt_data.append({
                "date": bar.date,
                "close": bar.close
            })

    def historicalDataEnd(self, reqId, start, end):
        self.done = True

def run_loop(app):
    app.run()

def fetch_spy_and_vrt_daily_returns(
    filename="spy_vrt_daily_returns_10y.csv",
    durationStr="10 Y"
):
    app = IBKRApp()
    app.connect("127.0.0.1", 7497, 1)
    api_thread = Thread(target=run_loop, args=(app,))
    api_thread.start()
    time.sleep(1)

    # Contract for SPY stock
    spy_contract = Contract()
    spy_contract.symbol = "SPY"
    spy_contract.secType = "STK"
    spy_contract.exchange = "ARCA"  # or "SMART"
    spy_contract.currency = "USD"

    app.mode = "spy"
    try:
        app.reqHistoricalData(
            reqId=1,
            contract=spy_contract,
            endDateTime="",
            durationStr=durationStr,
            barSizeSetting="1 day",
            whatToShow="TRADES",
            useRTH=1,
            formatDate=1,
            keepUpToDate=False,
            chartOptions=[]
        )
    except Exception as e:
        print(f"Error requesting SPY TRADES data:", e)
        app.done = True

    timeout = 90
    t0 = time.time()
    while not app.done and (time.time() - t0 < timeout):
        time.sleep(0.5)
    if not app.done:
        print("Timeout waiting for IBKR SPY price data.")

    app.done = False  # reset for vrt

    # Contract for VRT stock
    vrt_contract = Contract()
    vrt_contract.symbol = "VRT"
    vrt_contract.secType = "STK"
    vrt_contract.exchange = "NYSE"  # Use the appropriate exchange for VRT (can be "SMART" or other)
    vrt_contract.currency = "USD"

    app.mode = "vrt"
    try:
        app.reqHistoricalData(
            reqId=2,
            contract=vrt_contract,
            endDateTime="",
            durationStr=durationStr,
            barSizeSetting="1 day",
            whatToShow="TRADES",
            useRTH=1,
            formatDate=1,
            keepUpToDate=False,
            chartOptions=[]
        )
    except Exception as e:
        print(f"Error requesting VRT TRADES data:", e)
        app.done = True

    t1 = time.time()
    while not app.done and (time.time() - t1 < timeout):
        time.sleep(0.5)
    if not app.done:
        print("Timeout waiting for IBKR VRT price data.")

    app.disconnect()
    time.sleep(1)

    spy_df = pd.DataFrame(app.spy_data)
    vrt_df = pd.DataFrame(app.vrt_data)

    if not spy_df.empty:
        spy_df["date"] = pd.to_datetime(spy_df["date"])
        spy_df.set_index("date", inplace=True)
        spy_df.sort_index(inplace=True)
        spy_df["close"] = spy_df["close"].astype(float)

        spy_df["spy_log_return"] = np.log(spy_df["close"]).diff()
        spy_df["spy_simple_return"] = spy_df["close"].pct_change()

        spy_out = spy_df[["close", "spy_log_return", "spy_simple_return"]].copy()
        spy_out.rename(columns={"close": "spy_close"}, inplace=True)
    else:
        print("No TRADES price data for SPY.")
        spy_out = pd.DataFrame()

    if not vrt_df.empty:
        vrt_df["date"] = pd.to_datetime(vrt_df["date"])
        vrt_df.set_index("date", inplace=True)
        vrt_df.sort_index(inplace=True)
        vrt_df["close"] = vrt_df["close"].astype(float)

        vrt_df["vrt_log_return"] = np.log(vrt_df["close"]).diff()
        vrt_df["vrt_simple_return"] = vrt_df["close"].pct_change()

        vrt_out = vrt_df[["close", "vrt_log_return", "vrt_simple_return"]].copy()
        vrt_out.rename(columns={"close": "vrt_close"}, inplace=True)
    else:
        print("No TRADES price data for VRT.")
        vrt_out = pd.DataFrame()

    # Join SPY and VRT returns on date
    if not spy_out.empty and not vrt_out.empty:
        out_df = spy_out.join(vrt_out, how="outer")
    elif not spy_out.empty:
        out_df = spy_out
    elif not vrt_out.empty:
        out_df = vrt_out
    else:
        out_df = pd.DataFrame()

    if not out_df.empty:
        out_df.index.name = "date"
        out_df.to_csv(filename)
        print(f"Saved SPY and VRT daily returns (last 10 years) as {filename}")
        return out_df

if __name__ == "__main__":
    fetch_spy_and_vrt_daily_returns()