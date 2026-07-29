"""
Stock universe — tries to pull the live NSE 500 list first (free CSV, no
key). Falls back to a hardcoded liquid-stock list if that fetch fails
(NSE's site is flaky for scripted requests without a browser session).
"""
import io
import requests
import pandas as pd

NIFTY500_CSV_URL = "https://nsearchives.nseindia.com/content/indices/ind_nifty500list.csv"

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


def fetch_stock_universe():
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        resp = requests.get(NIFTY500_CSV_URL, headers=headers, timeout=15)
        if resp.status_code == 200 and "Symbol" in resp.text:
            df = pd.read_csv(io.StringIO(resp.text))
            symbols = df["Symbol"].dropna().astype(str).str.strip().tolist()
            if len(symbols) > 100:
                print(f"  Loaded live NIFTY 500 list ({len(symbols)} symbols).")
                return symbols
    except Exception as e:
        print(f"  Live universe fetch failed ({e}), using fallback list.")
    print(f"  Using fallback universe ({len(FALLBACK_UNIVERSE)} symbols).")
    return FALLBACK_UNIVERSE
