"""
Shared strategy logic for the swing scanner + tracker.

Core pattern:
  1. Impulse leg UP (swing low -> swing high), min % move.
  2. Pullback retraces into the 38.2%-61.8% fib zone.
  3. Base/consolidation forms after the pullback low.
  4. Entry trigger: breakout above the base high (with volume confirmation).
  5. Stop: below the base low.  Target: measured move (or fib extension).

find_live_signal() is the "live" version used for scanning: it only
returns a signal if the breakout happens on the VERY LAST bar of the
dataframe (i.e. today), so the scanner only flags fresh, actionable
setups -- not stale historical ones.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from scipy.signal import argrelextrema

IST = ZoneInfo("Asia/Kolkata")
MARKET_CLOSE_HOUR = 15
MARKET_CLOSE_MINUTE = 35  # 5 min buffer after NSE's actual 15:30 close


def market_session_finalized() -> bool:
    """
    Returns True only once today's NSE session data should be finalized
    (i.e. it's safe to trust Close/Volume as real end-of-day values).
    Guards scanner.py and tracker.py from acting on partial intraday bars.
    """
    now_ist = datetime.now(IST)
    if now_ist.weekday() >= 5:  # Saturday/Sunday
        return True  # no live session to worry about corrupting
    close_time = now_ist.replace(hour=MARKET_CLOSE_HOUR, minute=MARKET_CLOSE_MINUTE,
                                  second=0, microsecond=0)
    return now_ist >= close_time


CONFIG = dict(
    pivot_order=5,
    min_impulse_pct=0.15,
    retrace_lo=0.382,
    retrace_hi=0.618,
    base_window=5,
    breakout_lookahead=15,
    stop_buffer_pct=0.0,
    target_mode="measured",   # "measured" | "ext_1272" | "ext_1618"
    max_hold_days=60,
    volume_confirm=True,
    dedup_days=5,             # don't re-flag a ticker entered within this many days
)


def find_pivots(df, order):
    highs, lows = df["High"].values, df["Low"].values
    hi_idx = sorted(set(argrelextrema(highs, np.greater_equal, order=order)[0]))
    lo_idx = sorted(set(argrelextrema(lows, np.less_equal, order=order)[0]))
    return hi_idx, lo_idx


def find_live_signal(df: pd.DataFrame, cfg=CONFIG):
    """
    Look for a FRESH breakout signal on the most recent bar of df.
    Returns a dict describing the setup, or None if no fresh signal exists.
    """
    if len(df) < 60:
        return None

    hi_idx, lo_idx = find_pivots(df, cfg["pivot_order"])
    pivots = sorted([(i, "L") for i in lo_idx] + [(i, "H") for i in hi_idx])
    n = len(pivots)
    last_bar = len(df) - 1

    best = None  # keep the setup tied to the most recent impulse leg

    for a in range(n - 1):
        idx_low, type_low = pivots[a]
        if type_low != "L":
            continue
        idx_high, type_high = pivots[a + 1]
        if type_high != "H":
            continue

        leg_low = df["Low"].iloc[idx_low]
        leg_high = df["High"].iloc[idx_high]
        leg_range = leg_high - leg_low
        if leg_low <= 0 or leg_range / leg_low < cfg["min_impulse_pct"]:
            continue

        fib_hi_price = leg_high - cfg["retrace_lo"] * leg_range
        fib_lo_price = leg_high - cfg["retrace_hi"] * leg_range

        pullback_idx = None
        for b in range(a + 2, n):
            idx_p, type_p = pivots[b]
            if type_p == "H":
                if df["High"].iloc[idx_p] > leg_high:
                    break
                continue
            price_p = df["Low"].iloc[idx_p]
            if fib_lo_price <= price_p <= fib_hi_price:
                pullback_idx = idx_p
                break
            elif price_p < fib_lo_price:
                break
        if pullback_idx is None:
            continue

        base_start = pullback_idx
        base_end = min(pullback_idx + cfg["base_window"], len(df) - 1)
        if base_end <= base_start:
            continue
        base_high = df["High"].iloc[base_start:base_end + 1].max()
        base_low = df["Low"].iloc[base_start:base_end + 1].min()
        avg_vol20 = df["Volume"].iloc[max(0, base_start - 20):base_start].mean()

        # only accept if the breakout happens exactly on the LAST bar (today)
        search_start = base_end + 1
        search_end = min(base_end + 1 + cfg["breakout_lookahead"], len(df))
        if not (search_start <= last_bar < search_end):
            continue

        # make sure no earlier bar in the lookahead window already broke out
        # (otherwise this signal is stale, not fresh)
        already_broken = any(
            df["Close"].iloc[k] > base_high for k in range(search_start, last_bar)
        )
        if already_broken:
            continue

        close_last = df["Close"].iloc[last_bar]
        vol_last = df["Volume"].iloc[last_bar]
        vol_ok = (not cfg["volume_confirm"]) or (avg_vol20 == 0) or (vol_last > avg_vol20)

        if close_last > base_high and vol_ok:
            entry_price = close_last
            stop_price = base_low * (1 - cfg["stop_buffer_pct"])
            if cfg["target_mode"] == "ext_1272":
                target_price = leg_low + 1.272 * leg_range
            elif cfg["target_mode"] == "ext_1618":
                target_price = leg_low + 1.618 * leg_range
            else:
                target_price = entry_price + leg_range
            if stop_price >= entry_price or target_price <= entry_price:
                continue

            pullback_pct = (leg_high - df["Low"].iloc[pullback_idx]) / leg_range * 100
            strategy_text = (
                f"Impulse leg +{leg_range/leg_low*100:.1f}% from "
                f"{df.index[idx_low].date()} (Rs{leg_low:.2f}) to "
                f"{df.index[idx_high].date()} (Rs{leg_high:.2f}). "
                f"Pulled back to {pullback_pct:.1f}% fib zone on "
                f"{df.index[pullback_idx].date()} (Rs{df['Low'].iloc[pullback_idx]:.2f}). "
                f"Base formed {df.index[base_start].date()} to {df.index[base_end].date()} "
                f"(Rs{base_low:.2f}-Rs{base_high:.2f}). Breakout confirmed "
                f"{df.index[last_bar].date()} at Rs{close_last:.2f}"
                f"{' with volume above 20-day avg' if cfg['volume_confirm'] else ''}."
            )

            setup = dict(
                idx_high=idx_high,
                leg_low=float(leg_low), leg_high=float(leg_high),
                base_low=float(base_low), base_high=float(base_high),
                entry_price=float(entry_price), stop_price=float(stop_price),
                target_price=float(target_price),
                strategy_text=strategy_text,
                breakout_date=df.index[last_bar],
            )
            if best is None or idx_high > best["idx_high"]:
                best = setup

    if best is not None:
        best.pop("idx_high", None)
    return best
