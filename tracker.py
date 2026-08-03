"""
Tracker: does two jobs each time it runs --

1. For "Pending" candidates (from a prior scan), fills the entry at the
   NEXT available trading day's OPEN price and flips them to "Open".
2. For "Open" positions, checks the latest daily bar's High/Low against
   Target/StopLoss (stop checked first, conservative) and closes them
   out if hit, or via a time-based exit after max_hold_days.

Run AFTER market close each trading day -- the workflow runs this
automatically, or trigger it manually with mode=track.
"""
from datetime import datetime
from pathlib import Path

import pandas as pd
import yfinance as yf

from strategy_core import CONFIG

RESULTS_PATH = Path("results.csv")


def fetch_latest_bar(ticker):
    df = yf.download(ticker, period="10d", auto_adjust=True, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.dropna()
    if df.empty:
        return None
    return df.iloc[-1], df.index[-1]


def main():
    cfg = CONFIG
    if not RESULTS_PATH.exists():
        print("No results.csv found -- run the scanner first.")
        return

    results = pd.read_csv(RESULTS_PATH)
    for col in ["ScanDate", "EntryDate", "ExitDate"]:
        results[col] = pd.to_datetime(results[col], errors="coerce")

    changed = False

    # 1. Fill pending candidates at the next available day's open
    for idx in results.index[results["Taken"] == "No"]:
        ticker = results.at[idx, "Ticker"]
        bar = fetch_latest_bar(ticker)
        if bar is None:
            continue
        row, bar_date = bar
        if bar_date <= results.at[idx, "ScanDate"]:
            continue  # no new trading day available yet, try again next run
        results.at[idx, "EntryDate"] = bar_date
        results.at[idx, "Entry"] = round(float(row["Open"]), 2)
        results.at[idx, "Status"] = "Open"
        results.at[idx, "Taken"] = "Yes"
        changed = True
        print(f"Filled entry: {ticker} @ {row['Open']:.2f} on {bar_date.date()}")

    # 2. Check open positions against stop / target / time exit
    for idx in results.index[results["Status"] == "Open"]:
        ticker = results.at[idx, "Ticker"]
        bar = fetch_latest_bar(ticker)
        if bar is None:
            continue
        row, bar_date = bar
        entry_date = results.at[idx, "EntryDate"]
        if pd.isna(entry_date) or bar_date < entry_date:
            continue

        stop = results.at[idx, "StopLoss"]
        target = results.at[idx, "Target"]
        entry_price = results.at[idx, "Entry"]
        days_held = (bar_date - entry_date).days

        outcome, exit_price = None, None
        if row["Low"] <= stop:
            outcome, exit_price = "Stop", stop
        elif row["High"] >= target:
            outcome, exit_price = "Target", target
        elif days_held >= cfg["max_hold_days"]:
            outcome, exit_price = "TimeExit", round(float(row["Close"]), 2)

        if outcome:
            results.at[idx, "ExitDate"] = bar_date
            results.at[idx, "Exit"] = exit_price
            results.at[idx, "Outcome"] = outcome
            results.at[idx, "Status"] = "Closed"
            results.at[idx, "Return"] = round(exit_price - entry_price, 2)
            results.at[idx, "Return%"] = round((exit_price - entry_price) / entry_price * 100, 2)
            changed = True
            print(f"Closed: {ticker} -> {outcome} @ {exit_price:.2f}")

    if changed:
        results.to_csv(RESULTS_PATH, index=False)
        print(f"\nSaved updates to {RESULTS_PATH}")
    else:
        print("\nNo updates today.")


if __name__ == "__main__":
    main()
