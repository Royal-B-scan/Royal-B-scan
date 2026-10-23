"""
Next earnings date per ticker (Yahoo calendar), cached for 24 hours in cache/earnings.json.

days_to_earnings <= WARN_DAYS  -> warning badge in the app, and a heads-up email for stocks you hold.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import time
from datetime import date, datetime
from zoneinfo import ZoneInfo

BASE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(BASE, "cache", "earnings.json")
PT = ZoneInfo("America/Vancouver")
WARN_DAYS = 7
MAX_AGE = 24 * 3600


def _load() -> dict:
    try:
        with open(CACHE) as fh:
            return json.load(fh)
    except Exception:  # noqa: BLE001
        return {}


def _save(c: dict) -> None:
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    with open(CACHE + ".tmp", "w") as fh:
        json.dump(c, fh)
    os.replace(CACHE + ".tmp", CACHE)


def _reset_yahoo_session() -> None:
    """Yahoo sometimes rejects a stale cookie ('Invalid Crumb'); clearing yfinance's cookie cache fixes it."""
    try:
        import yfinance as yf
        path = yf.cache.get_cache_dirpath() if hasattr(yf, "cache") and hasattr(yf.cache, "get_cache_dirpath") else None
    except Exception:  # noqa: BLE001
        path = None
    for p in filter(None, [path, os.path.expanduser("~/.cache/py-yfinance"),
                           os.path.expanduser("~/Library/Caches/py-yfinance")]):
        shutil.rmtree(p, ignore_errors=True)


def _fetch_one(ticker: str):
    import yfinance as yf

    cal = yf.Ticker(ticker).calendar
    dates = cal.get("Earnings Date") if isinstance(cal, dict) else None
    today = datetime.now(PT).date()
    future = sorted(d for d in (dates or []) if isinstance(d, date) and d >= today)
    return future[0].isoformat() if future else None


def get_earnings(tickers: list[str], max_fetch: int = 150) -> dict[str, dict]:
    """Return {ticker: {"date": "YYYY-MM-DD", "days": n}} for tickers with a known upcoming date."""
    cache = _load()
    now = time.time()
    today = datetime.now(PT).date()
    todo = [t for t in dict.fromkeys(tickers)
            if t not in cache or now - cache[t].get("at", 0) > MAX_AGE
            or (cache[t].get("date") and cache[t]["date"] < today.isoformat())][:max_fetch]
    failures, reset = 0, False
    for t in todo:
        try:
            d = _fetch_one(t)
            # a missing date is often a silent Yahoo hiccup: keep it only 2 hours, then ask again
            cache[t] = {"date": d, "at": now if d else now - MAX_AGE + 2 * 3600}
            failures = 0
        except Exception as e:  # noqa: BLE001
            failures += 1
            print(f"  earnings {t}: {str(e)[:80]}", file=sys.stderr)
            if failures >= 3 and not reset:
                _reset_yahoo_session()
                reset, failures = True, 0
                time.sleep(3)
            elif failures >= 6:
                break
        time.sleep(0.15)
    _save(cache)
    out = {}
    for t in tickers:
        d = (cache.get(t) or {}).get("date")
        if d:
            out[t] = {"date": d, "days": (date.fromisoformat(d) - today).days}
    return out


def attach(entries: list[dict], max_fetch: int = 150) -> None:
    """Add entry['earnings'] = {"date", "days", "soon"} to each stock entry (ETFs have none)."""
    tickers = [e["ticker"] for e in entries if e.get("kind", "Stock") != "ETF"]
    if not tickers:
        return
    info = get_earnings(tickers, max_fetch=max_fetch)
    for e in entries:
        if e["ticker"] in info:
            e["earnings"] = {**info[e["ticker"]], "soon": info[e["ticker"]]["days"] <= WARN_DAYS}
    try:
        attach_company(entries)
    except Exception as ex:  # noqa: BLE001  (never break the screen over company facts)
        print(f"  company facts failed: {ex}", file=sys.stderr)


# ---------------------------------------------------------------- company facts (Taylor, Oct 22)
"""
Key stats + financial summary + company profile for the screen's Crossed / Approaching stocks
(not the 100 'On the radar' names, to keep the run quick). Yahoo quoteSummary via yfinance .info,
cached 24 hours in cache/company.json. Shown under the chart on the page.
"""
CO_CACHE = os.path.join(BASE, "cache", "company.json")
CO_FIELDS = {
    # key stats
    "marketCap": "mcap", "trailingPE": "pe", "forwardPE": "fpe", "trailingEps": "eps", "beta": "beta",
    "fiftyTwoWeekHigh": "hi52", "fiftyTwoWeekLow": "lo52", "averageVolume": "avgvol",
    "sharesOutstanding": "shares", "dividendYield": "divy", "dividendRate": "divr", "exDividendDate": "exdiv",
    "floatShares": "float", "shortPercentOfFloat": "short", "heldPercentInstitutions": "inst",
    # financials (trailing 12 months unless noted)
    "totalRevenue": "rev", "revenueGrowth": "revg", "earningsGrowth": "epsg", "grossMargins": "gm",
    "operatingMargins": "om", "profitMargins": "pm", "ebitda": "ebitda", "netIncomeToCommon": "ni",
    "freeCashflow": "fcf", "totalCash": "cash", "totalDebt": "debt", "debtToEquity": "de",
    "returnOnEquity": "roe", "currentRatio": "cr",
    # analysts
    "recommendationKey": "rec", "targetMeanPrice": "target", "numberOfAnalystOpinions": "analysts",
    # profile
    "longName": "name", "sector": "sector", "industry": "industry", "fullTimeEmployees": "employees",
    "city": "city", "state": "state", "country": "country", "website": "web", "longBusinessSummary": "about",
    "financialCurrency": "fincur",
}


def _co_fetch(t: str) -> dict:
    import yfinance as yf

    info = yf.Ticker(t).info or {}
    out = {}
    for k, short in CO_FIELDS.items():
        v = info.get(k)
        if v is None or v == "" or (isinstance(v, float) and v != v):
            continue
        if short == "about":
            v = str(v)[:1500]
        out[short] = round(v, 4) if isinstance(v, float) else v
    return out


def attach_company(entries: list[dict], max_fetch: int = 80) -> None:
    want = [e["ticker"] for e in entries
            if e.get("kind", "Stock") != "ETF" and e.get("status") not in (None, "SETTING UP")]
    if not want:
        return
    try:
        with open(CO_CACHE) as fh:
            cache = json.load(fh)
    except Exception:  # noqa: BLE001
        cache = {}
    now, fails = time.time(), 0
    for t in [t for t in dict.fromkeys(want) if now - (cache.get(t) or {}).get("at", 0) > MAX_AGE][:max_fetch]:
        try:
            cache[t] = {"at": now, "d": _co_fetch(t)}
            fails = 0
        except Exception as e:  # noqa: BLE001
            fails += 1
            print(f"  company {t}: {str(e)[:80]}", file=sys.stderr)
            if fails >= 5:
                break
        time.sleep(0.2)
    os.makedirs(os.path.dirname(CO_CACHE), exist_ok=True)
    with open(CO_CACHE + ".tmp", "w") as fh:
        json.dump(cache, fh)
    os.replace(CO_CACHE + ".tmp", CO_CACHE)
    for e in entries:
        d = (cache.get(e["ticker"]) or {}).get("d")
        if d and e["ticker"] in want:
            e["company"] = d
