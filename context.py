"""
Market + stock context (Taylor, Nov 5, 2026). INFO ONLY: nothing here changes Buy/Almost/Skip, crowns, Today,
Watch Alerts or any screener. It adds three readings the page shows next to what's already there.

  1. CREDIT LIGHT (market)  HYG (junk bonds) / LQD (investment-grade bonds). When big money gets nervous it
     sells junk bonds first, so this ratio often turns down before stocks do.
        green   ratio above its 50-day average and higher than 20 days ago   (risk-on)
        red     ratio below its 50-day average and lower than 20 days ago    (risk-off)
        yellow  anything in between
  2. RSI-14 (each stock)    Wilder's 14-day RSI. "Stretched" at 75 or more = the stock has already run hard;
     a warning not to chase, never a block.
  3. OBV (each stock)       On-Balance Volume = volume added on up days, subtracted on down days.
        net20   (OBV today - OBV 20 days ago) / total volume of those 20 days, in %.
                +30 means 30% more of the last month's volume traded on up days than on down days.
        trend   "up" (net20 >= +10 and OBV above its 50-day avg) = buyers loading up,
                "down" (net20 <= -10 and OBV below its 50-day avg) = sellers, else "flat"

Backtest (Nov 5, backtest-context.md in the project; Trend Cross + Early Turn signals, dev 2023-25 / 2026):
  credit light  NOT a filter: signals on red days did as well or better in 2023-25; SPY's next 20 days were the
                same on red and green days in 2023-25, weaker after red days in 2026 (only 30 days). Mood reading.
  RSI 75+       no clear harm (Trend Cross PF 1.71 / 0.91 vs all 1.51 / 0.97). Shown as a caution only.
  OBV           "up" beat "flat" on all three signals in both periods (e.g. Breakout 1.40 / 1.24 vs 1.25 / 0.92);
                the most useful of the three. "OBV lead" tested worse and was dropped.

    credit(hist, fetch=None) -> dict | None
    stock(df) -> {"rsi": .., "stretched": .., "obv_net20": .., "obv_trend": ..}
    attach(entries, hist)    adds those keys to each entry (scan rows, Early Turn rows, Weekly rows)
"""
from __future__ import annotations

import pandas as pd

RSI_STRETCHED = 75
OBV_BAND = 10.0          # net20 in % for "up" / "down"
HISTORY_DAYS = 200


# ---------------------------------------------------------------- 1. credit light
def credit_series(hyg: pd.Series, lqd: pd.Series) -> pd.DataFrame:
    r = (hyg / lqd.reindex(hyg.index).ffill()).dropna()
    s50 = r.rolling(50).mean()
    chg20 = r / r.shift(20) - 1
    light = pd.Series("y", index=r.index)
    light[(r > s50) & (chg20 > 0)] = "g"
    light[(r < s50) & (chg20 < 0)] = "r"
    light[s50.isna() | chg20.isna()] = None
    return pd.DataFrame({"ratio": r, "sma50": s50, "chg20": chg20, "light": light})


def credit(hist: dict, fetch=None) -> dict | None:
    """fetch(ticker) -> close series, used when HYG/LQD aren't already in the scan's history."""
    def close(t):
        df = hist.get(t)
        if df is not None:
            return df["Close"]
        return fetch(t) if fetch else None

    hyg, lqd = close("HYG"), close("LQD")
    if hyg is None or lqd is None:
        return None
    cs = credit_series(hyg.dropna(), lqd.dropna()).dropna()
    if cs.empty:
        return None
    last = cs.iloc[-1]
    lights = cs["light"]
    since = lights.index[-1]
    for d, v in lights.iloc[::-1].items():           # first day of the current color
        if v != last["light"]:
            break
        since = d
    pct_vs_50 = (cs["ratio"] / cs["sma50"] - 1) * 100
    tail = cs.tail(HISTORY_DAYS)
    return {
        "light": last["light"], "date": str(cs.index[-1].date()), "since": str(since.date()),
        "ratio": round(float(last["ratio"]), 4),
        "vs50": round(float(pct_vs_50.iloc[-1]), 2),           # % above (+) / below (-) its 50-day
        "chg5": round(float((cs["ratio"].iloc[-1] / cs["ratio"].iloc[-6] - 1) * 100), 2),
        "chg20": round(float(last["chg20"] * 100), 2),
        "history": [[str(d.date()), round(float(r), 4), round(float(s), 4), l]
                    for d, r, s, l in zip(tail.index, tail["ratio"], tail["sma50"], tail["light"])],
    }


# ---------------------------------------------------------------- 2 + 3. per stock
def rsi_series(c: pd.Series, n: int = 14) -> pd.Series:
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    return 100 - 100 / (1 + up / dn.where(dn > 0))


def obv_frame(df: pd.DataFrame) -> pd.DataFrame:
    c, v = df["Close"], df["Volume"].fillna(0)
    sign = c.diff().apply(lambda x: 1 if x > 0 else -1 if x < 0 else 0)
    obv = (sign * v).cumsum()
    net20 = (obv - obv.shift(20)) / v.rolling(20).sum().where(lambda s: s > 0) * 100
    above = obv > obv.rolling(50).mean()
    trend = pd.Series("flat", index=df.index)
    trend[(net20 >= OBV_BAND) & above] = "up"
    trend[(net20 <= -OBV_BAND) & ~above] = "down"
    return pd.DataFrame({"obv": obv, "net20": net20, "trend": trend})


def stock(df: pd.DataFrame) -> dict:
    if df is None or len(df) < 60:
        return {}
    r = rsi_series(df["Close"]).iloc[-1]
    o = obv_frame(df).iloc[-1]
    out = {"obv_trend": o["trend"]}
    if pd.notna(r):
        out.update(rsi=round(float(r), 1), stretched=bool(r >= RSI_STRETCHED))
    if pd.notna(o["net20"]):
        out["obv_net20"] = round(float(o["net20"]), 1)
    return out


def attach(entries: list, hist: dict) -> int:
    n = 0
    for e in entries or []:
        try:
            info = stock(hist.get(e.get("ticker")))
        except Exception:  # noqa: BLE001
            continue
        if info:
            e["ctx"] = info
            n += 1
    return n
