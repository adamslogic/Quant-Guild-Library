import time
import pandas as pd
from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract
from threading import Thread

# Script to fetch and save SPX OPTION_IMPLIED_VOLATILITY and Realized Volatility (windowed) to CSV

class IBKRApp(EWrapper, EClient):
    def __init__(self):
        EClient.__init__(self, self)
        EWrapper.__init__(self)
        self.ov_data = []
        self.price_data = []
        self.done = False
        self.req_error = False
        self.mode = None  # "implied" or "price"

    def error(self, reqId, errorCode, errorString):
        print(f"IBKR ERROR {reqId} {errorCode} {errorString}")
        if errorCode in [10314, 200]:
            self.done = True
            self.req_error = True

    def historicalData(self, reqId, bar):
        if self.mode == "implied":
            self.ov_data.append({
                "date": bar.date,
                "option_implied_volatility": bar.close
            })
        elif self.mode == "price":
            self.price_data.append({
                "date": bar.date,
                "close": bar.close
            })

    def historicalDataEnd(self, reqId, start, end):
        self.done = True

def run_loop(app):
    app.run()

def fetch_spx_option_implied_and_realized_volatility(
    filename="spx_option_implied_realized_vol_10y.csv",
    durationStr="10 Y",
    realized_window_days=21  # trading days (~1 month)
):
    app = IBKRApp()
    app.connect("127.0.0.1", 7497, 1)
    api_thread = Thread(target=run_loop, args=(app,))
    api_thread.start()
    time.sleep(1)

    # Contract for SPX index
    spx_contract = Contract()
    spx_contract.symbol = "SPX"
    spx_contract.secType = "IND"
    spx_contract.exchange = "CBOE"
    spx_contract.currency = "USD"

    # Fetch implied volatility
    app.mode = "implied"
    try:
        app.reqHistoricalData(
            reqId=1,
            contract=spx_contract,
            endDateTime="",
            durationStr=durationStr,
            barSizeSetting="1 day",
            whatToShow="OPTION_IMPLIED_VOLATILITY",
            useRTH=1,
            formatDate=1,
            keepUpToDate=False,
            chartOptions=[]
        )
    except Exception as e:
        print(f"Error requesting OPTION_IMPLIED_VOLATILITY for SPX:", e)
        app.done = True

    timeout = 90
    t0 = time.time()
    while not app.done and (time.time() - t0 < timeout):
        time.sleep(0.5)
    if not app.done:
        print("Timeout waiting for IBKR implied vol data.")

    implied_vol_df = pd.DataFrame(app.ov_data)
    app.done = False  # Reset for price data

    # Fetch historical prices for realized volatility
    app.mode = "price"
    try:
        app.reqHistoricalData(
            reqId=2,
            contract=spx_contract,
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
        print(f"Error requesting SPX TRADES data for realized vol:", e)
        app.done = True

    t1 = time.time()
    while not app.done and (time.time() - t1 < timeout):
        time.sleep(0.5)
    if not app.done:
        print("Timeout waiting for IBKR price data.")

    app.disconnect()
    time.sleep(1)

    price_df = pd.DataFrame(app.price_data)
    if not price_df.empty:
        # Compute daily log returns
        price_df["date"] = pd.to_datetime(price_df["date"])
        price_df.set_index("date", inplace=True)
        price_df.sort_index(inplace=True)
        price_df["log_return"] = (price_df["close"].astype(float)).apply(lambda x: float(x)).apply(lambda p: pd.NA if pd.isnull(p) else p)
        price_df["log_return"] = (price_df["close"].astype(float)).apply(lambda x: float(x)).apply(lambda p: pd.NA if pd.isnull(p) else p)
        price_df["log_return"] = np.log(price_df["close"].astype(float)).diff()
        # Realized volatility (windowed standard deviation of daily log returns annualized)
        price_df["realized_volatility"] = (
            price_df["log_return"].rolling(window=realized_window_days)
            .std() * (252**0.5)
        )
    else:
        print("No TRADES price data for SPX to compute realized volatility.")

    # Merge implied and realized volatility
    if not implied_vol_df.empty and not price_df.empty:
        implied_vol_df["date"] = pd.to_datetime(implied_vol_df["date"])
        implied_vol_df.set_index("date", inplace=True)
        # Only keep columns needed for merge
        out_df = implied_vol_df[["option_implied_volatility"]].copy()
        # Merge realized vol
        out_df = out_df.join(price_df[["realized_volatility"]], how="left")
        out_df.index.name = "date"
        out_df.to_csv(filename)
        print(
            f"Saved SPX implied and realized vol (window={realized_window_days} days) as {filename}"
        )
        return out_df
    else:
        print("Could not assemble implied and realized volatility data for SPX.")

if __name__ == "__main__":
    import numpy as np
    fetch_spx_option_implied_and_realized_volatility()