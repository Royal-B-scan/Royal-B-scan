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
