"""
Royal B Scout: the workers (Phase 2, Nov 12, 2026). Gathers the numbers; the Scout (Claude) does the judging.

    python scout_data.py                    today -> workers.json (+ a copy in data/workers-YYYY-MM-DD.json)
    python scout_data.py --asof 2026-11-06  replay a past day from the saved prices (no Royal B screens / book)
    python scout_data.py --summary          also print a one-screen summary
    python scout_data.py --no-download      reuse data/px_cache.pkl as it is

Workers in this file (PLAN.md "The team"):
  sector watcher      the plan's sector + theme ETFs vs SPY / XIU, and stock groups (sell-off, turn, breadth)
  price-action worker each stock's stage, the Shakeout Bounce signal, volume, distance from its averages
  calendar keeper     next earnings dates for the stocks that matter today
  Royal B screens     today's Top 5, Bullish Turn, Early Turn, Trend Cross, Weekly Trend, gauge, credit light
  your book           Taylor's watch list and holdings as Royal B's daily screen saw them
The news reader, earnings worker, business checker and hype worker stay with the Scout: they need judgment.

What is tested and what is only a label (research/phase1-results.md, research/shakeout-v2-results.md):
  TESTED   "sector_rebound": a leading group falls 8%+ and closes 3%+ off its low within 5 days.
  TESTED   "shakeout" with "with_group": Shakeout Bounce (52-week high within 120 days, close in the top half of
           the range) on a day when a third or more of its group was up 2%+. Alone, it was no better than random.
  LABELS   every "stage" below is a plain description of where the price is. Stages were not backtested.
Info only: this file never writes to Royal B. workers.json holds Taylor's holdings, so it stays in this folder.
All market timing is New York time. Not financial advice.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
PX = os.path.join(DATA, "px_cache.pkl")
EARN = os.path.join(DATA, "earnings_cache.json")
UNIVERSE = os.path.join(HERE, "research", "universe.csv")
UNIVERSE_EODHD = os.path.join(HERE, "research", "universe_eodhd.csv")   # Nov 14: whole market over $2B (universe_eodhd.py)
PX_EODHD = os.path.join(DATA, "px_eodhd_scout.pkl")


def pick_source() -> str:
    """Nov 14 (Taylor: Scout on the whole market): "eodhd" = 2,133 US + TSX companies over $2B with EODHD prices,
    re-tested in research/whole-market-retest-results.md. "yahoo" = the old 571 large caps. Env SCOUT_SOURCE overrides;
    by default EODHD whenever its key is available (env EODHD_API_KEY or the Mac key file)."""
    s = os.environ.get("SCOUT_SOURCE", "").lower()
    if s in ("eodhd", "yahoo"):
        return s
    has_key = bool(os.environ.get("EODHD_API_KEY")) or os.path.exists(os.path.expanduser("~/Documents/Stock Screener/.eodhd_key"))
    return "eodhd" if has_key and os.path.exists(UNIVERSE_EODHD) else "yahoo"
ET = ZoneInfo("America/New_York")
RESULTS = "https://raw.githubusercontent.com/Royal-B-scan/Royal-B-scan/results/"

US_SECTORS = ["XLK", "XLC", "XLY", "XLP", "XLE", "XLF", "XLV", "XLI", "XLB", "XLU", "XLRE"]
US_THEMES = ["SMH", "SOXX", "IGV", "HACK", "CLOU", "XBI", "IBB", "KRE", "ITA", "GDX", "SIL", "URA", "TAN", "ICLN", "COPX",
             "XHB", "ITB", "JETS", "XRT", "BOTZ", "ARKK", "IPAY"]
CA_SECTORS = ["XEG.TO", "XFN.TO", "XIT.TO", "XMA.TO", "XGD.TO", "XUT.TO", "XRE.TO"]
BENCH = {"USD": "SPY", "CAD": "XIU.TO"}
FOREIGN = {"TSM": "Semiconductors", "ASML": "Semiconductor Materials & Equipment", "ARM": "Semiconductors",
           "SHOP": "Application Software", "SAP": "Application Software", "NVO": "Pharmaceuticals",
           "BABA": "Broadline Retail", "PDD": "Broadline Retail", "MELI": "Broadline Retail", "SE": "Broadline Retail"}
FOREIGN_SECTOR = {"Semiconductors": "Information Technology", "Semiconductor Materials & Equipment": "Information Technology",
                  "Application Software": "Information Technology", "Pharmaceuticals": "Health Care", "Broadline Retail": "Consumer Discretionary"}
# tested settings (Taylor, Nov 12): do not change without a backtest on both periods
HI_DAYS, TOP_SHARE, GROUP_UP_SHARE = 120, 0.5, 1 / 3
REBOUND_DROP, REBOUND_BOUNCE, REBOUND_AGE = 8.0, 3.0, 5
COLS = ["Open", "High", "Low", "Close", "Volume"]


def r2(x, n=2):
    try:
        return None if x is None or not np.isfinite(float(x)) else round(float(x), n)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- universe + prices
def load_universe(source: str = "yahoo") -> tuple[pd.DataFrame, dict]:
    """(universe table, {ticker: group}). Group = GICS sub-industry with 8+ members, else sector; TSX by TSX sector.
    EODHD list: its own group column (EODHD industry, under 8 members rolled up to the sector), US and TSX together."""
    if source == "eodhd":
        uni = pd.read_csv(UNIVERSE_EODHD, keep_default_na=False)
        return uni, dict(zip(uni.ticker, uni.group))
    uni = pd.read_csv(UNIVERSE, keep_default_na=False)
    sub = uni[uni.group == "SP500"].groupby("industry").size()
    big = set(sub[sub >= 8].index)
    grp = {}
    for r in uni.itertuples():
        if r.group == "SP500":
            grp[r.ticker] = r.industry if r.industry in big else r.sector
        elif r.group == "TSX60":
            grp[r.ticker] = "CA " + (r.sector or "Other")
        else:
            g = FOREIGN.get(r.ticker, "")
            grp[r.ticker] = g if g in big else FOREIGN_SECTOR.get(g, "Other")
    return uni, grp


def download(tickers: list[str]) -> pd.DataFrame:
    """Two years of daily bars (adjusted) for everything, saved to data/px_cache.pkl."""
    import yfinance as yf

    parts, missing = [], []
    for i in range(0, len(tickers), 100):
        chunk = tickers[i:i + 100]
        d = None
        for attempt in range(3):
            try:
                d = yf.download(chunk, period="2y", interval="1d", group_by="ticker", auto_adjust=True, threads=True, progress=False)
                break
            except Exception as e:  # noqa: BLE001
                print(f"  price retry {attempt + 1}: {e}", file=sys.stderr)
                time.sleep(5 + attempt * 10)
        if d is None:
            missing += chunk
            continue
        for t in chunk:
            try:
                df = d[t].dropna(subset=["Close"])[COLS]
            except KeyError:
                missing.append(t)
                continue
            if len(df) < 60:
                missing.append(t)
                continue
            df.columns = pd.MultiIndex.from_product([[t], df.columns])
            parts.append(df)
        time.sleep(0.5)
    px = pd.concat(parts, axis=1, sort=True).sort_index()
    os.makedirs(DATA, exist_ok=True)
    px.to_pickle(PX)
    return px, missing


def frames(px: pd.DataFrame, asof: str | None) -> dict[str, pd.DataFrame]:
    out = {}
    for t in sorted(set(px.columns.get_level_values(0))):
        df = px[t].dropna(subset=["Close"])
        if asof:
            df = df[df.index <= pd.Timestamp(asof)]
        if len(df) >= 60:
            out[t] = df
    return out


# ---------------------------------------------------------------- shared maths
def drop_state(close: pd.Series) -> dict:
    """The sell-off read used everywhere: the 10-day low (before today) against the high of the 20 days before it."""
    c = close.values
    if len(c) < 32:
        return {"drop": None, "low_age": None, "off_low": None}
    lo, pk = c[-11:-1].min(), c[-31:-11].max()
    return {"drop": r2((1 - lo / pk) * 100, 1), "low_age": int(10 - int(np.argmin(c[-11:-1]))), "off_low": r2((c[-1] / lo - 1) * 100, 1),
            "low": r2(lo), "peak": r2(pk)}


def averages(close: pd.Series) -> dict:
    c = close
    out = {}
    for n in (20, 50, 200):
        out[f"vs{n}"] = r2((c.iloc[-1] / c.iloc[-n:].mean() - 1) * 100, 1) if len(c) >= n else None
    s200 = c.rolling(200).mean()
    out["rising200"] = bool(s200.iloc[-1] > s200.iloc[-21]) if len(c) >= 221 else None
    return out


def ret(close: pd.Series, n: int):
    return r2((close.iloc[-1] / close.iloc[-1 - n] - 1) * 100, 1) if len(close) > n else None


def shakeout_days(df: pd.DataFrame, last_n: int = 4) -> list[int]:
    """How many bars ago (0 = today) Shakeout Bounce fired, within the last few bars. Tested settings."""
    O, H, L, C, V = (df[k].values for k in COLS)
    n = len(C)
    if n < 300:
        return []
    c = pd.Series(C)
    s200 = c.rolling(200).mean().values
    hi252 = c.rolling(252).max().values
    v50 = pd.Series(V).rolling(50).mean().shift(1).values
    out = []
    for i in range(n - last_n, n):
        if not (C[i - 20] > s200[i - 20] and s200[i - 20] > s200[i - 40] and C[i - HI_DAYS:i + 1].max() >= hi252[i] * 0.999):
            continue
        lo, pk = C[i - 10:i].min(), C[i - 30:i - 10].max()
        if not lo <= pk * 0.88 or i - np.argmin(C[i - 10:i]) - (i - 10) > 5:
            continue
        rg = H[i] - L[i]
        if C[i] >= C[i - 1] * 1.03 and C[i] > H[i - 1] and rg > 0 and (C[i] - L[i]) / rg >= TOP_SHARE and V[i] >= 1.2 * v50[i]:
            out.append(n - 1 - i)
    return out


# ---------------------------------------------------------------- sector watcher
def etf_row(t: str, df: pd.DataFrame, bench: pd.Series | None, kind: str) -> dict:
    c = df["Close"]
    row = {"etf": t, "kind": kind, "close": r2(c.iloc[-1]), "d1": ret(c, 1), "d5": ret(c, 5), "d20": ret(c, 20), "d60": ret(c, 60)}
    row.update(averages(c))
    row.update(drop_state(c))
    if bench is not None:
        b = bench.reindex(c.index).ffill()
        for n in (5, 20, 60):
            if len(c) > n and pd.notna(b.iloc[-1 - n]):
                row[f"vs_market_{n}d"] = r2((c.iloc[-1] / c.iloc[-1 - n] - b.iloc[-1] / b.iloc[-1 - n]) * 100, 1)
    row["stage"] = stage_of_group(row.get("drop"), row.get("low_age"), row.get("off_low"), row.get("vs50"), row.get("vs200"))
    return row


def stage_of_group(drop, low_age, off_low, vs50, vs200) -> str:
    """LABEL, not a tested signal."""
    if drop is not None and drop >= REBOUND_DROP:
        if off_low is not None and off_low >= REBOUND_BOUNCE:
            return "turning up"
        if (off_low or 0) < 0 or (low_age is not None and low_age <= 2 and (off_low or 0) < 1):   # under the old low = a new low today
            return "falling"
        return "pulled back"
    if vs50 is not None and vs200 is not None and vs50 > 0 and vs200 > 0:
        return "in trend"
    if vs50 is not None and vs50 < 0 and vs200 is not None and vs200 < 0:
        return "weak"
    return "quiet"


def group_rows(F: dict, grp: dict, sector: dict) -> tuple[list[dict], dict]:
    """One row per stock group (5+ members), from the average daily move of its members.
    "family" = the sector most of its members sit in, so chips, hardware and software count as one story."""
    members = {}
    for t, g in grp.items():
        if t in F:
            members.setdefault(g, []).append(t)
    rows, state = [], {}
    for g, mem in members.items():
        if len(mem) < 5:
            continue
        rets = pd.concat([F[t]["Close"].pct_change().rename(t) for t in mem], axis=1, sort=True)
        ok = rets.notna().sum(axis=1) >= max(3, len(mem) / 2)
        rets = rets[ok]
        r = rets.mean(axis=1)
        lvl = (1 + r.fillna(0)).cumprod()
        if len(lvl) < 60:
            continue
        ds = drop_state(lvl)
        s200 = lvl.rolling(200).mean()
        lead = bool(len(lvl) > 240 and lvl.iloc[-21] > s200.iloc[-21] and s200.iloc[-21] > s200.iloc[-41])
        up_share = float((rets.iloc[-1] >= 0.02).mean())
        above50 = float(np.mean([F[t]["Close"].iloc[-1] > F[t]["Close"].iloc[-50:].mean() for t in mem if len(F[t]) >= 50]))
        rebound = bool(ds["drop"] is not None and ds["drop"] >= REBOUND_DROP and ds["low_age"] <= REBOUND_AGE
                       and ds["off_low"] >= REBOUND_BOUNCE and lead)
        # was it already true yesterday? (so the Scout can say "new today")
        prev = drop_state(lvl.iloc[:-1])
        prev_rebound = bool(prev["drop"] is not None and prev["drop"] >= REBOUND_DROP and prev["low_age"] <= REBOUND_AGE
                            and prev["off_low"] >= REBOUND_BOUNCE and lead)
        av = averages(lvl)
        fam = pd.Series([sector.get(t, "") for t in mem]).mode()
        row = {"group": g, "family": (g if g.startswith("CA ") or fam.empty or not fam.iloc[0] else fam.iloc[0]),
               "members": len(mem), "d1": r2(r.iloc[-1] * 100, 1), "d5": ret(lvl, 5), "d20": ret(lvl, 20),
               "drop": ds["drop"], "low_age": ds["low_age"], "off_low": ds["off_low"], "was_leading": lead,
               "up_2pct_share": r2(up_share * 100, 0), "above_50d_share": r2(above50 * 100, 0), "vs50": av["vs50"], "vs200": av["vs200"],
               "sector_rebound": rebound, "sector_rebound_new": rebound and not prev_rebound,
               "stage": stage_of_group(ds["drop"], ds["low_age"], ds["off_low"], av["vs50"], av["vs200"])}
        rows.append(row)
        state[g] = {"up_share": up_share, "members": mem, "row": row,
                    "up_share_by_day": (rets >= 0.02).mean(axis=1).iloc[-6:].round(3).tolist()}
    order = {"turning up": 0, "falling": 1, "pulled back": 2}
    rows.sort(key=lambda x: (not x["sector_rebound"], order.get(x["stage"], 3), -(x["drop"] or 0)))
    return rows, state


# ---------------------------------------------------------------- price-action worker
def stock_row(t: str, df: pd.DataFrame, group: str | None, gstate: dict | None, name: str = "") -> dict:
    c, v = df["Close"], df["Volume"]
    row = {"ticker": t, "name": name or t, "group": group, "close": r2(c.iloc[-1]), "d1": ret(c, 1), "d5": ret(c, 5), "d20": ret(c, 20),
           "currency": "CAD" if t.endswith((".TO", ".V")) else "USD"}
    row.update(averages(c))
    ds = drop_state(c)
    row.update(ds)
    v50 = float(v.iloc[-51:-1].mean()) if len(v) > 51 else 0
    row["volume_x"] = r2(float(v.iloc[-1]) / v50, 1) if v50 else None
    row["swing_pct"] = r2(((df["High"] - df["Low"]) / df["Close"]).iloc[-20:].mean() * 100, 1)
    if len(c) >= 126:
        row["d126"] = ret(c, 126)
    hi = c.iloc[-252:].max() if len(c) >= 120 else None
    row["off_52wk_high"] = r2((c.iloc[-1] / hi - 1) * 100, 1) if hi else None
    fired = shakeout_days(df)
    row["shakeout_days_ago"] = min(fired) if fired else None
    if fired and gstate:
        # a stock can fire on more than one of the last few days: a day it fired WITH its group counts first
        byday = gstate.get("up_share_by_day") or []
        shares = {k: (byday[-1 - k] if len(byday) > k else None) for k in fired}
        with_g = [k for k, s in shares.items() if s is not None and s >= GROUP_UP_SHARE]
        k = min(with_g) if with_g else min(fired)
        row["shakeout_days_ago"] = k
        row["shakeout_all_days_ago"] = sorted(fired)
        row["shakeout_with_group"] = bool(with_g)
        row["group_up_share_that_day"] = r2((shares[k] or 0) * 100, 0)
    row["stage"] = stage_of_stock(row)
    return row


def stage_of_stock(r: dict) -> str:
    """LABEL. Only 'turning up: entry window' rests on a tested signal (Shakeout Bounce with its group)."""
    drop, age, off = r.get("drop"), r.get("low_age"), r.get("off_low")
    if r.get("shakeout_days_ago") is not None:
        return "turning up: entry window" if r.get("shakeout_with_group") else "turning up alone: watch"
    if r.get("vs50") is not None and r["vs50"] >= 15:
        return "late / stretched"
    if drop is not None and drop >= 12:
        if (off or 0) < 0 or (age is not None and age <= 2 and (off or 0) < 3):   # under the old low = a new low today
            return "falling: wait"
        if off is not None and off >= 8 and r.get("d1") is not None and r["d1"] > 0:
            return "bouncing: watch"
        return "pulled back: watch"
    if (r.get("vs20") or -1) > 0 and (r.get("vs50") or -1) > 0 and (r.get("vs200") or -1) > 0:
        return "in trend"
    if (r.get("vs50") or 1) < 0 and (r.get("vs200") or 1) < 0:
        return "weak"
    return "quiet"


# ---------------------------------------------------------------- Royal B screens + your book
def fetch_json(name: str):
    import requests
    r = requests.get(RESULTS + name, params={"t": int(time.time())}, timeout=120)
    r.raise_for_status()
    return r.json()


def royal_b() -> tuple[dict, dict, dict]:
    """(screens summary, your book, {ticker: earnings days}) from the engine's results branch."""
    st, scan, data = fetch_json("status.json"), fetch_json("scan.json"), fetch_json("data.json")
    slim = lambda s: {"ticker": s.get("ticker"), "name": s.get("name"), "status": s.get("status"), "close": s.get("close"),  # noqa: E731
                      "sector": s.get("sector")}
    stocks = [s for s in scan.get("stocks", []) if s.get("kind") != "ETF"]
    weekly = (scan.get("weekly") or {}).get("rows") or []
    screens = {
        "screen_date": st.get("last_bar") or st.get("date"), "updated": st.get("updated"), "problems": st.get("problems") or {},
        "top5": [{"ticker": x.get("ticker"), "name": x.get("name"), "from": x.get("source_names"), "new": x.get("new")}
                 for x in (scan.get("top5") or {}).get("rows", [])],
        "bullish_turn": st.get("comeback_turn") or [],
        "early_turn_breakout": [slim(s) for s in scan.get("early", []) if s.get("status") == "BREAKOUT"],
        "trend_cross": [slim(s) for s in stocks if str(s.get("status", "")).startswith("TRIGGER") and not s.get("obv_skip")],
        "weekly_new": [slim(s) for s in weekly if s.get("new") or s.get("status") == "WK NEW"][:25],
        "comebacks_moved_up": st.get("comeback_moved_up") or [],
        "gauge": scan.get("breadth"), "credit": scan.get("credit"), "counts": st.get("counts"),
    }
    lists = data.get("lists") or {}
    pos = lambda s: {"ticker": s.get("ticker"), "name": s.get("name"), "close": s.get("close"), "change_pct": s.get("change_pct"),  # noqa: E731
                     "status": s.get("status"), "position": s.get("position"), "lt": s.get("lt"), "earnings": s.get("earnings")}
    book = {"as_of": data.get("last_bar"), "watch": lists.get("watch") or [], "holdings": [pos(s) for s in data.get("holdings", [])],
            "longterm": [pos(s) for s in data.get("longterm", []) if s.get("lt")],
            "note": "From Royal B's daily screen. Share counts and cash live in the page's database, not here."}
    earn = {}
    for s in data.get("stocks", []) + data.get("holdings", []) + data.get("longterm", []) + scan.get("stocks", []) + scan.get("early", []):
        e = s.get("earnings") or {}
        if s.get("ticker") and isinstance(e, dict) and e.get("date"):
            earn.setdefault(s["ticker"], e["date"])
    for t, e in ((scan.get("eh") or {}).get("next") or {}).items():
        if isinstance(e, dict) and e.get("date"):
            earn.setdefault(t, e["date"])
    return screens, book, earn


# ---------------------------------------------------------------- calendar keeper
def earnings_dates(tickers: list[str], known: dict, today: str, max_fetch: int = 60) -> dict:
    """{ticker: {"date", "days"}}: Royal B's dates first, then Yahoo for the rest (cached a day, capped)."""
    try:
        cache = json.load(open(EARN))
    except Exception:  # noqa: BLE001
        cache = {}
    now = time.time()
    todo = [t for t in tickers if t not in known and (t not in cache or now - cache[t].get("at", 0) > 86400)][:max_fetch]
    if todo:
        import yfinance as yf
        from datetime import date
        fails = 0
        for t in todo:
            try:
                cal = yf.Ticker(t).calendar
                ds = sorted(d for d in ((cal or {}).get("Earnings Date") or []) if isinstance(d, date) and d.isoformat() >= today)
                cache[t] = {"date": ds[0].isoformat() if ds else None, "at": now}
                fails = 0
            except Exception as e:  # noqa: BLE001
                fails += 1
                print(f"  earnings {t}: {str(e)[:70]}", file=sys.stderr)
                if fails >= 5:
                    break
            time.sleep(0.15)
        os.makedirs(DATA, exist_ok=True)
        json.dump(cache, open(EARN, "w"))
    out = {}
    for t in tickers:
        d = known.get(t) or (cache.get(t) or {}).get("date")
        if d and d >= today:
            out[t] = {"date": d, "days": int((pd.Timestamp(d) - pd.Timestamp(today)).days)}
    return out


# ---------------------------------------------------------------- run
class IncompletePrices(Exception):
    """The newest day reached only some stocks (Nov 12, 2026: Yahoo sent it for 73 of 633)."""


COMPLETE_SHARE = 0.75  # below this, the newest day is treated as missing. Canada-only holidays stay above it.


def check_complete(F: dict) -> None:
    lasts = [df.index[-1] for df in F.values()]
    newest = max(lasts)
    have = sum(d == newest for d in lasts)
    if have < COMPLETE_SHARE * len(lasts):
        prev = max(d for d in lasts if d < newest) if have < len(lasts) else newest
        raise IncompletePrices(f"prices for {newest:%Y-%m-%d} came for only {have} of {len(lasts)} stocks "
                               f"(the rest stop at {prev:%Y-%m-%d}). Nothing written; try again later.")


def build(asof: str | None, do_download: bool) -> dict:
    t0 = time.time()
    problems = {}
    source = pick_source()
    uni, grp = load_universe(source)
    etfs = US_SECTORS + US_THEMES + CA_SECTORS + list(BENCH.values())
    replay = bool(asof)
    screens, book, known_earn = {}, {}, {}
    if replay:
        problems["replay"] = "past day: Royal B screens, your book and earnings dates are not rebuilt for it"
    else:
        try:
            screens, book, known_earn = royal_b()
        except Exception as e:  # noqa: BLE001
            problems["royal b screens"] = str(e)[:200]
    mine = list(dict.fromkeys((book.get("watch") or []) + [h["ticker"] for h in book.get("holdings", []) + book.get("longterm", [])]))
    tickers = list(dict.fromkeys(uni.ticker.tolist() + etfs + mine))
    if do_download and not replay and source == "eodhd":
        try:
            from prices_eodhd import history
            px, missing = history(tickers, years=2)
            if len(set(px.columns.get_level_values(0))) < 0.9 * len(tickers):
                raise RuntimeError(f"only {len(set(px.columns.get_level_values(0)))} of {len(tickers)} stocks have prices")
            os.makedirs(DATA, exist_ok=True)
            px.to_pickle(PX_EODHD)
            if missing:
                problems["no prices"] = ", ".join(missing[:30])
        except Exception as e:  # noqa: BLE001
            problems["prices"] = f"EODHD failed ({str(e)[:120]}); this run used Yahoo and the old 571-stock list"
            source = "yahoo"
            uni, grp = load_universe("yahoo")
            tickers = list(dict.fromkeys(uni.ticker.tolist() + etfs + mine))
    if source == "yahoo" and do_download and not replay:
        px, missing = download(tickers)
        if missing:
            problems["no prices"] = ", ".join(missing[:30])
    elif not (do_download and not replay):
        path = PX_EODHD if source == "eodhd" and os.path.exists(PX_EODHD) else PX
        if not os.path.exists(path):
            raise SystemExit("No saved prices yet: run once without --asof / --no-download.")
        px = pd.read_pickle(path)
    names = dict(zip(uni.ticker, uni.name))
    F = frames(px, asof)
    check_complete(F)
    day = max(df.index[-1] for df in F.values()).strftime("%Y-%m-%d")

    bench = {k: (F[v]["Close"] if v in F else None) for k, v in BENCH.items()}
    sectors = []
    for kind, lst, b in (("US sector", US_SECTORS, "USD"), ("US theme", US_THEMES, "USD"), ("Canada sector", CA_SECTORS, "CAD")):
        for t in lst:
            if t in F:
                sectors.append(etf_row(t, F[t], bench[b], kind))
    market = {k: etf_row(v, F[v], None, "market") for k, v in BENCH.items() if v in F}
    above50 = [F[t]["Close"].iloc[-1] > F[t]["Close"].iloc[-50:].mean() for t in uni.ticker if t in F and len(F[t]) >= 50]
    market["above_50d_share_large_caps"] = r2(np.mean(above50) * 100, 0) if above50 else None

    sector = ({r.ticker: r.sector for r in uni.itertuples()} if source == "eodhd" else
              {r.ticker: (r.sector if r.group == "SP500" else FOREIGN_SECTOR.get(FOREIGN.get(r.ticker, ""), "")) for r in uni.itertuples()})
    groups, gstate = group_rows(F, grp, sector)
    in_play = [g["group"] for g in groups if g["sector_rebound"] or g["stage"] in ("turning up", "falling", "pulled back")]
    want = set(mine)
    for g in in_play:
        want.update(gstate[g]["members"])
    stocks = {}
    for t in sorted(want):
        if t in F and len(F[t]) >= 60:
            g = grp.get(t)
            stocks[t] = stock_row(t, F[t], g, gstate.get(g), names.get(t, ""))
    # every Shakeout Bounce that fired in the last 4 days, anywhere in the universe
    shake = []
    for t in uni.ticker:
        if t in F:
            row = stocks.get(t) or stock_row(t, F[t], grp.get(t), gstate.get(grp.get(t)), names.get(t, ""))
            if row.get("shakeout_days_ago") is not None:
                stocks[t] = row
                shake.append({"ticker": t, "group": row["group"], "days_ago": row["shakeout_days_ago"],
                              "with_group": row.get("shakeout_with_group", False), "close": row["close"]})
    shake.sort(key=lambda x: (not x["with_group"], x["days_ago"]))

    calendar = {"earnings": {}, "macro": None,
                "macro_note": "Fed, CPI and jobs dates are not fetched here: the Scout looks them up with its news search."}
    if not replay:
        try:
            calendar["earnings"] = earnings_dates(sorted(stocks), known_earn, day)
        except Exception as e:  # noqa: BLE001
            problems["earnings dates"] = str(e)[:200]
    for t, e in calendar["earnings"].items():
        if t in stocks:
            stocks[t]["earnings_in_days"] = e["days"]
            stocks[t]["earnings_date"] = e["date"]

    return {
        "asof": day, "generated": datetime.now(ET).isoformat(timespec="minutes"), "replay": replay, "source": source,
        "universe_size": len(uni),
        "tested": {"sector_rebound": "group was leading, fell 8%+, closed 3%+ off its low within 5 days",
                   "entry_window": "Shakeout Bounce on a day a third+ of its group was up 2%+",
                   "everything_else": "stages are labels, not tested signals"},
        "market": market, "sectors": sectors, "groups": groups, "groups_in_play": in_play,
        "shakeout_signals": shake, "stocks": stocks, "book": book, "royal_b": screens, "calendar": calendar,
        "problems": problems, "seconds": round(time.time() - t0),
    }


def summary(w: dict) -> None:
    print(f"\nRoyal B Scout workers · {w.get('source', 'yahoo')}, {w.get('universe_size')} stocks · prices to {w['asof']}" + (" (replay)" if w["replay"] else "") + f" · {w['seconds']}s")
    m = w["market"]
    print("Market: " + " · ".join(f"{k} {m[k]['d1']:+.1f}% today, {m[k]['d5']:+.1f}% 5d, {m[k]['stage']}" for k in ("USD", "CAD") if k in m)
          + f" · {m.get('above_50d_share_large_caps')}% of large caps above their 50-day")
    etf = sorted(w["sectors"], key=lambda r: -(r.get("drop") or 0))[:6]
    print("Biggest ETF sell-offs: " + ", ".join(f"{r['etf']} -{r['drop']}% ({r['stage']}, {r['off_low']:+.1f}% off low)" for r in etf))
    print("Groups in play:")
    for g in [x for x in w["groups"] if x["group"] in w["groups_in_play"]][:10]:
        tag = " SECTOR REBOUND" + (" (new today)" if g["sector_rebound_new"] else "") if g["sector_rebound"] else ""
        print(f"  {g['group'][:38]:38} {g['stage']:11} fell {g['drop']:4.1f}%  {g['off_low']:+5.1f}% off low  {g['up_2pct_share']:3.0f}% up 2%+ today"
              f"  {'was leading' if g['was_leading'] else 'not leading':11}{tag}")
    if w["shakeout_signals"]:
        print("Shakeout Bounce (last 4 days): " + ", ".join(f"{s['ticker']} ({s['days_ago']}d ago, {'with group' if s['with_group'] else 'alone'})"
                                                            for s in w["shakeout_signals"][:20]))
    else:
        print("Shakeout Bounce (last 4 days): none")
    look = [t for t in ("AMD", "AVGO", "TSM", "MU", "NVDA", "GOOGL") if t in w["stocks"]]
    if look:
        print("Chip names: " + " · ".join(f"{t} {w['stocks'][t]['stage']}" for t in look))
    b = w.get("book") or {}
    if b.get("holdings") or b.get("longterm"):
        print("Your book: " + ", ".join(f"{h['ticker']} {w['stocks'].get(h['ticker'], {}).get('stage', '?')}" for h in b.get("holdings", []) + b.get("longterm", [])))
    rb = w.get("royal_b") or {}
    if rb:
        print(f"Royal B screen of {rb.get('screen_date')}: Top 5 {', '.join(x['ticker'] for x in rb.get('top5', [])) or 'none'}; "
              f"Bullish Turn {', '.join(x['ticker'] for x in rb.get('bullish_turn', [])) or 'none'}")
    if w["problems"]:
        print("Problems: " + "; ".join(f"{k}: {v}" for k, v in w["problems"].items()))


def main() -> int:
    ap = argparse.ArgumentParser(description="Royal B Scout workers")
    ap.add_argument("--asof", help="YYYY-MM-DD: replay a past day from saved prices")
    ap.add_argument("--no-download", action="store_true")
    ap.add_argument("--summary", action="store_true")
    a = ap.parse_args()
    try:
        w = build(a.asof, not a.no_download)
    except IncompletePrices as e:
        print(f"STOPPED: {e}", file=sys.stderr)
        return 2
    os.makedirs(DATA, exist_ok=True)
    name = f"workers-{w['asof']}" + ("-replay" if w["replay"] else "") + ".json"
    with open(os.path.join(DATA, name), "w") as fh:
        json.dump(w, fh, separators=(",", ":"))
    if not w["replay"]:
        with open(os.path.join(HERE, "workers.json"), "w") as fh:
            json.dump(w, fh, separators=(",", ":"))
    if a.summary:
        summary(w)
    print(f"wrote data/{name}" + ("" if w["replay"] else " and workers.json") + f" ({len(w['stocks'])} stocks, {len(w['groups'])} groups, {w['seconds']}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
