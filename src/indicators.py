"""
Indicator set for the Hybrid Trend-Following & Volatility-Stop System
(Strategy B: 100 DMA trend filter / 20 EMA momentum setup).
"""
import pandas as pd


def _flatten_columns(df):
    """yfinance sometimes returns MultiIndex columns even for a single
    ticker — flatten to plain Open/High/Low/Close/Volume regardless."""
    if isinstance(df.columns, pd.MultiIndex):
        df = df.copy()
        df.columns = df.columns.get_level_values(0)
    return df


def compute_atr(df, period=14):
    high, low, close = df["High"], df["Low"], df["Close"]
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def prepare(df):
    df = df.copy()
    df["DMA100"] = df["Close"].rolling(100).mean()
    df["EMA20"] = df["Close"].ewm(span=20, adjust=False).mean()
    df["SMA20"] = df["Close"].rolling(20).mean()
    df["ATR14"] = compute_atr(df, 14)
    df["VolSMA20"] = df["Volume"].rolling(20).mean()
    return df
