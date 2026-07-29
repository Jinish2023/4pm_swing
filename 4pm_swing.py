"""
4pm_swing — Hybrid Trend-Following & Volatility-Stop System (Strategy B)
──────────────────────────────────────────────────────────────────────────
Daily flow, meant to run once after market close (hence the name):

  1. Load every symbol currently tracked (PENDING ENTRY or OPEN) in the
     Excel tracker, fetch fresh data for each, and advance its state:
       PENDING ENTRY -> OPEN        (once the actual T+1 open is known)
       OPEN          -> OPEN        (trailing stop/highest-close updated)
       OPEN          -> EXITED      (3xATR trailing stop or 20 SMA broken)
  2. Scan the rest of the universe (everyone NOT already tracked, so we
     never duplicate a live setup) for fresh Layer 1-3 signals and log them
     as new PENDING ENTRY rows.
  3. Rebuild the Dashboard sheet's summary cards.

This fixes the two core gaps from the previous version: positions are now
actually monitored day-to-day against the strategy's own exit rule (not
just logged once and forgotten), and entries use the real T+1 open price
per the spec's execution-timing rule, not same-day close.

Run with:  python 4pm_swing.py
"""
import os
import sys
import time

import pandas as pd
import yfinance as yf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.strategy import scan_new_entry, confirm_pending_entry, update_open_position
from src.tracker import (
    get_tracked_symbols, get_tracked_rows_full, append_pending_signals,
    update_tracked_rows, rebuild_dashboard,
)

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


def fetch(symbol):
    ticker = f"{symbol}.NS"
    df = yf.download(ticker, period="1y", interval="1d", auto_adjust=True, progress=False)
    return _flatten_columns(df)


def trading_days_held(raw_df, entry_date, latest_date):
    try:
        i0 = raw_df.index.get_loc(entry_date)
        i1 = raw_df.index.get_loc(latest_date)
        return int(i1 - i0)
    except Exception:
        return None


def process_tracked_positions():
    tracked = get_tracked_rows_full(EXCEL_FILE)
    if not tracked:
        print("No tracked (PENDING/OPEN) positions to update.")
        return
    print(f"Updating {len(tracked)} tracked position(s)...")

    updates = {}
    for r, state in tracked.items():
        symbol = state["symbol"]
        try:
            raw_df = fetch(symbol)
        except Exception as e:
            print(f"  [{symbol}] fetch failed ({e}), skipping this run.")
            continue
        if raw_df.empty:
            continue

        if state["status"] == "PENDING ENTRY":
            entry_date, entry_price = confirm_pending_entry(raw_df, state["signal_date"])
            if entry_date is None:
                print(f"  [{symbol}] still PENDING — T+1 hasn't traded yet.")
                continue
            atr_signal = state["atr_signal"]
            initial_stop = round(entry_price - 3.0 * atr_signal, 2)
            updates[r] = {
                "status": "OPEN", "entry_date": entry_date.strftime("%d/%m/%Y"),
                "entry_price": round(entry_price, 2), "initial_stop": initial_stop,
                "current_price": round(entry_price, 2), "highest_close": round(entry_price, 2),
                "trailing_stop": initial_stop, "pnl_rs": 0.0, "pnl_pct": 0.0, "days_held": 0,
            }
            print(f"  [{symbol}] PENDING -> OPEN, entry confirmed @ Rs.{entry_price:.2f}")

        elif state["status"] == "OPEN":
            result = update_open_position(raw_df, state["entry_price"], state["highest_close"], state["trailing_stop"])
            if result is None:
                continue
            days_held = trading_days_held(raw_df, state["entry_date"], result["date"]) or 0
            entry_price = state["entry_price"]

            if result["status"] == "EXITED":
                exit_price = result["exit_price"]
                pnl_rs = round(exit_price - entry_price, 2)
                pnl_pct = round((exit_price / entry_price - 1), 4)
                updates[r] = {
                    "status": "EXITED", "current_price": exit_price, "highest_close": result["highest_close"],
                    "trailing_stop": result["trailing_stop"], "sma20": result["sma20"],
                    "pnl_rs": pnl_rs, "pnl_pct": pnl_pct, "exit_date": result["date"].strftime("%d/%m/%Y"),
                    "exit_price": exit_price, "exit_reason": result["exit_reason"], "days_held": days_held,
                }
                print(f"  [{symbol}] OPEN -> EXITED ({result['exit_reason']}) @ Rs.{exit_price:.2f}, P&L {pnl_pct*100:+.2f}%")
            else:
                pnl_rs = round(result["current_price"] - entry_price, 2)
                pnl_pct = round((result["current_price"] / entry_price - 1), 4)
                updates[r] = {
                    "current_price": result["current_price"], "highest_close": result["highest_close"],
                    "trailing_stop": result["trailing_stop"], "sma20": result["sma20"],
                    "pnl_rs": pnl_rs, "pnl_pct": pnl_pct, "days_held": days_held,
                }
        time.sleep(0.15)

    update_tracked_rows(EXCEL_FILE, updates)


def scan_for_new_signals():
    if USE_FULL_NIFTY500:
        try:
            from src.universe import fetch_stock_universe
            universe = fetch_stock_universe()
        except Exception as e:
            print(f"Could not load full NIFTY 500 list ({e}). Using fallback.")
            universe = FALLBACK_UNIVERSE
    else:
        universe = FALLBACK_UNIVERSE

    already_tracked = set(get_tracked_symbols(EXCEL_FILE).keys())
    scan_list = [s for s in universe if s not in already_tracked]
    print(f"\nScanning {len(scan_list)} untracked symbols for new signals "
          f"({len(already_tracked)} already tracked, skipped)...")

    new_signals = []
    for i, symbol in enumerate(scan_list):
        try:
            raw_df = fetch(symbol)
            sig = scan_new_entry(symbol, raw_df)
            if sig:
                new_signals.append(sig)
                print(f"  [SIGNAL] {symbol} — {sig['entry_type']} @ Rs.{sig['signal_close']:.2f} "
                      f"(buy tomorrow's open if it holds)")
        except Exception as e:
            print(f"  [{i+1}/{len(scan_list)}] {symbol}: failed ({e})")
        time.sleep(0.15)

    if new_signals:
        append_pending_signals(EXCEL_FILE, new_signals)
    print(f"\nNew signals logged: {len(new_signals)}")


def main():
    print("=" * 70)
    print("4PM SWING — daily update")
    print("=" * 70)
    process_tracked_positions()
    scan_for_new_signals()
    rebuild_dashboard(EXCEL_FILE)
    print(f"\nDone. See {EXCEL_FILE} (Dashboard + Positions sheets).")


if __name__ == "__main__":
    main()
