"""
Comeback Turn (Taylor, decided Nov 9, 2026): the first close back above the 20-day after an oversold low,
on a beaten-down large cap. Test: backtest-comeback-turn.md (2023-25 PF 1.96, 2026 out-of-sample PF 1.13,
about 1 in 3 hit the stop, profit comes from a few big runners). Starter size, hold winners to the 50-day exit.

  beaten down   >= 25% below the 2-year high AND >= 15 points behind SPY over 12 months, on any day in the last 60
  oversold      RSI-14 under 30 on any day in the last 30
  base          no new 60-day closing low in the last 7 days
  signal        today closes above the 20-day after closing at or below it yesterday

    signal_series(df, spy) -> bool Series (every day)
    turn(df, spy) -> dict for today, or None
"""
from __future__ import annotations

import pandas as pd

from context import rsi_series

DD_MIN = -0.25
LAG_MIN = -0.15
BEATEN_DAYS = 60
OVERSOLD_DAYS = 30
BASE_DAYS = 5
STOP_PCT = 8


def signal_series(df: pd.DataFrame, spy: pd.Series | None) -> pd.Series:
    c = df["Close"]
    s20 = c.rolling(20).mean()
    dd = c / c.rolling(504, min_periods=250).max() - 1
    r1y = c / c.shift(252) - 1
    if spy is not None:
        b = spy.reindex(c.index).ffill()
        lag = r1y - (b / b.shift(252) - 1)
    else:
        lag = pd.Series(float("nan"), index=c.index)
    beaten = ((dd <= DD_MIN) & (lag <= LAG_MIN)).astype(float).rolling(BEATEN_DAYS, min_periods=1).max() > 0
    oversold = (rsi_series(c) < 30).astype(float).rolling(OVERSOLD_DAYS, min_periods=1).max() > 0
    low60 = c.rolling(60).min()
    base = low60 >= low60.shift(BASE_DAYS)          # the 60-day low hasn't moved down in 7 days
    cross = (c > s20) & (c.shift(1) <= s20.shift(1))
    return (beaten & oversold & base & cross).fillna(False)


def turn(df: pd.DataFrame, spy: pd.Series | None) -> dict | None:
    if df is None or len(df) < 260:
        return None
    sig = signal_series(df, spy)
    if not bool(sig.iloc[-1]):
        return None
    c = df["Close"]
    close = float(c.iloc[-1])
    low = float(c.iloc[-60:].min())
    return {
        "date": c.index[-1].strftime("%Y-%m-%d"),
        "close": round(close, 2),
        "sma20": round(float(c.rolling(20).mean().iloc[-1]), 2),
        "sma50": round(float(c.rolling(50).mean().iloc[-1]), 2),
        "low60": round(low, 2),
        "from_low": round((close / low - 1) * 100, 1),
        "stop": round(close * (1 - STOP_PCT / 100), 2),
        "rsi": round(float(rsi_series(c).iloc[-1]), 1),
    }


if __name__ == "__main__":   # quick test: python turn.py ROP MCD
    import sys
    import yfinance as yf
    T = sys.argv[1:] or ["ROP", "MCD"]
    d = yf.download(T + ["SPY"], period="3y", interval="1d", group_by="ticker", auto_adjust=True, progress=False)
    spy = d["SPY"]["Close"].dropna()
    for t in T:
        df = d[t].dropna(subset=["Close"])
        s = signal_series(df, spy)
        print(t, [x.strftime("%Y-%m-%d") for x in s[s].index[-6:]], turn(df, spy))
