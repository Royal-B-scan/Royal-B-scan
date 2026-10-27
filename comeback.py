"""
Comeback watch + long-term holdings (Oct 21, 2026; Oct 27: saved company numbers when Yahoo refuses lookups).

Comeback = large caps that got beaten down but are still good businesses. Taylor watches them
and waits for them to start coming around (for his long-term portfolio, not swing trades).

  large        market cap > $10B (US + CA, NYSE / Nasdaq / NYSE American / TSX)
  beaten down  >= 25% below the 2-year high AND >= 15 points behind SPY over 12 months
  quality      profit margin >= 5%, forward P/E 0-30, revenue growth > -10%, free cash flow > 0

Stages ("coming around"):
  1 Still falling  new 52-week low within the last 30 trading days
  2 Basing         no new 52-week low for 30+ days, below the 50/200-day
  3 Turning up     above a rising 50-day (still below the 200-day)
  4 Recovered      back above the 200-day
All-time high (full history) is added to every row: ath, ath_date, ath_years, dd_ath, lower_highs_years
(consecutive calendar years of lower highs) and long_decline (ATH 2.5+ years ago AND 3+ years of lower highs),
so a 2-year view can't hide a 5-year slide (e.g. NKE).
"moved_up" = today's stage is higher than any stage in the previous 10 trading days
(first real step up, so a stock wobbling around a line doesn't alert every day).

Long-term holdings get slower alerts: close below the 200-day, >= 20% below the 52-week high,
earnings within 7 days.
"""
from __future__ import annotations

import sys
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd

LARGE = 10e9
DD_MIN = -25.0          # % below 2-year high
LAG_MIN = -15.0         # points behind SPY over 12 months
OFF_HIGH_ALERT = -20.0  # long-term alert: % below 52-week high
EXCH = {"NYQ", "NMS", "NGM", "NCM", "ASE", "TOR"}
STAGES = {1: "STILL FALLING", 2: "BASING", 3: "TURNING UP", 4: "RECOVERED"}
KEEP_BARS = 260         # daily bars kept for the chart


def _noop(*_a, **_k):
    pass


# ---------------------------------------------------------------- data
def large_caps(progress=_noop) -> dict[str, dict]:
    import yfinance as yf
    from yfinance import EquityQuery as Q

    out: dict[str, dict] = {}
    for region in ("us", "ca"):
        off, total = 0, None
        while True:
            res = None
            for attempt in range(5):
                try:
                    res = yf.screen(Q("and", [Q("eq", ["region", region]), Q("gt", ["intradaymarketcap", LARGE])]),
                                    offset=off, size=250, sortField="intradaymarketcap", sortAsc=False)
                    break
                except Exception as e:  # noqa: BLE001
                    print(f"  comeback screen retry {attempt + 1}: {e}", file=sys.stderr)
                    time.sleep(3 + attempt * 4)
            if res is None:
                break
            quotes = res.get("quotes", [])
            total = res.get("total", 0)
            off += len(quotes)
            for q in quotes:
                if q.get("quoteType") == "EQUITY" and q.get("exchange") in EXCH:
                    out[q["symbol"]] = {"name": q.get("shortName") or q.get("longName") or q["symbol"],
                                        "market_cap": q.get("marketCap") or 0,
                                        "currency": q.get("currency") or "USD",
                                        "exchange": q.get("fullExchangeName", "")}
            progress("Comeback: finding large caps", None, None, f"{region.upper()} {off} of {total}")
            if not quotes or off >= (total or 0):
                break
            time.sleep(0.4)
    return out


def download(tickers: list[str], period: str = "2y") -> dict[str, pd.DataFrame]:
    import yfinance as yf

    out: dict[str, pd.DataFrame] = {}
    tickers = list(dict.fromkeys(tickers))
    for i in range(0, len(tickers), 200):
        chunk = tickers[i:i + 200]
        data = None
        for attempt in range(3):
            try:
                data = yf.download(chunk, period=period, interval="1d", group_by="ticker",
                                   auto_adjust=True, threads=True, progress=False)
                break
            except Exception as e:  # noqa: BLE001
                print(f"  comeback download retry {attempt + 1}: {e}", file=sys.stderr)
                time.sleep(3 + attempt * 5)
        if data is None:
            continue
        for t in chunk:
            try:
                df = (data[t] if len(chunk) > 1 else data).dropna(subset=["Close"])
                df = df[["Open", "High", "Low", "Close", "Volume"]]
            except (KeyError, TypeError):
                continue
            if len(df) >= 60:
                out[t] = df
        time.sleep(0.3)
    return out


FUND_CACHE_URL = "https://raw.githubusercontent.com/Royal-B-scan/Royal-B-scan/results/fund_cache.json"
FUND_MAX_AGE = 45   # days: company numbers only change each quarter


def _load_fund_cache() -> dict:
    """Last good company numbers per ticker (Oct 27 fix): yesterday's copy on the results branch,
    else the seed file in the repo. Used whenever Yahoo refuses a lookup, so one bad day can't empty Comebacks."""
    import json
    import os
    cache: dict = {}
    seed = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fund_cache.json")
    try:
        with open(seed) as fh:
            cache.update(json.load(fh))
    except Exception:  # noqa: BLE001
        pass
    try:
        import requests
        r = requests.get(FUND_CACHE_URL, params={"x": int(time.time())}, timeout=20)
        if r.ok:
            cache.update(r.json())
    except Exception as e:  # noqa: BLE001
        print("  fund cache download failed:", e, file=sys.stderr)
    return cache


def _save_fund_cache(cache: dict) -> None:
    import json
    import os
    os.makedirs("site", exist_ok=True)
    with open(os.path.join("site", "fund_cache.json"), "w") as fh:
        json.dump(cache, fh, separators=(",", ":"))


def fundamentals(tickers: list[str]) -> dict[str, dict]:
    import yfinance as yf

    cache = _load_fund_cache()
    today = datetime.now(timezone.utc).date()

    def fresh(t):
        c = cache.get(t)
        if not c or not c.get("_date"):
            return False
        try:
            return (today - datetime.strptime(c["_date"], "%Y-%m-%d").date()).days <= FUND_MAX_AGE
        except ValueError:
            return False

    out: dict[str, dict] = {}
    fails, live, used_cache, blocked = 0, 0, 0, False
    for t in tickers:
        i = None
        if not blocked:
            for attempt in range(2):
                try:
                    i = yf.Ticker(t).info or {}
                    break
                except Exception as e:  # noqa: BLE001
                    print(f"  fundamentals {t}: {str(e)[:80]}", file=sys.stderr)
                    time.sleep(5 + attempt * 10)   # Yahoo rate limit: back off, then try once more
            if i is None:
                fails += 1
                if fails >= 8:
                    blocked = True   # Yahoo is refusing us today: use the saved numbers for the rest
                    print("  fundamentals: Yahoo refusing lookups, using saved numbers", file=sys.stderr)
            else:
                fails = 0
        if i and (i.get("profitMargins") is not None or i.get("forwardPE") is not None):
            out[t] = {
                "pe": _r(i.get("trailingPE"), 1), "fpe": _r(i.get("forwardPE"), 1),
                "margin": _r(_pct(i.get("profitMargins")), 0), "rev": _r(_pct(i.get("revenueGrowth")), 0),
                "fcf_pos": (i.get("freeCashflow") or 0) > 0 if i.get("freeCashflow") is not None else None,
                "div": _r(i.get("dividendYield"), 2), "target": _r(i.get("targetMeanPrice"), 2),
                "sector": i.get("sector"), "industry": i.get("industry"),
                "name": i.get("shortName") or i.get("longName"),
                "market_cap": i.get("marketCap"),
            }
            cache[t] = dict(out[t], _date=today.isoformat())
            live += 1
            time.sleep(0.15)
        elif fresh(t):
            out[t] = {k: v for k, v in cache[t].items() if k != "_date"}
            used_cache += 1
    print(f"  fundamentals: {live} from Yahoo, {used_cache} from saved numbers, {len(tickers) - live - used_cache} missing", file=sys.stderr)
    try:
        _save_fund_cache(cache)
    except Exception as e:  # noqa: BLE001
        print("  fund cache save failed:", e, file=sys.stderr)
    return out


def _r(v, d):
    try:
        return None if v is None or (isinstance(v, float) and np.isnan(v)) else round(float(v), d)
    except (TypeError, ValueError):
        return None


def _pct(v):
    return None if v is None else float(v) * 100


def quality_ok(f: dict | None) -> bool:
    if not f:
        return False
    return ((f.get("margin") or -1) >= 5 and f.get("fpe") is not None and 0 < f["fpe"] <= 30
            and (f.get("rev") if f.get("rev") is not None else -99) > -10 and f.get("fcf_pos") is True)


# ---------------------------------------------------------------- analysis
def stage_series(df: pd.DataFrame) -> pd.Series:
    c = df["Close"]
    s50, s200 = c.rolling(50).mean(), c.rolling(200).mean()
    low252 = c.rolling(252, min_periods=120).min()
    falling = c.rolling(30).min() <= low252 * 1.0001
    s50_up = s50 > s50.shift(10)
    st = np.where(c > s200, 4, np.where((c > s50) & s50_up, 3, np.where(falling, 1, 2)))
    st = pd.Series(st, index=c.index, dtype=float)
    st[s200.isna() | low252.isna()] = np.nan
    return st


def comeback_info(df: pd.DataFrame, spy: pd.Series | None) -> dict | None:
    c = df["Close"]
    if len(c) < 210:
        return None
    st = stage_series(df)
    if np.isnan(st.iloc[-1]):
        return None
    stage = int(st.iloc[-1])
    prev = st.iloc[-11:-1].dropna()
    moved_up = bool(len(prev) and stage > prev.max())
    s50, s200 = c.rolling(50).mean(), c.rolling(200).mean()
    high2y = float(c.iloc[-504:].max())
    high52 = float(c.iloc[-252:].max())
    low52 = float(c.iloc[-252:].min())
    since_low = int(len(c.iloc[-252:]) - 1 - int(np.argmin(c.iloc[-252:].values)))
    r1y = float(c.iloc[-1] / c.iloc[-252] - 1) * 100 if len(c) > 252 else None
    lag = None
    if spy is not None and r1y is not None:
        b = spy.reindex(c.index).ffill()
        if b.notna().iloc[-252] and b.notna().iloc[-1]:
            lag = r1y - float(b.iloc[-1] / b.iloc[-252] - 1) * 100
    return {
        "stage": stage, "stage_name": STAGES[stage], "moved_up": moved_up,
        "prev_stage": int(prev.iloc[-1]) if len(prev) else None,
        "high2y": round(high2y, 2), "dd2y": round((c.iloc[-1] / high2y - 1) * 100, 1),
        "high52": round(high52, 2), "off_high52": round((c.iloc[-1] / high52 - 1) * 100, 1),
        "low52": round(low52, 2), "from_low": round((c.iloc[-1] / low52 - 1) * 100, 1), "days_since_low": since_low,
        "r1y": _r(r1y, 1), "vs_spy": _r(lag, 1),
        "sma50": _r(s50.iloc[-1], 2), "sma200": _r(s200.iloc[-1], 2),
        "above200": bool(c.iloc[-1] > s200.iloc[-1]),
    }


def ath_info(df: pd.DataFrame) -> dict | None:
    """All-time high (from full history) and how long the stock has been making lower yearly highs."""
    c = df["Close"].dropna()
    if c.empty:
        return None
    i = int(np.argmax(c.values))
    ath, when = float(c.iloc[i]), c.index[i]
    yrs = (c.index[-1] - when).days / 365.25
    yh = c.groupby(c.index.year).max()
    lower = 0
    for k in range(len(yh) - 1, 0, -1):
        if yh.iloc[k] < yh.iloc[k - 1]:
            lower += 1
        else:
            break
    return {"ath": round(ath, 2), "ath_date": when.strftime("%Y-%m-%d"), "ath_years": round(yrs, 1),
            "dd_ath": round((c.iloc[-1] / ath - 1) * 100, 1), "lower_highs_years": lower,
            "long_decline": bool(yrs >= 2.5 and lower >= 3)}


def add_ath(rows_or_cbs: dict[str, dict]) -> None:
    """rows_or_cbs = {ticker: cb dict}; adds all-time-high fields in place (full price history)."""
    if not rows_or_cbs:
        return
    hist = download(list(rows_or_cbs), period="max")
    for t, cb in rows_or_cbs.items():
        df = hist.get(t)
        try:
            info = ath_info(df) if df is not None else None
        except Exception:  # noqa: BLE001
            info = None
        if info:
            cb.update(info)


def make_row(t: str, df: pd.DataFrame, meta: dict, cb: dict, fund: dict | None) -> dict:
    from export_site import rule_checks, series

    c = df["Close"]
    ser = series(df)
    ser = {k: v[-KEEP_BARS:] for k, v in ser.items() if k not in ("sma10", "sma20")}
    f = fund or {}
    return {
        "ticker": t, "kind": "Stock",
        "name": f.get("name") or meta.get("name") or t,
        "currency": meta.get("currency") or ("CAD" if t.endswith((".TO", ".V")) else "USD"),
        "exchange": meta.get("exchange", ""),
        "sector": f.get("sector") or meta.get("sector") or "Other",
        "market_cap": f.get("market_cap") or meta.get("market_cap") or 0,
        "close": round(float(c.iloc[-1]), 2),
        "change": round(float(c.iloc[-1] - c.iloc[-2]), 2),
        "change_pct": round(float((c.iloc[-1] / c.iloc[-2] - 1) * 100), 2),
        "status": cb["stage_name"],
        "exit_level": None,
        "rvol": round(float(df["Volume"].iloc[-1] / df["Volume"].iloc[-50:].mean()), 2),
        "checks": rule_checks(df),
        "series": ser,
        "cb": cb,
        "fund": {k: f.get(k) for k in ("pe", "fpe", "margin", "rev", "fcf_pos", "div", "target", "industry")},
    }


# ---------------------------------------------------------------- full screen (daily run)
def build(progress=_noop) -> dict:
    t0 = time.time()
    uni = large_caps(progress)
    progress("Comeback: downloading 2 years of prices", None, None, f"{len(uni)} large caps")
    hist = download(list(uni) + ["SPY"])
    spy = hist.pop("SPY", pd.DataFrame()).get("Close")
    beaten = {}
    for t, df in hist.items():
        try:
            cb = comeback_info(df, spy)
        except Exception:  # noqa: BLE001
            continue
        if cb and cb["dd2y"] <= DD_MIN and cb["vs_spy"] is not None and cb["vs_spy"] <= LAG_MIN:
            beaten[t] = cb
    progress("Comeback: checking fundamentals", None, None, f"{len(beaten)} beaten down")
    fund = fundamentals(list(beaten))
    rows = []
    for t, cb in beaten.items():
        if not quality_ok(fund.get(t)):
            continue
        try:
            rows.append(make_row(t, hist[t], uni.get(t, {}), cb, fund.get(t)))
        except Exception as e:  # noqa: BLE001
            print(f"  comeback row {t}: {e}", file=sys.stderr)
    progress("Comeback: all-time highs", None, None, f"{len(rows)} stocks")
    add_ath({r["ticker"]: r["cb"] for r in rows})
    try:
        import earnings
        earnings.attach(rows, max_fetch=200)
    except Exception as e:  # noqa: BLE001
        print("comeback earnings failed:", e, file=sys.stderr)
    rows.sort(key=lambda r: (-r["cb"]["stage"], -(r["market_cap"] or 0)))
    counts = {"large": len(uni), "beaten": len(beaten), "quality": len(rows),
              **{STAGES[s].lower().replace(" ", "_"): sum(1 for r in rows if r["cb"]["stage"] == s) for s in STAGES}}
    return {
        "updated": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "seconds": round(time.time() - t0),
        "criteria": {"market_cap_min": LARGE, "dd2y_max": DD_MIN, "vs_spy_max": LAG_MIN,
                     "margin_min": 5, "fpe_max": 30, "rev_min": -10, "fcf_positive": True},
        "counts": counts,
        "moved_up": [r["ticker"] for r in rows if r["cb"]["moved_up"]],
        "rows": rows,
    }


# ---------------------------------------------------------------- long-term holdings + pinned comeback stocks
def track(tickers: list[str], longterm: dict, pins: set[str]) -> list[dict]:
    """Entries for Taylor's long-term holdings and pinned comeback stocks (every refresh, quick included)."""
    tickers = [t for t in dict.fromkeys(tickers) if t]
    if not tickers:
        return []
    hist = download(tickers + ["SPY"])
    spy = hist.pop("SPY", pd.DataFrame()).get("Close")
    fund = fundamentals([t for t in tickers if t in hist])
    out = []
    for t in tickers:
        df = hist.get(t)
        if df is None or len(df) < 210:
            continue
        cb = comeback_info(df, spy)
        if not cb:
            continue
        f = fund.get(t) or {}
        meta = {"currency": "CAD" if t.endswith((".TO", ".V")) else "USD"}
        try:
            import yfinance as yf
            m = yf.Ticker(t).history_metadata or {}
            meta.update(currency=m.get("currency", meta["currency"]), exchange=m.get("fullExchangeName", ""))
        except Exception:  # noqa: BLE001
            pass
        row = make_row(t, df, meta, cb, f)
        row["quality"] = quality_ok(f)
        row["pinned"] = t in pins
        pos = longterm.get(t)
        if isinstance(pos, dict):
            cost = pos.get("cost")
            alerts = []
            if not cb["above200"]:
                alerts.append("BELOW 200-DAY")
            if cb["off_high52"] <= OFF_HIGH_ALERT:
                alerts.append(f"{cb['off_high52']:.0f}% FROM HIGH")
            if t not in pins and cb["dd2y"] > DD_MIN:   # not a beaten-down name: show the long-term trend instead
                row["status"] = "ABOVE 200-DAY" if cb["above200"] else "BELOW 200-DAY"
            row["lt"] = {"cost": cost, "date": pos.get("date"),
                         "pl_pct": round((row["close"] / float(cost) - 1) * 100, 2) if cost else None,
                         "alerts": alerts}
        out.append(row)
    add_ath({r["ticker"]: r["cb"] for r in out})
    try:
        from export_site import timeframes
        extra = timeframes([r["ticker"] for r in out])
        for r in out:
            r["tf"] = extra.get(r["ticker"], {})
    except Exception as e:  # noqa: BLE001
        print("long-term timeframes failed:", e, file=sys.stderr)
    try:
        import earnings
        earnings.attach(out)
    except Exception as e:  # noqa: BLE001
        print("long-term earnings failed:", e, file=sys.stderr)
    for r in out:
        if r.get("lt") and r.get("earnings", {}).get("soon"):
            r["lt"]["alerts"].append(f"EARNINGS {r['earnings']['days']}D")
    return out


if __name__ == "__main__":
    import json
    import os

    if len(sys.argv) > 1:
        print(json.dumps([{k: r[k] for k in ("ticker", "close", "cb", "fund", "lt") if k in r}
                          for r in track(sys.argv[1:], {}, set())], indent=1))
    else:
        res = build(lambda s, d, t, n: print(s, n or "", flush=True))
        os.makedirs("site", exist_ok=True)
        with open("site/comeback.json", "w") as fh:
            json.dump(res, fh, separators=(",", ":"))
        print(json.dumps(res["counts"]), res["moved_up"], f"{res['seconds']}s")
