"""
Full-market scan: US + Canadian stocks and ETFs -> site/scan.json

Universe (Rules v1, Oct 20):
  exchanges  NYSE, Nasdaq, NYSE American, NYSE Arca / Cboe BZX (ETFs), TSX, TSXV  (no OTC)
  price      > $5
  liquidity  price x 50-day avg volume >= $5M per day (local currency)
  stocks     market cap > $300M

python scan.py      (also run from the app's "Scan market" button)
"""
from __future__ import annotations

import json
import os
import pickle
import re
import sys
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pandas as pd

from screener import CONFIG, analyze, get_hype, rvol_for

BASE = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.join(BASE, "site")
CACHE = os.path.join(BASE, "cache")
CACHE_FILE = os.path.join(CACHE, "history.pkl")

MIN_DOLLAR_VOL = 5_000_000
MIN_ETF_DOLLAR_VOL = 25_000_000   # ETFs: only the liquid ones (keeps the scan fast)
STOCK_EXCH = {"NYQ", "NMS", "NGM", "NCM", "ASE", "TOR", "VAN"}
ETF_EXCH = STOCK_EXCH | {"PCX", "BTS"}
EXCH_NAME = {"NYQ": "NYSE", "NMS": "Nasdaq", "NGM": "Nasdaq", "NCM": "Nasdaq", "ASE": "NYSE American",
             "PCX": "NYSE Arca", "BTS": "Cboe BZX", "TOR": "TSX", "VAN": "TSXV"}
MAX_RESULTS = 60          # TRIGGER / HEADS-UP setups (full charts incl. hourly/weekly/monthly)
MAX_SETTING_UP = 100      # "setting up" leaders (daily chart only)
SECTORS = ["Technology", "Healthcare", "Financial Services", "Industrials", "Consumer Cyclical",
           "Consumer Defensive", "Communication Services", "Energy", "Basic Materials", "Real Estate", "Utilities"]
LEVERAGED = re.compile(r"\b(\d(\.\d+)?x|ultra|ultrapro|bull|bear|inverse|leveraged|short|daily|"
                       r"-\d(\.\d+)?x|2x|3x|direxion|proshares ultra|bets?|yieldmax|option income)\b", re.I)


def _floor(kind, currency) -> float:
    """Daily dollar-volume minimum. US ETFs need more; Canadian ETFs trade far less."""
    if kind == "ETF" and currency != "CAD":
        return MIN_ETF_DOLLAR_VOL
    return MIN_DOLLAR_VOL


def _noop(*_a, **_k):
    pass


# ---------------------------------------------------------------- universe
def _screen_all(query, label, progress):
    import yfinance as yf

    rows, offset, total = [], 0, None
    while True:
        res = None
        for attempt in range(6):
            try:
                res = yf.screen(query, offset=offset, size=250, sortField="intradayprice", sortAsc=False)
                break
            except Exception as e:  # noqa: BLE001
                print(f"  screen retry {attempt + 1} ({label}): {e}", file=sys.stderr)
                progress("Finding stocks", None, None, f"{label}: Yahoo is busy, retrying")
                time.sleep(3 + attempt * 4)
        if res is None:
            raise RuntimeError(f"Yahoo wouldn't return the {label} list. Wait a few minutes and scan again")
        quotes = res.get("quotes", [])
        total = res.get("total", 0)
        rows += quotes
        offset += len(quotes)
        progress("Finding stocks", None, None, f"{label}: {offset} of {total}")
        if not quotes or offset >= total:
            break
        time.sleep(0.4)
    return rows


def get_universe(progress=_noop) -> pd.DataFrame:
    from yfinance import EquityQuery as Q, ETFQuery as E

    out = []
    for region in ("us", "ca"):
        for sector in SECTORS:
            stocks = _screen_all(Q("and", [
                Q("eq", ["region", region]),
                Q("eq", ["sector", sector]),
                Q("gt", ["intradayprice", CONFIG["min_price"]]),
                Q("gt", ["avgdailyvol3m", 50_000]),
                Q("gt", ["intradaymarketcap", CONFIG["min_market_cap"]]),
            ]), f"{region.upper()} {sector}", progress)
            for q in stocks:
                if q.get("quoteType") == "EQUITY" and q.get("exchange") in STOCK_EXCH:
                    q["_sector"] = sector
                    out.append((q, "Stock"))
        etfs = _screen_all(E("and", [
            E("eq", ["region", region]),
            E("gt", ["intradayprice", CONFIG["min_price"]]),
            E("gt", ["avgdailyvol3m", 50_000]),
        ]), f"{region.upper()} ETFs", progress)
        for q in etfs:
            if q.get("exchange") in ETF_EXCH:
                q["_sector"] = "ETFs"
                out.append((q, "ETF"))
    def dollar_vol(q):
        px = q.get("regularMarketPrice") or 0
        av = q.get("averageDailyVolume3Month") or q.get("averageDailyVolume10Day") or 0
        return px * av

    # pre-filter on Yahoo's own 3-month averages (with slack) so we only download likely candidates
    out = [(q, k) for q, k in out
           if dollar_vol(q) >= _floor(k, q.get("currency")) * 0.7]
    # leveraged / inverse ETFs decay over multi-day holds -> leave them out of a swing scan
    out = [(q, k) for q, k in out if not (k == "ETF" and LEVERAGED.search(
        f'{q.get("shortName", "")} {q.get("longName", "")}'))]
    uni = pd.DataFrame([{
        "ticker": q["symbol"],
        "name": q.get("shortName") or q.get("longName") or q["symbol"],
        "exchange": EXCH_NAME.get(q.get("exchange"), q.get("fullExchangeName", "")),
        "currency": q.get("currency") or ("CAD" if q["symbol"].endswith((".TO", ".V")) else "USD"),
        "sector": q.get("_sector", "Other"),
        "market_cap": q.get("marketCap") or 0,
        "kind": kind,
    } for q, kind in out])
    return uni.drop_duplicates("ticker").reset_index(drop=True)


# ---------------------------------------------------------------- history (cached)
def _load_cache() -> dict:
    try:
        with open(CACHE_FILE, "rb") as fh:
            return pickle.load(fh)
    except Exception:  # noqa: BLE001
        return {}


def _save_cache(cache: dict) -> None:
    os.makedirs(CACHE, exist_ok=True)
    tmp = CACHE_FILE + ".tmp"
    with open(tmp, "wb") as fh:
        pickle.dump(cache, fh, protocol=pickle.HIGHEST_PROTOCOL)
    os.replace(tmp, CACHE_FILE)


def _download(tickers, period):
    import yfinance as yf

    for attempt in range(3):
        try:
            return yf.download(tickers, period=period, interval="1d", group_by="ticker",
                               auto_adjust=True, threads=True, progress=False)
        except Exception as e:  # noqa: BLE001
            print(f"  download retry {attempt + 1}: {e}", file=sys.stderr)
            time.sleep(3 + attempt * 5)
    return None


def update_history(tickers: list[str], progress=_noop, batch: int = 250) -> dict[str, pd.DataFrame]:
    cache = _load_cache()
    fresh = [t for t in tickers if t in cache]
    new = [t for t in tickers if t not in cache]
    jobs = [(new[i:i + batch], "1y") for i in range(0, len(new), batch)] + \
           [(fresh[i:i + batch * 2], "1mo") for i in range(0, len(fresh), batch * 2)]
    done = 0
    for chunk, period in jobs:
        data = _download(chunk, period)
        if data is not None:
            for t in chunk:
                try:
                    df = data[t] if len(chunk) > 1 else data
                    df = df.dropna(subset=["Close"])[["Open", "High", "Low", "Close", "Volume"]]
                except (KeyError, TypeError):
                    continue
                if df.empty:
                    continue
                if t in cache and period != "1y":
                    df = pd.concat([cache[t], df])
                    df = df[~df.index.duplicated(keep="last")].sort_index()
                cache[t] = df.iloc[-300:]
        done += len(chunk)
        progress("Downloading prices", done, len(tickers), None)
        time.sleep(0.3)
    _save_cache(cache)
    return {t: cache[t] for t in tickers if t in cache}


# ---------------------------------------------------------------- scan
def market_open_now() -> bool:
    now = datetime.now(ZoneInfo("America/New_York"))
    return now.weekday() < 5 and (9, 30) <= (now.hour, now.minute) < (16, 0)


def _bench_close(hist, ticker):
    df = hist.get(ticker)
    if df is None:
        try:
            df = update_history([ticker]).get(ticker)
        except Exception:  # noqa: BLE001
            df = None
    return None if df is None else df["Close"]


def profile(df: pd.DataFrame, bench: pd.Series | None) -> dict:
    """Quick trend + relative-strength read used for 'setting up' and the heat map."""
    c, h, l = df["Close"], df["High"], df["Low"]
    s50 = c.rolling(50).mean()
    channel = bool(c.iloc[-1] > s50.iloc[-1] and s50.iloc[-1] > s50.iloc[-11]
                   and h.iloc[-20:].max() > h.iloc[-40:-20].max()
                   and l.iloc[-20:].min() > l.iloc[-40:-20].min())
    r1d = float(c.iloc[-1] / c.iloc[-2] - 1)
    r1m = float(c.iloc[-1] / c.iloc[-22] - 1) if len(c) > 22 else 0.0
    r3m = float(c.iloc[-1] / c.iloc[-64] - 1) if len(c) > 64 else 0.0
    rs3m, rs_high = 0.0, False
    if bench is not None:
        b = bench.reindex(c.index).ffill()
        if len(b.dropna()) > 64:
            rs3m = r3m - float(b.iloc[-1] / b.iloc[-64] - 1)
            rs = (c / b).dropna()
            rs_high = bool(rs.iloc[-1] >= rs.iloc[-63:].max() * 0.98)
    return {"channel": channel, "r1d": r1d, "r1m": r1m, "r3m": r3m, "rs3m": rs3m, "rs_high": rs_high}


def run_scan(progress=_noop) -> dict:
    from export_site import make_entry

    t0 = time.time()
    progress("Finding stocks", None, None, "Asking Yahoo for the list")
    uni = get_universe(progress)
    meta = uni.set_index("ticker").to_dict("index")
    hist = update_history(uni["ticker"].tolist(), progress)
    bench = {"USD": _bench_close(hist, "SPY"), "CAD": _bench_close(hist, "XIU.TO")}

    progress("Checking rules", None, None, None)
    liquid, hits, setting_up, rows = 0, [], [], []
    for t, df in hist.items():
        if len(df) < 80:
            continue
        m = meta.get(t, {})
        dollar_vol = float(df["Close"].iloc[-1] * df["Volume"].iloc[-50:].mean())
        if dollar_vol < _floor(m.get("kind"), m.get("currency")) or df["Close"].iloc[-1] <= CONFIG["min_price"]:
            continue
        liquid += 1
        try:
            pr = profile(df, bench.get(m.get("currency", "USD")) if bench.get(m.get("currency", "USD")) is not None else bench["USD"])
            sig = analyze(df, rvol_for(m.get("market_cap", 0)))
        except Exception:  # noqa: BLE001
            continue
        rows.append({"ticker": t, "sector": m.get("sector", "Other"), **pr})
        if sig or (pr["channel"] and pr["rs_high"] and pr["rs3m"] > 0):
            status_sig = sig or {"status": "SETTING UP", "exit_level": round(float(df["Close"].rolling(50).mean().iloc[-1]), 2),
                                 "rvol": round(float(df["Volume"].iloc[-1] / df["Volume"].iloc[-50:].mean()), 2)}
            entry = make_entry(t, df, m.get("name", t), m.get("currency", "USD"), m.get("exchange", ""), status_sig)
            entry.update(kind=m.get("kind", "Stock"), sector=m.get("sector", "Other"), market_cap=m.get("market_cap", 0),
                         dollar_vol=round(dollar_vol), rs3m=round(pr["rs3m"] * 100, 1), r1m=round(pr["r1m"] * 100, 1),
                         rs_high=pr["rs_high"])
            (hits if sig else setting_up).append(entry)

    order = lambda s: 0 if s["status"] == "TRIGGER" else 1 if s["status"].startswith("TRIGGERED") else 2  # noqa: E731
    hits.sort(key=lambda s: (order(s), -s["rs3m"]))
    setting_up.sort(key=lambda s: -s["rs3m"])
    setting_up = setting_up[:MAX_SETTING_UP]
    hits = hits[:MAX_RESULTS]
    # Oct 28: every screen that fails is recorded here and shown in red on the page, instead of a silent zero
    problems = {}
    try:
        from export_site import timeframes
        progress("Loading hourly/weekly/monthly charts", None, None, None)
        extra = timeframes([h["ticker"] for h in hits])
        for h in hits:
            h["tf"] = extra.get(h["ticker"], {})
    except Exception as e:  # noqa: BLE001
        print("timeframes failed:", e, file=sys.stderr)
        problems["charts"] = str(e)[:200]

    progress("Checking earnings dates and buzz", None, None, None)
    try:
        import earnings
        earnings.attach(hits + setting_up)
    except Exception as e:  # noqa: BLE001
        print("earnings failed:", e, file=sys.stderr)
        problems["earnings"] = str(e)[:200]
    try:
        import hype as hype_mod
        hype_mod.attach(hits + setting_up, hype_mod.get_hype())
    except Exception as e:  # noqa: BLE001
        print("hype failed:", e, file=sys.stderr)
        problems["buzz"] = str(e)[:200]

    # sector strength across every liquid stock (ETFs kept separate)
    prof = pd.DataFrame(rows)
    sectors = []
    if not prof.empty:
        for sec, g in prof.groupby("sector"):
            sectors.append({"sector": sec, "n": int(len(g)),
                            "in_channel_pct": round(float(g["channel"].mean() * 100), 1),
                            "leaders_pct": round(float((g["rs_high"] & g["channel"]).mean() * 100), 1),
                            "median_1d": round(float(g["r1d"].median() * 100), 2),
                            "median_1m": round(float(g["r1m"].median() * 100), 2),
                            "median_rs3m": round(float(g["rs3m"].median() * 100), 2)})
        sectors.sort(key=lambda x: -x["median_rs3m"])

    # Early Entry screener (Oct 24): large caps before Crown Cross sees them (earlyentry.py)
    early = []
    try:
        import earlyentry
        progress("Early Entry screen", None, None, None)
        srank = {x["sector"]: i + 1 for i, x in enumerate(sectors)}
        early = earlyentry.screen(hist, meta, bench, srank)
        try:
            import earnings
            earnings.attach(early)
        except Exception as e:  # noqa: BLE001
            print("early earnings failed:", e, file=sys.stderr)
            problems["early entry earnings"] = str(e)[:200]
    except Exception as e:  # noqa: BLE001
        print("early entry failed:", e, file=sys.stderr)
        problems["early entry"] = str(e)[:200]

    # Market breadth meter (Oct 26): % of liquid stocks above their 50-day (breadth.py)
    breadth = None
    try:
        import breadth as breadth_mod
        progress("Market breadth", None, None, None)
        breadth = breadth_mod.compute(hist, meta)
    except Exception as e:  # noqa: BLE001
        print("breadth failed:", e, file=sys.stderr)
        problems["breadth"] = str(e)[:200]

    counts = {
        "universe": len(uni),
        "stocks": int((uni["kind"] == "Stock").sum()),
        "etfs": int((uni["kind"] == "ETF").sum()),
        "liquid": liquid,
        "hits": len(hits),
        "trigger": sum(1 for h in hits if h["status"] == "TRIGGER"),
        "triggered": sum(1 for h in hits if h["status"].startswith("TRIGGERED")),
        "headsup": sum(1 for h in hits if h["status"] == "HEADS-UP"),
        "setting_up": len(setting_up),
        "early_breakout": sum(1 for e in early if e["status"] == "BREAKOUT"),
        "early_pullback": sum(1 for e in early if e["status"] == "PULLBACK"),
        "early_squeeze": sum(1 for e in early if e["status"] == "SQUEEZE"),
    }
    out = {
        "updated": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "last_bar": max((df.index[-1] for df in hist.values()), default=None),
        "market_open": market_open_now(),
        "seconds": round(time.time() - t0),
        "counts": counts,
        "sectors": sectors,
        "stocks": hits + setting_up,
        "early": early,
        "breadth": breadth,
        "problems": problems,
    }
    try:
        import journal
        progress("Updating the signal journal", None, None, None)
        out["journal"] = journal.build(hist, meta)
    except Exception as e:  # noqa: BLE001
        print("journal failed:", e, file=sys.stderr)
        problems["journal"] = str(e)[:200]
    if out["last_bar"] is not None:
        out["last_bar"] = out["last_bar"].strftime("%Y-%m-%d")
    os.makedirs(SITE, exist_ok=True)
    tmp = os.path.join(SITE, "scan.json.tmp")
    with open(tmp, "w") as fh:
        json.dump(out, fh, separators=(",", ":"))
    os.replace(tmp, os.path.join(SITE, "scan.json"))
    return out


if __name__ == "__main__":
    def show(stage, done, total, note):
        print(f"{stage}: {done}/{total}" if total else f"{stage}: {note or ''}", flush=True)
    res = run_scan(show)
    print(json.dumps(res["counts"]), f"{res['seconds']}s")
