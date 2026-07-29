"""
Entry scanning (Strategy B: 100 DMA trend filter, 20 EMA momentum setup,
volume-confirmed Touch & Bounce) + incremental position/exit management
(3xATR trailing stop, ratchets up only / 20 SMA structural exit).

Golden Cross entries are intentionally OFF by default — the backtest showed
they're barely breakeven (profit factor ~1.0-1.05, avg gain 0.08-0.14% per
trade), which is smaller than realistic NSE round-trip trading costs
(~0.2-0.5%). Flip ENABLE_GOLDEN_CROSS to True below if you want them anyway.
"""
import numpy as np
import pandas as pd

from .indicators import prepare

ENABLE_GOLDEN_CROSS = False
ENABLE_BOUNCE = True
BOUNCE_TOLERANCE_PCT = 0.015
ATR_TRAIL_MULT = 3.0


def scan_new_entry(symbol, raw_df):
    """
    Evaluates ONLY the latest completed daily bar (day T) — this is a live
    scanner, not a backtest. Per the spec's execution rule: the signal is
    locked at close of T; actual entry happens at the Open of T+1 (handled
    by the PENDING -> OPEN state transition in the tracker, not here).
    Returns a signal dict or None.
    """
    if raw_df.empty or len(raw_df) < 130:
        return None
    df = prepare(raw_df)
    i = len(df) - 1

    trend_ma, fast_ma = df["DMA100"].values, df["EMA20"].values
    close, volume, vol_sma20, atr = df["Close"].values, df["Volume"].values, df["VolSMA20"].values, df["ATR14"].values

    if np.isnan(trend_ma[i]) or np.isnan(fast_ma[i]) or np.isnan(atr[i]) or np.isnan(vol_sma20[i]):
        return None

    # Layer 1: macro regime filter
    if close[i] <= trend_ma[i]:
        return None
    # Layer 2: volume confirmation (mandatory per spec)
    if volume[i] <= vol_sma20[i]:
        return None

    # Layer 3: trigger setup
    golden_cross = ENABLE_GOLDEN_CROSS and (fast_ma[i - 1] <= trend_ma[i - 1]) and (fast_ma[i] > trend_ma[i])
    touch_and_bounce = ENABLE_BOUNCE and (
        abs(fast_ma[i] - trend_ma[i]) / trend_ma[i] <= BOUNCE_TOLERANCE_PCT
    ) and (fast_ma[i] >= fast_ma[i - 1])

    if not (golden_cross or touch_and_bounce):
        return None

    return {
        "symbol": symbol,
        "signal_date": df.index[i],
        "signal_close": float(close[i]),
        "atr_at_signal": float(atr[i]),
        "entry_type": "Golden Cross" if golden_cross else "Touch & Bounce",
    }


def confirm_pending_entry(raw_df, signal_date):
    """
    For a PENDING row: checks whether the trading day AFTER signal_date has
    now occurred and has data, and if so returns its actual Open price —
    the real fill price per the spec's T -> T+1-Open execution rule.
    Returns (entry_date, entry_price) or (None, None) if T+1 hasn't happened yet.
    """
    if raw_df.empty:
        return None, None
    idx = raw_df.index
    after = idx[idx > signal_date]
    if len(after) == 0:
        return None, None
    entry_date = after[0]
    entry_price = float(raw_df.loc[entry_date, "Open"])
    return entry_date, entry_price


def update_open_position(raw_df, entry_price, prev_highest_close, prev_trailing_stop):
    """
    Incremental daily update for an OPEN position, using ONLY today's bar
    plus yesterday's tracked state (matches how a trader actually manages
    a position day-to-day — no need to replay full history each run).

    Returns a dict: status ("OPEN"/"EXITED"), today's close, updated
    highest_close, updated trailing_stop, and exit info if triggered.
    """
    df = prepare(raw_df)
    i = len(df) - 1
    if np.isnan(df["ATR14"].iloc[i]) or np.isnan(df["SMA20"].iloc[i]):
        return None

    close_t = float(df["Close"].iloc[i])
    low_t = float(df["Low"].iloc[i])
    atr_t = float(df["ATR14"].iloc[i])
    sma20_t = float(df["SMA20"].iloc[i])
    date_t = df.index[i]

    highest_close = max(prev_highest_close, close_t)
    candidate_trail = highest_close - ATR_TRAIL_MULT * atr_t
    trailing_stop = max(prev_trailing_stop, candidate_trail)  # only ratchets up, never down

    exit_reason, exit_price = None, None
    if low_t <= trailing_stop:
        exit_reason, exit_price = f"Trailing stop loss ({ATR_TRAIL_MULT:.1f}xATR)", trailing_stop
    elif close_t < sma20_t:
        exit_reason, exit_price = "Price crossed below 20 SMA", close_t

    return {
        "date": date_t,
        "current_price": close_t,
        "highest_close": highest_close,
        "trailing_stop": round(trailing_stop, 2),
        "sma20": round(sma20_t, 2),
        "status": "EXITED" if exit_reason else "OPEN",
        "exit_reason": exit_reason,
        "exit_price": round(exit_price, 2) if exit_price is not None else None,
    }
