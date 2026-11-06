"""
Weekly Trend screener (Taylor + Gene, decided Nov 4, 2026). INFO ONLY: it never feeds Today, Watch Alerts or the crowns.

Gene's "ride the wave longer" idea on weekly bars, as tested in backtest-gene-rules.md (the steadiest test:
2023-25 PF 2.21, 2026 out-of-sample PF 1.14 with a 15% stop, holds about 3-4 months).

  Signal  the weekly 8-EMA crosses above the weekly 21-SMA, and that week closed above a rising 40-week SMA
          (rising = higher than 4 weeks earlier)
  Exit    the weekly 8-EMA closes below the weekly 21-SMA, or the 15% safety stop (15% below the cross-week close)
  When    completed weeks only, so the list changes after Friday's close. Prices (and the stop check) update daily.

Universe: the scan's liquid stocks (no ETFs). Shows every stock that crossed in the last WINDOW_WEEKS completed weeks
and hasn't exited since. Each row carries ~2 years of weekly bars (for the 8/21 chart) and ~6 months of daily bars.

    screen(hist, meta, tickers) -> {"asof", "week", "rows": [...], "counts": {...}}
"""
from __future__ import annotations

import sys
import time

import pandas as pd

WINDOW_WEEKS = 6      # show crosses from the last 6 completed weeks that are still in trend
STOP_PCT = 15         # safety stop below the cross-week close
RISING_WEEKS = 4      # the 40-week SMA must be higher than it was this many weeks earlier
DAILY_BARS = 130      # daily bars sent with each row (about 6 months)
MAX_ROWS = 250


def weekly_bars(df: pd.DataFrame) -> pd.DataFrame:
    """Daily OHLCV -> Monday-to-Friday weeks. 'start' = first trading day of the week, 'end' = last one so far."""
    d = df.assign(_d=df.index)
    g = d.groupby(df.index.to_period("W-FRI"))
    w = g.agg(Open=("Open", "first"), High=("High", "max"), Low=("Low", "min"), Close=("Close", "last"),
              Volume=("Volume", "sum"), start=("_d", "first"), end=("_d", "last"))
    return w.reset_index(drop=True)


def _complete(w: pd.DataFrame) -> pd.DataFrame:
    """Drop the week still in progress. A week is done once its Friday has closed (holiday weeks finish on Monday)."""
    if len(w) and pd.Timestamp(w["end"].iloc[-1]).weekday() != 4:
        return w.iloc[:-1]
    return w


def signal(df: pd.DataFrame) -> dict | None:
    """The most recent weekly 8/21 cross in the last WINDOW_WEEKS completed weeks that is still in trend, or None."""
    w = _complete(weekly_bars(df))
    if len(w) < 40 + RISING_WEEKS + 1:
        return None
    c = w["Close"]
    ema8 = c.ewm(span=8, adjust=False).mean()
    sma21 = c.rolling(21).mean()
    sma40 = c.rolling(40).mean()
    n = len(w)
    above = ema8 > sma21
    for k in range(n - 1, max(n - 1 - WINDOW_WEEKS, 0), -1):
        if pd.isna(sma40.iloc[k - RISING_WEEKS]) or pd.isna(sma21.iloc[k - 1]):
            break
        crossed = bool(above.iloc[k] and not above.iloc[k - 1])
        if not crossed:
            continue
        if not (c.iloc[k] > sma40.iloc[k] and sma40.iloc[k] > sma40.iloc[k - RISING_WEEKS]):
            return None          # the latest cross didn't qualify; an older one would have exited at it anyway
        if not bool(above.iloc[k:].all()):
            return None          # weekly 8 closed back below the 21 since: exited
        cross_close = float(c.iloc[k])
        stop = cross_close * (1 - STOP_PCT / 100)
        after = df[df.index > pd.Timestamp(w["end"].iloc[k])]
        stop_hit = bool(len(after) and float(after["Low"].min()) <= stop)
        last = float(df["Close"].iloc[-1])
        return {
            "cross_date": pd.Timestamp(w["end"].iloc[k]).strftime("%Y-%m-%d"),
            "cross_close": round(cross_close, 2),
            "weeks_ago": int(n - 1 - k),
            "pct_above": round((last / cross_close - 1) * 100, 1),
            "ema8": round(float(ema8.iloc[-1]), 2),
            "sma21": round(float(sma21.iloc[-1]), 2),
            "sma40": round(float(sma40.iloc[-1]), 2),
            "gap_pct": round(float((ema8.iloc[-1] / sma21.iloc[-1] - 1) * 100), 1),
            "stop": round(stop, 2),
            "stop_hit": stop_hit,
            "week": pd.Timestamp(w["end"].iloc[-1]).strftime("%Y-%m-%d"),
        }
    return None


def _bars(df: pd.DataFrame, date_col=None) -> dict:
    """Compact candles + volume (the page adds the moving averages itself)."""
    out = {"candles": [], "volume": []}
    for i, (ts, r) in enumerate(df.iterrows()):
        t = pd.Timestamp(r[date_col] if date_col else ts).strftime("%Y-%m-%d")
        out["candles"].append([t, *(round(float(r[k]), 2) for k in ("Open", "High", "Low", "Close"))])
        out["volume"].append([t, int(r["Volume"]), bool(r["Close"] >= r["Open"])])
    return out


def _yahoo_weekly(tickers: list[str]) -> dict[str, pd.DataFrame]:
    """2 years of Yahoo weekly bars for the chart (falls back to weeks built from the daily cache)."""
    import yfinance as yf

    out = {}
    for i in range(0, len(tickers), 100):
        chunk = tickers[i:i + 100]
        try:
            data = yf.download(chunk, period="2y", interval="1wk", group_by="ticker",
                               auto_adjust=True, threads=True, progress=False)
        except Exception as e:  # noqa: BLE001
            print("weekly chart download failed:", e, file=sys.stderr)
            continue
        for t in chunk:
            try:
                df = (data[t] if isinstance(data.columns, pd.MultiIndex) else data).dropna(subset=["Close"])
            except (KeyError, TypeError):
                continue
            if len(df) >= 30:
                out[t] = df
        time.sleep(0.3)
    return out


def screen(hist: dict[str, pd.DataFrame], meta: dict, tickers: list[str] | None = None) -> dict:
    tickers = tickers if tickers is not None else list(hist)
    rows, week = [], None
    for t in tickers:
        m = meta.get(t, {})
        if m.get("kind", "Stock") != "Stock":
            continue
        df = hist.get(t)
        if df is None or len(df) < 200:
            continue
        try:
            sig = signal(df)
        except Exception:  # noqa: BLE001
            continue
        if not sig:
            continue
        week = max(week or sig["week"], sig["week"])
        c = df["Close"]
        status = "WK STOP" if sig["stop_hit"] else "WK NEW" if sig["weeks_ago"] == 0 else "WK HOLD"
        rows.append({
            "ticker": t, "name": m.get("name", t), "currency": m.get("currency", "USD"), "exchange": m.get("exchange", ""),
            "sector": m.get("sector", "Other"), "market_cap": m.get("market_cap", 0), "kind": "Stock",
            "close": round(float(c.iloc[-1]), 2), "change": round(float(c.iloc[-1] - c.iloc[-2]), 2),
            "change_pct": round(float((c.iloc[-1] / c.iloc[-2] - 1) * 100), 2),
            "status": status, "wk": sig, "checks": [],
            "series": _bars(df.iloc[-DAILY_BARS:]),
        })
    order = {"WK NEW": 0, "WK HOLD": 1, "WK STOP": 2}
    rows.sort(key=lambda r: (order[r["status"]], r["wk"]["weeks_ago"], -(r["market_cap"] or 0)))
    rows = rows[:MAX_ROWS]
    yw = _yahoo_weekly([r["ticker"] for r in rows]) if rows else {}
    for r in rows:
        df = yw.get(r["ticker"])
        r["wkbars"] = _bars(df) if df is not None else _bars(weekly_bars(hist[r["ticker"]]), "start")
    counts = {"new": sum(r["status"] == "WK NEW" for r in rows), "holding": sum(r["status"] == "WK HOLD" for r in rows),
              "stop": sum(r["status"] == "WK STOP" for r in rows), "total": len(rows)}
    return {"week": week, "window_weeks": WINDOW_WEEKS, "stop_pct": STOP_PCT, "rows": rows, "counts": counts}


if __name__ == "__main__":   # quick test: python weekly.py AAPL MSFT NVDA
    import yfinance as yf

    T = sys.argv[1:] or ["AAPL", "MSFT", "NVDA", "SHOP.TO"]
    data = yf.download(T, period="2y", interval="1d", group_by="ticker", auto_adjust=True, progress=False)
    H = {t: (data[t] if len(T) > 1 else data).dropna(subset=["Close"]).iloc[-300:] for t in T}
    res = screen(H, {})
    print(res["week"], res["counts"])
    for r in res["rows"]:
        print(r["ticker"], r["status"], r["wk"])
