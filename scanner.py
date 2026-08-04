"""
Scanner: scans the ticker universe for FRESH breakout setups and appends
them to results.csv as "Pending" rows (not yet entered).

Run AFTER market close each trading day. The GitHub Actions workflow
runs this automatically, or trigger it manually with mode=scan.
"""
from datetime import datetime
from pathlib import Path

import pandas as pd
import yfinance as yf

from strategy_core import CONFIG, find_live_signal, market_session_finalized

RESULTS_PATH = Path("results.csv")
TICKERS_PATH = Path("tickers.csv")

COLUMNS = [
    "SerialNo", "ScanDate", "Ticker", "Status", "Strategy",
    "EntryDate", "Entry", "StopLoss", "Target",
    "ExitDate", "Exit", "Outcome", "Return", "Return%", "Taken",
    "LegLow", "LegHigh", "BaseLow", "BaseHigh",
]


def load_results():
    if RESULTS_PATH.exists():
        df = pd.read_csv(RESULTS_PATH)
        for col in ["ScanDate", "EntryDate", "ExitDate"]:
            df[col] = pd.to_datetime(df[col], errors="coerce")
        return df
    return pd.DataFrame(columns=COLUMNS)


def load_tickers():
    df = pd.read_csv(TICKERS_PATH)
    col = "Symbol" if "Symbol" in df.columns else df.columns[0]
    syms = df[col].astype(str).str.strip().tolist()
    return [s if s.endswith(".NS") else s + ".NS" for s in syms if s]


def already_flagged_recently(results, ticker, today, dedup_days):
    """True if we should SKIP this ticker (already pending, or entered recently)."""
    if results.empty:
        return False
    sub = results[results["Ticker"] == ticker]
    if sub.empty:
        return False
    if (sub["Taken"] == "No").any():
        return True  # already have an unresolved pending candidate
    entered = sub.dropna(subset=["EntryDate"])
    if entered.empty:
        return False
    recent = entered[(today - entered["EntryDate"]).dt.days <= dedup_days]
    return not recent.empty


def main():
    if not market_session_finalized():
        print("Refusing to scan: today's NSE session isn't finalized yet "
              "(before 3:35pm IST on a weekday). Running now would read partial "
              "intraday Close/Volume and could flag a false breakout that locks "
              "in via the dedup rule. Run this again after market close.")
        return

    cfg = CONFIG
    results = load_results()
    tickers = load_tickers()
    today = pd.Timestamp(datetime.now().date())

    print(f"Scanning {len(tickers)} tickers for fresh breakout setups...")
    new_rows = []
    serial_start = (
        int(results["SerialNo"].max()) + 1
        if not results.empty and results["SerialNo"].notna().any() else 1
    )

    for i, ticker in enumerate(tickers):
        try:
            if already_flagged_recently(results, ticker, today, cfg["dedup_days"]):
                continue

            df = yf.download(ticker, period="2y", auto_adjust=True, progress=False)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            df = df.dropna()
            if df.empty:
                continue

            signal = find_live_signal(df, cfg)
            if signal is None:
                continue

            new_rows.append({
                "SerialNo": serial_start + len(new_rows),
                "ScanDate": today,
                "Ticker": ticker,
                "Status": "Pending",
                "Strategy": signal["strategy_text"],
                "EntryDate": pd.NaT,
                "Entry": None,
                "StopLoss": round(signal["stop_price"], 2),
                "Target": round(signal["target_price"], 2),
                "ExitDate": pd.NaT,
                "Exit": None,
                "Outcome": None,
                "Return": None,
                "Return%": None,
                "Taken": "No",
                "LegLow": round(signal["leg_low"], 2),
                "LegHigh": round(signal["leg_high"], 2),
                "BaseLow": round(signal["base_low"], 2),
                "BaseHigh": round(signal["base_high"], 2),
            })
            print(f"  [{i+1}/{len(tickers)}] {ticker}: NEW CANDIDATE")
        except Exception as e:
            print(f"  [{i+1}/{len(tickers)}] {ticker}: error - {e}")
            continue

    if new_rows:
        results = pd.concat([results, pd.DataFrame(new_rows)], ignore_index=True)
        results.to_csv(RESULTS_PATH, index=False)
        print(f"\nAdded {len(new_rows)} new candidates. Saved to {RESULTS_PATH}")
    else:
        print("\nNo new candidates found today.")
        if not RESULTS_PATH.exists():
            results.to_csv(RESULTS_PATH, index=False)


if __name__ == "__main__":
    main()
