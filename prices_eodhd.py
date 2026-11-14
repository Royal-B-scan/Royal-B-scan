"""
Daily prices from EODHD for the whole-market universe (whole-market plan, step 2, Nov 13 2026).

    python prices_eodhd.py --history        two years of daily bars for every stock in research/universe_eodhd.csv
                                            (one request each, 10 at a time) -> data/px_eodhd.pkl
    python prices_eodhd.py --update DATE    add one day for the whole US and Toronto (two bulk requests); checks the
                                            row count, because right after the close the day's file is still filling

Saved like the Scout's Yahoo cache (data/px_cache.pkl): columns (ticker, Open/High/Low/Close/Volume), split- and
dividend-adjusted (open/high/low scaled by adjusted_close / close, as Yahoo's auto_adjust does).
Tickers in Yahoo style: US as is (BRK-B), Toronto with .TO.
Key: ~/Documents/Stock Screener/.eodhd_key (Mac) or env EODHD_API_KEY (cloud). Never printed.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import os
import sys
import time
from datetime import date, timedelta

import pandas as pd
import requests

from universe_eodhd import key

HERE = os.path.dirname(os.path.abspath(__file__))
UNI = os.path.join(HERE, "research", "universe_eodhd.csv")
PX = os.path.join(HERE, "data", "px_eodhd.pkl")
COLS = ["Open", "High", "Low", "Close", "Volume"]


def eod_code(t: str) -> str:
    return t[:-3] + ".TO" if t.endswith(".TO") else t + ".US"


def adjust(df: pd.DataFrame) -> pd.DataFrame:
    f = (df["adjusted_close"] / df["close"]).where(df["close"] > 0, 1.0)
    out = pd.DataFrame({"Open": df["open"] * f, "High": df["high"] * f, "Low": df["low"] * f,
                        "Close": df["adjusted_close"], "Volume": df["volume"]})
    out.index = pd.to_datetime(df["date"])
    return out


def one(t: str, start: str, k: str) -> tuple[str, pd.DataFrame | None]:
    for attempt in range(4):
        try:
            r = requests.get(f"https://eodhd.com/api/eod/{eod_code(t)}",
                             params={"api_token": k, "fmt": "json", "from": start}, timeout=60)
            if r.status_code == 404:
                return t, None
            r.raise_for_status()
            d = pd.DataFrame(r.json())
            return t, (adjust(d) if len(d) else None)
        except Exception as e:  # noqa: BLE001
            time.sleep((12 if "429" in str(e) else 2) + 4 * attempt)   # 429 = EODHD's per-minute limit
    return t, None


def history(tickers: list[str], years: int = 2) -> tuple[pd.DataFrame, list[str]]:
    start = (date.today() - timedelta(days=365 * years + 10)).isoformat()
    k = key()
    parts, missing = {}, []
    with cf.ThreadPoolExecutor(max_workers=6) as ex:
        for t, df in ex.map(lambda t: one(t, start, k), tickers):
            if df is None or len(df) < 60:
                missing.append(t)
            else:
                parts[t] = df
    px = pd.concat(parts, axis=1).sort_index()
    return px, missing


def update(day: str) -> pd.DataFrame:
    """Append one day from the two bulk files. Stops if a file looks incomplete."""
    px = pd.read_pickle(PX)
    want = set(px.columns.get_level_values(0))
    k = key()
    rows = {}
    for ex, min_rows in (("US", 20000), ("TO", 1500)):
        d = requests.get(f"https://eodhd.com/api/eod-bulk-last-day/{ex}",
                         params={"api_token": k, "fmt": "json", "date": day}, timeout=180).json()
        if len(d) < min_rows:
            raise SystemExit(f"STOPPED: EODHD's {ex} file for {day} has only {len(d)} rows; try again later.")
        for x in d:
            t = x["code"] + (".TO" if ex == "TO" else "")
            if t in want and x.get("close"):
                f = x["adjusted_close"] / x["close"]
                rows[t] = [x["open"] * f, x["high"] * f, x["low"] * f, x["adjusted_close"], x["volume"]]
    new = pd.DataFrame({(t, c): [v[i]] for t, v in rows.items() for i, c in enumerate(COLS)}, index=[pd.Timestamp(day)])
    px = pd.concat([px[px.index != pd.Timestamp(day)], new]).sort_index()
    px.to_pickle(PX)
    print(f"added {day}: {len(rows)} of {len(want)} stocks")
    return px


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--history", action="store_true")
    ap.add_argument("--update", metavar="YYYY-MM-DD")
    a = ap.parse_args()
    if a.history:
        tickers = pd.read_csv(UNI).ticker.tolist()
        t0 = time.time()
        px, missing = history(tickers)
        os.makedirs(os.path.dirname(PX), exist_ok=True)
        px.to_pickle(PX)
        n = len(set(px.columns.get_level_values(0)))
        print(f"wrote {PX}: {n} of {len(tickers)} stocks, {px.index[0].date()} to {px.index[-1].date()}, "
              f"{round(time.time() - t0)}s. Missing: {len(missing)} {missing[:20]}")
    if a.update:
        update(a.update)
    return 0


if __name__ == "__main__":
    sys.exit(main())
