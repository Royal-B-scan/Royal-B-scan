"""
Signal journal: every TRIGGER and HEADS-UP the rules produced over the last ~3 months,
and how each one did afterwards. Rebuilt on every full scan from price history, so it
always reflects the current rules (no separate state to keep).

For each signal (day t, signal-day close = reference price):
  r5 / r10 / r20   % change in the close 5 / 10 / 20 trading days later (None until that day arrives)
  max20            best close within the next 20 days
  stopped          the low touched 8% below the reference within 20 days
HEADS-UP is recorded on its first day only (not again for the same stock within 10 days).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

LOOKBACK = 65          # trading days of signals to keep (~3 months)
STOP = 0.08


def _signals(df: pd.DataFrame, rvol_min=1.5, gap_max=0.01):
    c, h, l, v = df["Close"], df["High"], df["Low"], df["Volume"]
    s10, s20, s50 = c.rolling(10).mean(), c.rolling(20).mean(), c.rolling(50).mean()
    v50, v5 = v.rolling(50).mean(), v.rolling(5).mean()
    channel = ((c > s50) & (s50 > s50.shift(10))
               & (h.rolling(20).max() > h.shift(20).rolling(20).max())
               & (l.rolling(20).min() > l.shift(20).rolling(20).min()))
    vol5 = v5 > v5.shift(5)
    diff = s10 - s20
    cross = (diff > 0) & (diff.shift(1) <= 0)
    trigger = channel & cross & (v >= rvol_min * v50) & vol5
    gap = -diff / s20
    heads = channel & (gap > 0) & (gap <= gap_max) & (diff > diff.shift(1)) & vol5 & ~trigger
    return trigger.fillna(False), heads.fillna(False)


def build(hist: dict[str, pd.DataFrame], meta: dict) -> dict:
    events = []
    for t, df in hist.items():
        m = meta.get(t, {})
        if m.get("kind") == "ETF" or len(df) < 120:
            continue
        trig, heads = _signals(df)
        n = len(df)
        start = max(60, n - LOOKBACK)
        c, lo = df["Close"].values, df["Low"].values
        idx = df.index
        last_heads = -99
        for i in range(start, n):
            status = "TRIGGER" if trig.iat[i] else ("HEADS-UP" if heads.iat[i] else None)
            if status == "HEADS-UP":
                if i - last_heads < 10:
                    continue
                last_heads = i
            if not status:
                continue
            ref = float(c[i])
            fwd = lambda k: round(float(c[i + k] / ref - 1) * 100, 2) if i + k < n else None  # noqa: E731
            win = slice(i + 1, min(i + 21, n))
            ev = {"ticker": t, "date": idx[i].strftime("%Y-%m-%d"), "status": status,
                  "sector": m.get("sector", "Other"), "close": round(ref, 2),
                  "r5": fwd(5), "r10": fwd(10), "r20": fwd(20),
                  "days": int(n - 1 - i)}
            if i + 1 < n:
                ev["max20"] = round(float(np.max(c[win]) / ref - 1) * 100, 2)
                ev["stopped"] = bool(np.min(lo[win]) <= ref * (1 - STOP))
            events.append(ev)
    events.sort(key=lambda e: (e["date"], e["status"] != "TRIGGER"), reverse=True)

    def stats(evs):
        out = {"n": len(evs)}
        for k in ("r5", "r10", "r20"):
            vals = [e[k] for e in evs if e.get(k) is not None]
            out[k] = {"n": len(vals),
                      "up_pct": round(sum(v > 0 for v in vals) / len(vals) * 100, 1) if vals else None,
                      "avg": round(float(np.mean(vals)), 2) if vals else None,
                      "median": round(float(np.median(vals)), 2) if vals else None}
        done = [e for e in evs if e.get("days", 0) >= 20]
        out["stop_pct"] = round(sum(e.get("stopped", False) for e in done) / len(done) * 100, 1) if done else None
        out["max20_avg"] = round(float(np.mean([e["max20"] for e in done])), 2) if done else None
        return out

    summary = {s: stats([e for e in events if e["status"] == s]) for s in ("TRIGGER", "HEADS-UP")}
    dates = [e["date"] for e in events]
    return {"from": min(dates) if dates else None, "to": max(dates) if dates else None,
            "summary": summary, "events": events[:1500]}
