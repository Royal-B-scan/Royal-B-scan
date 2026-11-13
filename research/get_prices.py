"""Price download for the Phase 1 tests (Nov 12, 2026). Writes px.pkl next to this file, in the shape shakeout_bt.py
reads: daily bars, adjusted, columns (ticker, Open/High/Low/Close/Volume), Jan 2022 to today.

Universe (the one research/shakeout-backtest.md used): S&P 500 + S&P/TSX 60 + 10 big foreign stocks.
The lists are today's members, so companies that left the indexes are missing (survivorship bias): treat
absolute returns as optimistic; comparisons against the random baseline on the same stocks are still fair.

    python get_prices.py            download everything (about 5 minutes)
"""
import io
import json
import os
import sys
import time

import pandas as pd
import requests
import yfinance as yf

HERE = os.path.dirname(os.path.abspath(__file__))
UA = {"User-Agent": "Mozilla/5.0 (price research script)"}
FOREIGN = ["TSM", "ASML", "ARM", "SHOP", "SAP", "NVO", "BABA", "PDD", "MELI", "SE"]
BENCH = ["SPY", "XIU.TO"]


def wiki_table(url: str, col_options: tuple[str, ...]) -> pd.DataFrame:
    html = requests.get(url, headers=UA, timeout=30).text
    for t in pd.read_html(io.StringIO(html), keep_default_na=False)   # keep_default_na: National Bank's ticker is "NA":
        for c in col_options:
            if c in t.columns and len(t) >= 50:
                return t.rename(columns={c: "Symbol"})
    raise RuntimeError(f"no ticker table found at {url}")


def universe() -> pd.DataFrame:
    sp = wiki_table("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", ("Symbol",))
    sp["ticker"] = sp["Symbol"].astype(str).str.strip().str.replace(".", "-", regex=False)
    sp["sector"] = sp.get("GICS Sector", "")
    sp["industry"] = sp.get("GICS Sub-Industry", "")
    sp["name"] = sp.get("Security", sp["ticker"])
    sp["group"] = "SP500"
    tsx = wiki_table("https://en.wikipedia.org/wiki/S%26P/TSX_60", ("Symbol", "Ticker"))
    tsx["ticker"] = tsx["Symbol"].astype(str).str.strip().str.replace(".", "-", regex=False) + ".TO"
    tsx["sector"] = tsx.get("Sector", "")
    tsx["industry"] = ""
    tsx["name"] = tsx.get("Company", tsx["ticker"])
    tsx["group"] = "TSX60"
    extra = pd.DataFrame({"ticker": FOREIGN, "sector": "", "industry": "", "name": FOREIGN, "group": "FOREIGN"})
    cols = ["ticker", "name", "sector", "industry", "group"]
    return pd.concat([sp[cols], tsx[cols], extra]).drop_duplicates("ticker").reset_index(drop=True)


def main() -> int:
    uni = universe()
    print(f"universe: {len(uni)} stocks ({(uni.group == 'SP500').sum()} S&P 500, {(uni.group == 'TSX60').sum()} TSX 60, "
          f"{(uni.group == 'FOREIGN').sum()} foreign)", flush=True)
    uni = uni[uni["ticker"].apply(lambda t: isinstance(t, str) and bool(t.strip()) and not t.lower().startswith("nan"))]
    uni.to_csv(os.path.join(HERE, "universe.csv"), index=False)
    tickers = uni["ticker"].tolist() + BENCH
    parts, missing = [], []
    for i in range(0, len(tickers), 100):
        chunk = tickers[i:i + 100]
        for attempt in range(3):
            try:
                d = yf.download(chunk, start="2022-01-01", interval="1d", group_by="ticker", auto_adjust=True,
                                threads=True, progress=False)
                break
            except Exception as e:  # noqa: BLE001
                print(f"  retry {attempt + 1}: {e}", file=sys.stderr)
                time.sleep(5 + attempt * 10)
        else:
            missing += chunk
            continue
        for t in chunk:
            try:
                df = d[t].dropna(subset=["Close"])[["Open", "High", "Low", "Close", "Volume"]]
            except KeyError:
                missing.append(t)
                continue
            if len(df) < 50:
                missing.append(t)
                continue
            df.columns = pd.MultiIndex.from_product([[t], df.columns])
            parts.append(df)
        print(f"  {min(i + 100, len(tickers))}/{len(tickers)}", flush=True)
        time.sleep(1)
    px = pd.concat(parts, axis=1, sort=True).sort_index()
    px.to_pickle(os.path.join(HERE, "px.pkl"))
    with open(os.path.join(HERE, "px_info.json"), "w") as fh:
        json.dump({"tickers": int(px.columns.get_level_values(0).nunique()), "first": str(px.index[0].date()),
                   "last": str(px.index[-1].date()), "missing": missing}, fh, indent=1)
    print(f"saved px.pkl: {px.columns.get_level_values(0).nunique()} tickers, {px.index[0].date()} to {px.index[-1].date()}, "
          f"missing {len(missing)}: {missing[:15]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
