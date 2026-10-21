"""
Swing-trade stock screener — US + Canada (Rules v1).

Stage 1  Universe:  price > $5, avg volume > 500K, market cap > $300M (Yahoo screener)
Stage 2  Channel:   50-day MA rising, price above it, higher highs + higher lows
Stage 3  Setup:     10-day MA crossing above 20-day MA with volume strengthening
Hype     Separate list of tickers with spiking Reddit mentions (ApeWisdom)

Run:  python screener.py            -> writes output/watchlist.csv, output/hype.csv, output/report.md
"""
from __future__ import annotations

import os
import sys
import time
from datetime import datetime

import numpy as np
import pandas as pd
import requests

# ---------------------------------------------------------------- settings
CONFIG = {
    "min_price": 5.0,
    "min_avg_volume": 500_000,
    "min_market_cap": 300_000_000,
    "regions": ["us", "ca"],
    "fast_ma": 10,
    "mid_ma": 20,
    "slow_ma": 50,
    "rvol_trigger": 1.5,        # cross-day volume vs 50-day average
    "headsup_gap_pct": 1.0,     # 10-day within this % of 20-day -> heads-up
    "channel_lookback": 20,     # bars used for higher-highs / higher-lows
    "recent_cross_days": 3,     # crosses within N days stay on the watchlist
    "hype_min_mentions": 20,
    "hype_top_n": 25,
}
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")


# ---------------------------------------------------------------- stage 1
def get_universe() -> pd.DataFrame:
    """Ask Yahoo's screener for US + Canadian stocks that pass the size filters."""
    import yfinance as yf
    from yfinance import EquityQuery as Q

    rows = []
    for region in CONFIG["regions"]:
        query = Q("and", [
            Q("eq", ["region", region]),
            Q("gt", ["intradayprice", CONFIG["min_price"]]),
            Q("gt", ["avgdailyvol3m", CONFIG["min_avg_volume"]]),
            Q("gt", ["intradaymarketcap", CONFIG["min_market_cap"]]),
        ])
        offset = 0
        while True:
            try:
                res = yf.screen(query, offset=offset, size=250,
                                sortField="intradaymarketcap", sortAsc=False)
            except Exception as e:  # noqa: BLE001
                print(f"  screener error ({region} @ {offset}): {e}", file=sys.stderr)
                break
            quotes = res.get("quotes", [])
            for q in quotes:
                if q.get("quoteType") != "EQUITY":
                    continue
                rows.append({
                    "ticker": q["symbol"],
                    "name": q.get("shortName") or q.get("longName", ""),
                    "exchange": q.get("fullExchangeName", q.get("exchange", "")),
                    "region": region.upper(),
                    "market_cap": q.get("marketCap"),
                })
            offset += len(quotes)
            if not quotes or offset >= res.get("total", 0):
                break
            time.sleep(0.5)
    uni = pd.DataFrame(rows).drop_duplicates("ticker")
    print(f"Universe: {len(uni)} stocks")
    return uni


def get_history(tickers: list[str], batch: int = 200) -> dict[str, pd.DataFrame]:
    """Download ~1 year of daily bars, in batches."""
    import yfinance as yf

    out: dict[str, pd.DataFrame] = {}
    for i in range(0, len(tickers), batch):
        chunk = tickers[i:i + batch]
        data = yf.download(chunk, period="1y", interval="1d", group_by="ticker",
                           auto_adjust=True, threads=True, progress=False)
        for t in chunk:
            try:
                df = data[t] if len(chunk) > 1 else data
                df = df.dropna(subset=["Close"])
                if len(df) >= 80:
                    out[t] = df
            except KeyError:
                pass
        print(f"  history {min(i + batch, len(tickers))}/{len(tickers)}")
    return out


# ---------------------------------------------------------------- stages 2+3
def analyze(df: pd.DataFrame) -> dict | None:
    """Score one stock against Rules v1. Returns None if not in an upward channel."""
    c, h, l, v = df["Close"], df["High"], df["Low"], df["Volume"]
    f, m, s = CONFIG["fast_ma"], CONFIG["mid_ma"], CONFIG["slow_ma"]
    sma_f, sma_m, sma_s = c.rolling(f).mean(), c.rolling(m).mean(), c.rolling(s).mean()
    vol50 = v.rolling(50).mean()
    vol5 = v.rolling(5).mean()
    n = CONFIG["channel_lookback"]

    # --- upward channel
    slow_rising = sma_s.iloc[-1] > sma_s.iloc[-11]
    above_slow = c.iloc[-1] > sma_s.iloc[-1]
    higher_highs = h.iloc[-n:].max() > h.iloc[-2 * n:-n].max()
    higher_lows = l.iloc[-n:].min() > l.iloc[-2 * n:-n].min()
    channel = bool(slow_rising and above_slow and higher_highs and higher_lows)
    if not channel:
        return None

    # --- volume
    rvol = float(v.iloc[-1] / vol50.iloc[-1]) if vol50.iloc[-1] else 0.0
    vol5_rising = bool(vol5.iloc[-1] > vol5.iloc[-6])

    # --- MA cross
    diff = sma_f - sma_m
    gap_pct = float(-diff.iloc[-1] / sma_m.iloc[-1] * 100)  # >0 means fast still below mid
    crossed = (diff > 0) & (diff.shift(1) <= 0)
    days_since_cross = None
    recent = crossed.iloc[-CONFIG["recent_cross_days"]:]
    if recent.any():
        days_since_cross = int(len(recent) - 1 - np.where(recent.values)[0][-1])
    strong = bool(sma_m.iloc[-1] > sma_s.iloc[-1] and sma_m.iloc[-6] <= sma_s.iloc[-6])

    status = None
    if days_since_cross is not None and vol5_rising:
        cross_idx = -1 - days_since_cross
        cross_rvol = float(v.iloc[cross_idx] / vol50.iloc[cross_idx])
        if cross_rvol >= CONFIG["rvol_trigger"]:
            status = "TRIGGER" if days_since_cross == 0 else f"TRIGGERED {days_since_cross}d ago"
    if status is None and 0 < gap_pct <= CONFIG["headsup_gap_pct"] \
            and diff.iloc[-1] > diff.iloc[-2] and vol5_rising:
        status = "HEADS-UP"
    if status is None:
        return None

    return {
        "status": status,
        "close": round(float(c.iloc[-1]), 2),
        "sma10": round(float(sma_f.iloc[-1]), 2),
        "sma20": round(float(sma_m.iloc[-1]), 2),
        "sma50": round(float(sma_s.iloc[-1]), 2),
        "gap_pct": round(gap_pct, 2),
        "rvol": round(rvol, 2),
        "strong_20x50": strong,
        "exit_level": round(float(sma_s.iloc[-1]), 2),  # trailing exit: close below 50-day (Taylor, Oct 20)
    }


# ---------------------------------------------------------------- hype
def get_hype(universe: set[str] | None = None) -> pd.DataFrame:
    """Separate list: tickers with the biggest jump in Reddit mentions over 24h."""
    try:
        r = requests.get("https://apewisdom.io/api/v1.0/filter/all-stocks/page/1", timeout=20)
        r.raise_for_status()
        results = r.json().get("results", [])
    except Exception as e:  # noqa: BLE001
        print(f"  hype source error: {e}", file=sys.stderr)
        return pd.DataFrame()
    df = pd.DataFrame(results)
    if df.empty:
        return df
    df["mentions"] = pd.to_numeric(df["mentions"], errors="coerce").fillna(0)
    df["mentions_24h_ago"] = pd.to_numeric(df["mentions_24h_ago"], errors="coerce").fillna(0)
    df = df[df["mentions"] >= CONFIG["hype_min_mentions"]].copy()
    df["mention_change_pct"] = ((df["mentions"] - df["mentions_24h_ago"])
                                / df["mentions_24h_ago"].clip(lower=1) * 100).round(0)
    if universe is not None:
        df["passes_universe"] = df["ticker"].isin(universe)
    df = df.sort_values("mention_change_pct", ascending=False).head(CONFIG["hype_top_n"])
    cols = ["ticker", "name", "mentions", "mentions_24h_ago", "mention_change_pct", "rank"]
    if universe is not None:
        cols.append("passes_universe")
    return df[[c for c in cols if c in df.columns]]


# ---------------------------------------------------------------- main
def run() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    uni = get_universe()
    hist = get_history(uni["ticker"].tolist())

    hits = []
    for t, df in hist.items():
        try:
            r = analyze(df)
        except Exception:  # noqa: BLE001
            continue
        if r:
            hits.append({"ticker": t, **r})
    wl = pd.DataFrame(hits)
    if not wl.empty:
        wl = wl.merge(uni[["ticker", "name", "region"]], on="ticker", how="left")
        order = {"TRIGGER": 0, "HEADS-UP": 2}
        wl["_o"] = wl["status"].map(lambda s: order.get(s, 1))
        wl = wl.sort_values(["_o", "rvol"], ascending=[True, False]).drop(columns="_o")
    wl.to_csv(os.path.join(OUT_DIR, "watchlist.csv"), index=False)

    hype = get_hype(set(uni["ticker"]))
    hype.to_csv(os.path.join(OUT_DIR, "hype.csv"), index=False)

    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(os.path.join(OUT_DIR, "report.md"), "w") as fh:
        fh.write(f"# Screener report — {stamp}\n\n")
        fh.write(f"Universe: {len(uni)} | analyzed: {len(hist)} | setups: {len(wl)}\n\n")
        fh.write("## Technical watchlist\n\n")
        fh.write(wl.to_markdown(index=False) if not wl.empty else "_No setups today._")
        fh.write("\n\n## Hype list (separate)\n\n")
        fh.write(hype.to_markdown(index=False) if not hype.empty else "_No hype data._")
        fh.write("\n")
    print(f"Done: {len(wl)} setups, {len(hype)} hype names -> {OUT_DIR}")


if __name__ == "__main__":
    run()
