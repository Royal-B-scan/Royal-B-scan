"""
EODHD as the price source for Royal B's daily screen (Nov 14, 2026; handoff claude/eodhd-whole-market-handoff-2026-11-13.md).

Same two jobs as scan.py's Yahoo code, same shapes, so scan.py only swaps the source (env DATA_SOURCE=eodhd):
  get_universe()        every stock/ETF that passes Rules v1 (scan.py docstring), from one "extended" bulk file per
                        exchange (US, TSX, TSXV): type, market cap, 50-day average volume in the same request
  update_history(tick)  daily bars, split- and dividend-adjusted like Yahoo's auto_adjust. A stock new to the cache
                        gets ~14 months from /eod (1 request); after that one bulk file per exchange per day is added on
                        top (100 requests each). Stocks that split or paid a dividend that day are re-downloaded.
                        Kept in cache/history_eodhd.pkl (separate from Yahoo's cache, for the side-by-side).
Key: env EODHD_API_KEY (GitHub Secret of the same name), or ~/Documents/Stock Screener/.eodhd_key on Taylor's Mac.
Never printed or saved. About 300-400 requests a day after the first run (~3,500 once).
"""
from __future__ import annotations

import concurrent.futures as cf
import json
import os
import pickle
import re
import sys
import time
from datetime import date, datetime, timedelta

import pandas as pd
import requests

BASE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(BASE, "cache")
CACHE_FILE = os.path.join(CACHE, "history_eodhd.pkl")
SECTOR_FILE = os.path.join(CACHE, "sectors_eodhd.json")
API = "https://eodhd.com/api/"
EXCH = {"US": "", "TO": ".TO", "V": ".V"}              # EODHD exchange -> Yahoo-style suffix
US_STOCK = {"NYSE": "NYSE", "NASDAQ": "Nasdaq", "NYSE MKT": "NYSE American", "AMEX": "NYSE American"}
US_ETF = {**US_STOCK, "NYSE ARCA": "NYSE Arca", "BATS": "Cboe BZX"}
CA_NAME = {"TO": "TSX", "V": "TSXV"}
SECTORS = ["Technology", "Healthcare", "Financial Services", "Industrials", "Consumer Cyclical", "Consumer Defensive",
           "Communication Services", "Energy", "Basic Materials", "Real Estate", "Utilities"]


def _key() -> str:
    k = os.environ.get("EODHD_API_KEY")
    if not k:
        p = os.path.expanduser("~/Documents/Stock Screener/.eodhd_key")
        k = open(p).read() if os.path.exists(p) else ""
    if not k.strip():
        raise RuntimeError("EODHD_API_KEY is not set")
    return k.strip()


def _get(path: str, **params):
    params.update(api_token=_key(), fmt="json")
    for attempt in range(3):
        try:
            r = requests.get(API + path, params=params, timeout=180)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json()
        except Exception as e:  # noqa: BLE001
            if attempt == 2:
                raise
            busy = "429" in str(e)   # EODHD's per-minute limit: wait it out quietly
            if not busy:
                print(f"  EODHD retry {attempt + 1} ({path.split('/')[0]}): {str(e)[:80]}", file=sys.stderr)
            time.sleep((10 if busy else 3) + attempt * 10)


def yahoo(code: str, ex: str) -> str:
    return code + EXCH[ex]


def eod_code(t: str) -> str:
    for ex, suf in EXCH.items():
        if suf and t.endswith(suf):
            return t[: -len(suf)] + "." + ex
    return t + ".US"


def last_trading_day() -> str:
    """The newest day whose US bulk file is complete (row count check), searching back up to 7 days."""
    d = date.today()
    for _ in range(8):
        if d.weekday() < 5:
            rows = _get("eod-bulk-last-day/US", date=d.isoformat(), symbols="SPY,AAPL,MSFT")
            if rows and all(x.get("date") == d.isoformat() for x in rows) and len(rows) >= 3:
                full = _get("eod-bulk-last-day/TO", date=d.isoformat(), symbols="RY,TD,ENB")
                if full and len(full) >= 3:
                    return d.isoformat()
        d -= timedelta(days=1)
    raise RuntimeError("no complete EODHD day in the last week")


def sectors(refresh: bool = False) -> dict:
    """Ticker -> sector, from EODHD's screener (cached a week). Missing ones show as Other."""
    try:
        if not refresh and os.path.exists(SECTOR_FILE) and time.time() - os.path.getmtime(SECTOR_FILE) < 7 * 86400:
            return json.load(open(SECTOR_FILE))
    except Exception:  # noqa: BLE001
        pass
    out = {}
    for ex, exf in (("US", "us"), ("TO", "TO"), ("V", "V")):
        for sec in SECTORS + ["Financials"]:
            for lo, hi in ((3e8, 1e9), (1e9, 3e9), (3e9, 1e10), (1e10, 1e15)):
                for off in range(0, 1000, 100):
                    f = [["market_capitalization", ">", lo], ["market_capitalization", "<=", hi],
                         ["exchange", "=", exf], ["sector", "=", sec]]
                    d = (_get("screener", filters=json.dumps(f), limit=100, offset=off) or {}).get("data", [])
                    for r in d:
                        out[yahoo(r["code"], ex)] = "Financial Services" if sec == "Financials" else sec
                    if len(d) < 100:
                        break
    os.makedirs(CACHE, exist_ok=True)
    json.dump(out, open(SECTOR_FILE, "w"))
    return out


def get_universe(progress=lambda *a, **k: None, day: str | None = None):
    """Rules v1 universe from EODHD, same columns as scan.get_universe()."""
    from scan import CONFIG, LEVERAGED, _floor   # one source of truth for the rules
    day = day or last_trading_day()
    progress("Finding stocks", None, None, f"EODHD bulk files for {day}")
    sym = {}
    for s in _get("exchange-symbol-list/US") or []:
        sym[s["Code"]] = s.get("Exchange")
    sec = sectors()
    rows = []
    for ex in EXCH:
        for x in _get(f"eod-bulk-last-day/{ex}", date=day, filter="extended") or []:
            typ, px = x.get("type"), float(x.get("close") or 0)
            kind = "Stock" if typ == "Common Stock" else "ETF" if typ == "ETF" else None
            if not kind or px <= CONFIG["min_price"]:
                continue
            if ex == "US":
                exname = (US_STOCK if kind == "Stock" else US_ETF).get(sym.get(x["code"]))
                if not exname:
                    continue
            else:
                exname = CA_NAME[ex]
            cur = "USD" if ex == "US" else "CAD"
            mc = float(x.get("MarketCapitalization") or 0)
            if kind == "Stock" and mc <= CONFIG["min_market_cap"]:
                continue
            if kind == "ETF" and LEVERAGED.search(x.get("name") or ""):
                continue
            if px * float(x.get("avgvol_50d") or 0) < _floor(kind, cur) * 0.7:   # same 30% slack as the Yahoo pre-filter
                continue
            t = yahoo(x["code"], ex)
            rows.append({"ticker": t, "name": x.get("name") or t, "exchange": exname, "currency": cur,
                         "sector": "ETFs" if kind == "ETF" else sec.get(t, "Other"), "market_cap": mc, "kind": kind})
    for t, ex, nm in (("SPY", "NYSE Arca", "SPDR S&P 500"), ("XIU.TO", "TSX", "iShares S&P/TSX 60")):   # benchmarks
        if not any(r["ticker"] == t for r in rows):
            rows.append({"ticker": t, "name": nm, "exchange": ex, "currency": "CAD" if t.endswith(".TO") else "USD",
                         "sector": "ETFs", "market_cap": 0, "kind": "ETF"})
    uni = pd.DataFrame(rows).drop_duplicates("ticker").reset_index(drop=True)
    uni.attrs["day"] = day
    print(f"EODHD universe {day}: {len(uni)} ({(uni.kind == 'Stock').sum()} stocks, {(uni.kind == 'ETF').sum()} ETFs)")
    return uni


def _adjust(d: pd.DataFrame) -> pd.DataFrame:
    f = (d["adjusted_close"] / d["close"]).where(d["close"] > 0, 1.0)
    out = pd.DataFrame({"Open": d["open"] * f, "High": d["high"] * f, "Low": d["low"] * f,
                        "Close": d["adjusted_close"], "Volume": d["volume"].astype(float)})
    out.index = pd.to_datetime(d["date"])
    return out


def _one(t: str, start: str, end: str):
    try:
        d = _get(f"eod/{eod_code(t)}", **{"from": start, "to": end})
        return t, (_adjust(pd.DataFrame(d)) if d else None)
    except Exception:  # noqa: BLE001
        return t, None


def _bulk_day(day: str) -> dict:
    out = {}
    for ex in EXCH:
        for x in _get(f"eod-bulk-last-day/{ex}", date=day) or []:
            if x.get("close"):
                f = (x["adjusted_close"] or x["close"]) / x["close"]
                out[yahoo(x["code"], ex)] = [x["open"] * f, x["high"] * f, x["low"] * f, x["adjusted_close"] or x["close"], float(x["volume"] or 0)]
    return out


def _events(day: str) -> set:
    """Tickers with a split or dividend on that day: their past prices change, so they are re-downloaded."""
    hit = set()
    for ex in EXCH:
        for typ in ("splits", "dividends"):
            for x in _get(f"eod-bulk-last-day/{ex}", date=day, type=typ) or []:
                hit.add(yahoo(x.get("code", ""), ex))
    return hit


def update_history(tickers: list[str], progress=lambda *a, **k: None, day: str | None = None) -> dict:
    day = day or last_trading_day()
    try:
        cache = pickle.load(open(CACHE_FILE, "rb"))
    except Exception:  # noqa: BLE001
        cache = {}
    start = (pd.Timestamp(day) - pd.Timedelta(days=430)).date().isoformat()
    need = [t for t in tickers if t not in cache or len(cache[t]) < 60
            or (pd.Timestamp(day) - cache[t].index[-1]).days > 7]
    have = [t for t in tickers if t not in need]
    if have:
        last = min(cache[t].index[-1] for t in have)
        days = [d.date().isoformat() for d in pd.bdate_range(last + pd.Timedelta(days=1), day)]
        redo = set()
        for d in days:
            redo |= _events(d)
            bars = _bulk_day(d)
            for t in have:
                if t in bars and cache[t].index[-1] < pd.Timestamp(d):
                    row = pd.DataFrame([bars[t]], columns=["Open", "High", "Low", "Close", "Volume"], index=[pd.Timestamp(d)])
                    cache[t] = pd.concat([cache[t], row]).iloc[-300:]
        need += [t for t in have if t in redo]
    progress("Downloading prices", 0, len(need), None)
    with cf.ThreadPoolExecutor(max_workers=6) as ex:
        for i, (t, df) in enumerate(ex.map(lambda t: _one(t, start, day), need), 1):
            if df is not None and len(df):
                cache[t] = df.iloc[-300:]
            if i % 250 == 0:
                progress("Downloading prices", i, len(need), None)
    os.makedirs(CACHE, exist_ok=True)
    tmp = CACHE_FILE + ".tmp"
    pickle.dump(cache, open(tmp, "wb"), protocol=pickle.HIGHEST_PROTOCOL)
    os.replace(tmp, CACHE_FILE)
    print(f"EODHD history to {day}: {len(need)} downloaded per stock, {len(tickers) - len(need)} topped up from bulk files")
    return {t: cache[t] for t in tickers if t in cache}
