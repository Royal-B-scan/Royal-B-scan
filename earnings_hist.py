"""
Earnings history for the chart's E markers and their pop-up (Nov 10, 2026: refreshed by the daily screen).

Same data as build_eh.py (Nov 6), now kept up to date on GitHub instead of by hand:
  by[T]   = [[report date, "amc"|"bmo", EPS surprise %, EPS estimate, EPS reported, period ending, revenue, revenue YoY %], ...]
  next[T] = {"date", "when", "est"}
Saved in cache/earnings_hist.json (kept between runs by the workflow's cache) and put into scan.json "eh", which the
page already receives every day (GitHub results branch -> Google Drive -> page).
A ticker is looked up again when it's new, when its next report date has passed, or after 7 days. At most MAX_FETCH
lookups a run, so a slow Yahoo day can't hold up the screen; the rest wait for the next run.

    refresh(tickers) -> {"updated", "v": 2, "by": {...}, "next": {...}}   (only the tickers asked for)
"""
from __future__ import annotations

import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime

BASE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(BASE, "cache", "earnings_hist.json")
MAX_AGE_DAYS = 7
MAX_FETCH = 250


def _num(x, d=2):
    try:
        x = float(x)
    except Exception:  # noqa: BLE001
        return None
    return None if x != x else round(x, d)


def _one(t):
    import yfinance as yf
    err = None
    for attempt in range(2):
        try:
            tk = yf.Ticker(t)
            df = tk.get_earnings_dates(limit=28)
            rev, cols = {}, set()
            try:
                q = tk.quarterly_income_stmt
                if q is not None and "Total Revenue" in q.index:
                    for c, v in q.loc["Total Revenue"].items():
                        cols.add(c.date().isoformat())
                        v = _num(v, 0)
                        if v:
                            rev[c.date().isoformat()] = v
            except Exception:  # noqa: BLE001
                pass
            ends = sorted(cols)
            rows, nxt = [], None
            today = date.today().isoformat()
            for ts, r in (df.iterrows() if df is not None else []):
                d0 = ts.strftime("%Y-%m-%d")
                when = "amc" if ts.hour >= 12 else "bmo"
                rep = _num(r.get("Reported EPS"))
                if rep is None:
                    if d0 >= today and (nxt is None or d0 < nxt["date"]):
                        nxt = {"date": d0, "when": when, "est": _num(r.get("EPS Estimate"))}
                    continue
                pe = [e for e in ends if e < d0 and (datetime.fromisoformat(d0) - datetime.fromisoformat(e)).days <= 120]
                pe = pe[-1] if pe else None
                rv = rev.get(pe) if pe else None
                yoy = None
                if pe and rv:
                    py = [e for e in ends if 330 <= (datetime.fromisoformat(pe) - datetime.fromisoformat(e)).days <= 400]
                    if py and rev.get(py[-1]):
                        yoy = round((rv / rev[py[-1]] - 1) * 100, 1)
                rows.append([d0, when, _num(r.get("Surprise(%)"), 1), _num(r.get("EPS Estimate")), rep, pe, rv, yoy])
            return t, sorted(rows), nxt
        except Exception as e:  # noqa: BLE001
            err = e
            time.sleep(2 + attempt * 3)
    print(f"  earnings history {t}: {str(err)[:80]}", file=sys.stderr)
    return t, None, None


def _load() -> dict:
    try:
        with open(CACHE) as fh:
            c = json.load(fh)
            return c if isinstance(c, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def refresh(tickers: list[str]) -> dict:
    tickers = [t for t in dict.fromkeys(tickers) if t]
    cache = _load()                         # {T: {"rows": [...], "next": {...} | None, "at": "YYYY-MM-DD"}}
    today = date.today()

    def stale(t):
        c = cache.get(t)
        if not c:
            return True
        try:
            if (today - date.fromisoformat(c.get("at", "2000-01-01"))).days >= MAX_AGE_DAYS:
                return True
        except ValueError:
            return True
        n = c.get("next") or {}
        return bool(n.get("date") and n["date"] < today.isoformat())   # it has reported since we last looked

    todo = [t for t in tickers if stale(t)]
    todo.sort(key=lambda t: t in cache)     # never-seen tickers first
    todo = todo[:MAX_FETCH]
    got = 0
    if todo:
        with ThreadPoolExecutor(6) as ex:
            for t, rows, nxt in ex.map(_one, todo):
                if rows is None:
                    continue
                cache[t] = {"rows": rows, "next": nxt, "at": today.isoformat()}
                got += 1
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    with open(CACHE + ".tmp", "w") as fh:
        json.dump(cache, fh, separators=(",", ":"))
    os.replace(CACHE + ".tmp", CACHE)
    print(f"  earnings history: {got} looked up, {len(todo) - got} failed, {len(tickers)} on the page", file=sys.stderr)
    by = {t: cache[t]["rows"] for t in tickers if t in cache and cache[t].get("rows")}
    nx = {t: cache[t]["next"] for t in tickers if t in cache and cache[t].get("next")}
    return {"updated": today.isoformat(), "v": 2, "by": by, "next": nx}
