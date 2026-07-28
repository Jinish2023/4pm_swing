"""
Production Scanner & Position Monitor with Excel Export
──────────────────────────────────────────────────────────────────────────
Columns: serial no, date, stock name, entry price, stop loss, current price, profit/loss, profit & loss %
"""
import os
import sys
import time
from datetime import datetime
import numpy as np
import pandas as pd
import yfinance as yf

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

EXCEL_FILE = "portfolio_tracker.xlsx"
USE_FULL_NIFTY500 = True

FALLBACK_UNIVERSE = [
    "RELIANCE", "TCS", "HDFCBANK", "ICICIBANK", "INFY", "HINDUNILVR", "ITC",
    "SBIN", "BHARTIARTL", "KOTAKBANK", "LT", "AXISBANK", "BAJFINANCE",
    "ASIANPAINT", "MARUTI", "SUNPHARMA", "TITAN", "ULTRACEMCO", "WIPRO",
    "NESTLEIND", "HCLTECH", "TATASTEEL", "POWERGRID", "NTPC",
    "ONGC", "M&M", "ADANIENT", "JSWSTEEL", "GRASIM", "BAJAJFINSV",
    "INDUSINDBK", "TECHM", "DRREDDY", "CIPLA", "DIVISLAB", "EICHERMOT",
    "HEROMOTOCO", "BRITANNIA", "COALINDIA", "HINDALCO", "APOLLOHOSP", "BPCL",
    "TATACONSUM", "TRENT", "DLF", "HAVELLS", "SIEMENS", "PIDILITIND",
]


def _flatten_columns(df):
    if isinstance(df.columns, pd.MultiIndex):
        df = df.copy()
        df.columns = df.columns.get_level_values(0)
    return df


def compute_atr(df, period=14):
    high = df["High"]
    low = df["Low"]
    close = df["Close"]
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def scan_new_entries(symbol):
    ticker = f"{symbol}.NS"
    try:
        df = yf.download(ticker, period="1y", interval="1d", auto_adjust=True, progress=False)
        df = _flatten_columns(df)
        if len(df) < 130:
            return None

        df["DMA100"] = df["Close"].rolling(100).mean()
        df["EMA20"] = df["Close"].ewm(span=20, adjust=False).mean()
        df["SMA20"] = df["Close"].rolling(20).mean()
        df["ATR"] = compute_atr(df, 14)
        df["VolSMA20"] = df["Volume"].rolling(20).mean()

        trend_ma = df["DMA100"].values
        fast_ma = df["EMA20"].values
        close = df["Close"].values
        volume = df["Volume"].values
        vol_sma20 = df["VolSMA20"].values
        
        i = len(df) - 1
        if np.isnan(trend_ma[i]) or np.isnan(fast_ma[i]) or np.isnan(df["ATR"].iloc[i]) or np.isnan(vol_sma20[i]):
            return None

        # 1. Macro Regime Check (Price > 100 DMA)
        if close[i] <= trend_ma[i]:
            return None

        # 2. Volume Confirmation Filter (Volume > 20-day Volume SMA)
        if volume[i] <= vol_sma20[i]:
            return None

        # 3. Setup Trigger: Touch & Bounce Only
        touch_and_bounce = (abs(fast_ma[i] - trend_ma[i]) / trend_ma[i] <= 0.015) and (fast_ma[i] >= fast_ma[i - 1])

        if touch_and_bounce:
            initial_stop = close[i] - (3.0 * df["ATR"].iloc[i])
            return {
                "stock name": symbol,
                "entry_price": round(close[i], 2),
                "stop_loss": round(initial_stop, 2),
                "current_price": round(close[i], 2),
            }
    except Exception:
        pass
    return None


def update_excel_tracker(new_signals):
    if not new_signals:
        print("No new signals to append today.")
        return

    today_str = datetime.now().strftime("%Y-%m-%d")
    
    if os.path.exists(EXCEL_FILE):
        df_existing = pd.read_excel(EXCEL_FILE)
        start_sl = len(df_existing) + 1
    else:
        df_existing = pd.DataFrame(columns=[
            "serial no", "date", "stock name", "entry price", 
            "stop loss", "current price", "profit/loss", "profit & loss %"
        ])
        start_sl = 1

    rows_to_add = []
    for idx, sig in enumerate(new_signals):
        ep = sig["entry_price"]
        cp = sig["current_price"]
        pl = round(cp - ep, 2)
        pl_pct = round((pl / ep) * 100, 2) if ep > 0 else 0.0

        rows_to_add.append({
            "serial no": start_sl + idx,
            "date": today_str,
            "stock name": sig["stock name"],
            "entry price": ep,
            "stop loss": sig["stop_loss"],
            "current price": cp,
            "profit/loss": pl,
            "profit & loss %": pl_pct
        })

    df_new = pd.DataFrame(rows_to_add)
    df_combined = pd.concat([df_existing, df_new], ignore_index=True)
    
    df_combined.to_excel(EXCEL_FILE, index=False)
    print(f"Successfully updated {EXCEL_FILE} with {len(rows_to_add)} new entries.")


def main():
    if USE_FULL_NIFTY500:
        try:
            from src.universe import fetch_stock_universe
            universe = fetch_stock_universe()
            print(f"Loaded live NIFTY 500 list ({len(universe)} symbols).")
        except Exception as e:
            universe = FALLBACK_UNIVERSE
            print(f"Using fallback universe due to: {e}")
    else:
        universe = FALLBACK_UNIVERSE

    print(f"\n[PRODUCTION SCANNER] Scanning {len(universe)} symbols for Strategy B (Bounce + Vol Filter)...")
    print("=" * 60)

    buy_signals = []
    for symbol in universe:
        res = scan_new_entries(symbol)
        if res:
            buy_signals.append(res)
            print(f"[BUY SIGNAL] Found: {res['stock name']} @ Entry {res['entry_price']} | Stop: {res['stop_loss']}")
        time.sleep(0.05)

    print("=" * 60)
    print(f"Scan complete. Total Actionable Buy Signals: {len(buy_signals)}")

    update_excel_tracker(buy_signals)


if __name__ == "__main__":
    main()
