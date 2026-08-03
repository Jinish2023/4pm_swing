==================================================
UNIVERSE: 473 tickers with valid setups
TOTAL TRADES: 3783
WIN RATE: 50.9%
AVG WIN: 17.15%    AVG LOSS: -9.88%
PROFIT FACTOR: 1.80
EXPECTANCY PER TRADE: 3.87%
==================================================


# Swing Strategy Scanner + Tracker

Automates the fib-retracement + order-block/base breakout swing strategy:
scans NSE stocks for fresh setups, and tracks open positions to stop/target,
entirely through GitHub Actions.

## Strategy recap
1. Impulse leg up (min 15% move by default)
2. Pullback into the 38.2%-61.8% fib zone
3. Base/consolidation forms after the pullback
4. Entry: breakout above base high (with volume confirmation)
5. Stop: below base low. Target: measured move of the impulse leg.

All thresholds live in `strategy_core.py` under `CONFIG` -- tune freely.

## One-time setup

1. Create a new GitHub repo and push all these files to it.
2. **Replace `tickers.csv`** with the full NSE 500 list (the included one
   is just a 20-stock sample so you can test quickly):
   ```
   pip install -r requirements.txt
   python fetch_tickers.py
   ```
   This downloads the live NSE 500 list and overwrites `tickers.csv`.
   Commit the updated file. Re-run this every few months to keep the
   universe current (index constituents change periodically).
3. In your repo: **Settings -> Actions -> General -> Workflow permissions**
   -> select **"Read and write permissions"**. This lets the workflow
   commit `results.csv` back to the repo after each run.

## Running it

Go to the **Actions** tab -> **Swing Strategy Bot** -> **Run workflow**,
and choose:

- **scan** -- scans every ticker in `tickers.csv` for a FRESH breakout
  (i.e. the breakout happened on the most recent trading day). New
  candidates are appended to `results.csv` with `Status = Pending` and
  `Taken = No`. A ticker is skipped if it already has a pending
  candidate, or was entered within the last 5 days (`dedup_days` in
  `strategy_core.py`) -- so you won't get duplicate flags.

- **track** -- does two things:
  1. Fills any `Pending` candidate at the next available day's open
     price, flips it to `Status = Open`, `Taken = Yes`.
  2. Checks every `Open` position's latest bar against its stop/target,
     closing it out (`Status = Closed`) if hit, or via a time-based
     exit after `max_hold_days` (default 60).

It's also scheduled to run automatically on weekdays (scan ~3:35pm IST,
track ~3:50pm IST) -- edit the cron lines in
`.github/workflows/swing_bot.yml` if you want different timing (times
are in UTC; IST = UTC+5:30).

## Output: results.csv

| Column | Meaning |
|---|---|
| SerialNo | Sequential ID |
| ScanDate | Date the setup was first flagged |
| Ticker | NSE symbol (.NS suffix) |
| Status | Pending / Open / Closed |
| Strategy | Plain-English justification (impulse leg, pullback %, base range, breakout date) |
| EntryDate / Entry | Filled at next-day open once taken |
| StopLoss / Target | From base low / measured move |
| ExitDate / Exit / Outcome | Stop / Target / TimeExit, once closed |
| Return / Return% | Absolute and % P&L once closed |
| Taken | No while still Pending, Yes once entered |
| LegLow / LegHigh / BaseLow / BaseHigh | Reference values used to compute stop/target |

This one file serves as both your **live candidate list** and your
**trade journal** -- nothing else to maintain.

## Honest limitations
- No position sizing or portfolio-level capital limits here -- this is
  a signal generator + tracker, not a portfolio simulator. Pair it with
  the `portfolio_simulator.py` from your backtest if you want to reason
  about realistic capital allocation across concurrent signals.
- Data quality depends entirely on Yahoo Finance / yfinance uptime.
- NSE's ticker-list endpoint can change or block requests without
  warning -- if `fetch_tickers.py` breaks, get the CSV manually from
  niftyindices.com.
