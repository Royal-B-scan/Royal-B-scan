"""
Early Entry screener (Taylor, Oct 24, 2026): find big stocks BEFORE Crown Cross does.

Large companies only (market cap >= $10B, US + CA, no ETFs), computed from the same daily history as the
full screen. Three signals (all on today's close):

  SQUEEZE   (watch)  after a decline (50-day lower than 40 days ago), the 10/20/50-day averages bunch
                     within 2% of each other and the price closes above all three. TMO on Jun 22, 2026.
  BREAKOUT  (buy)    close at a new 60-day high with the averages stacked 10 > 20 > 50, within 30 days of a
                     squeeze. TMO on Jul 16, 2026 ($543; Crown Cross only crowned it Oct 20 at ~$687).
  PULLBACK  (buy)    a leader (new 60-day high within the last 15 days, averages stacked, 50-day rising)
                     dips so the day's low touches the 20-day (within 1%) and closes back above it.

Backtest (Aug 2024 - Oct 2026, ~3,000 US + CA stocks, buy at the close, exit 8% stop or close below the
50-day; see early-entry-backtest.md): large-cap PULLBACK PF 1.64 (1.48 without the top 10 trades), 15% hit
the stop; large-cap BREAKOUT PF 1.24 (1.07). A "hot sector" filter (top-3 sectors by 3-month return) did
NOT help breakouts (PF 0.83) - hot sectors are usually late - so sector heat is shown, not filtered.
To keep the list short, each signal is capped and ranked by 3-month strength vs the market.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
MIN_CAP = 2_000_000_000
LIMITS = {"BREAKOUT": 25, "PULLBACK": 25, "SQUEEZE": 25}


def signals(df: pd.DataFrame) -> dict | None:
    """Today's Early Entry signal for one stock, or None."""
    if len(df) < 120:
        return None
    c, h, l = df["Close"], df["High"], df["Low"]
    s10, s20, s50 = c.rolling(10).mean(), c.rolling(20).mean(), c.rolling(50).mean()
    hi60 = h.rolling(60).max().shift(1)
    top = pd.concat([s10, s20, s50], axis=1).max(axis=1)
    bot = pd.concat([s10, s20, s50], axis=1).min(axis=1)
    band = top / bot - 1
    squeeze = (band <= 0.02) & (c > top) & (s50 < s50.shift(40))
    stacked = (s10 > s20) & (s20 > s50)
    newhi = c > hi60
    sq_recent = squeeze.rolling(31, min_periods=1).max().astype(bool)       # a squeeze within 30 days
    breakout = newhi & stacked & sq_recent
    recent_hi = newhi.rolling(15, min_periods=1).max().astype(bool)
    pullback = stacked & (s50 > s50.shift(10)) & recent_hi & (l <= s20 * 1.01) & (c >= s20) & (c > s50)
    i = -1
    status = "BREAKOUT" if breakout.iloc[i] else "PULLBACK" if pullback.iloc[i] else "SQUEEZE" if squeeze.iloc[i] else None
    if not status:
        return None
    last_sq = squeeze[squeeze].index[-1].strftime("%Y-%m-%d") if squeeze.any() else None
    return {"status": status, "close": round(float(c.iloc[i]), 2),
            "sma10": round(float(s10.iloc[i]), 2), "sma20": round(float(s20.iloc[i]), 2), "sma50": round(float(s50.iloc[i]), 2),
            "band_pct": round(float(band.iloc[i] * 100), 2), "high60": round(float(hi60.iloc[i]), 2),
            "squeeze_date": last_sq, "exit_level": round(float(s50.iloc[i]), 2),
            "rvol": round(float(df["Volume"].iloc[-1] / df["Volume"].iloc[-50:].mean()), 2)}


def screen(hist: dict, meta: dict, bench: dict | None = None, sector_rank: dict | None = None) -> list[dict]:
    """Early Entry entries (with charts) for the page. bench = {"USD": SPY close, "CAD": XIU.TO close}."""
    from export_site import make_entry

    found = []
    for t, df in hist.items():
        m = meta.get(t, {})
        if m.get("kind") == "ETF" or (m.get("market_cap") or 0) < MIN_CAP:
            continue
        if float(df["Close"].iloc[-1] * df["Volume"].iloc[-50:].mean()) < 5e6:
            continue
        try:
            sig = signals(df)
        except Exception:  # noqa: BLE001
            continue
        if not sig:
            continue
        c = df["Close"]
        r3m = float(c.iloc[-1] / c.iloc[-64] - 1) if len(c) > 64 else 0.0
        b = (bench or {}).get(m.get("currency", "USD"))
        rs3m = r3m
        if b is not None:
            bb = b.reindex(c.index).ffill()
            if len(bb.dropna()) > 64:
                rs3m = r3m - float(bb.iloc[-1] / bb.iloc[-64] - 1)
        found.append((sig["status"], rs3m, t, df, m, sig))
    out = []
    for st, n in LIMITS.items():
        rows = sorted([f for f in found if f[0] == st], key=lambda f: -f[1])[:n]
        for _, rs3m, t, df, m, sig in rows:
            e = make_entry(t, df, m.get("name", t), m.get("currency", "USD"), m.get("exchange", ""),
                           {"status": st, "exit_level": sig["exit_level"], "rvol": sig["rvol"]})
            e.update(kind="Stock", sector=m.get("sector", "Other"), market_cap=m.get("market_cap", 0),
                     rs3m=round(rs3m * 100, 1), ee=sig, screener="early",
                     sector_rank=(sector_rank or {}).get(m.get("sector")))
            out.append(e)
    return out
