"""
Universe Loader for NIFTY 500 Stocks
──────────────────────────────────────────────────────────────────────────
Fetches the current Nifty 500 symbols dynamically for use in technical scanners.
"""
import pandas as pd

def fetch_stock_universe():
    """
    Fetches the Nifty 500 stock symbols from official or reliable index sources.
    Returns a clean list of stock ticker symbols (without .NS suffix, as the 
    scanner adds it automatically).
    """
    try:
        # Nifty 500 constituents official index CSV/URL mapping or fallback web source
        url = "https://archives.nseindia.com/content/indices/ind_nifty500list.csv"
        
        # NSE requires a user-agent header to prevent HTTP 403 Forbidden errors
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        df = pd.read_csv(url, storage_options={"User-Agent": headers["User-Agent"]})
        
        if "Symbol" in df.columns:
            symbols = df["Symbol"].dropna().astype(str).str.strip().tolist()
            # Clean up any weird formatting if present
            symbols = [s.upper() for s in symbols if s]
            if len(symbols > 100):
                print(f"Successfully loaded {len(symbols)} symbols from NSE Nifty 500 index.")
                return symbols
    except Exception as e:
        print(f"Warning: Could not fetch live Nifty 500 list from NSE archive ({e}). Using backup source.")

    # Alternative backup endpoint via Git/GitHub raw mirrors or standard major indices if NSE blocks connection
    try:
        alt_url = "https://raw.githubusercontent.com/raghavtwenty/swagger-nse-feed/main/nifty_500.csv"
        df_alt = pd.read_csv(alt_url)
        symbol_col = "Symbol" if "Symbol" in df_alt.columns else df_alt.columns[0]
        symbols = df_alt[symbol_col].dropna().astype(str).str.strip().tolist()
        if len(symbols) > 100:
            return [s.upper() for s in symbols]
    except Exception:
        pass

    # Final hardcoded safety net if all network fetches fail
    from main import FALLBACK_UNIVERSE
    return FALLBACK_UNIVERSE

if __name__ == "__main__":
    univ = fetch_stock_universe()
    print(f"Total universe count: {len(univ)}")
