"""Market breadth meter (Oct 26, 2026).

% of liquid stocks (no ETFs) closing above their own 50-day average.
Liquid = price over $5 and $5M+ traded a day (50-day average), the same floor as the screener.
Lights: green >= 60%, yellow 40-60%, red < 40%. In the out-of-sample test (backtest-oos-round2.md),
pullbacks taken when breadth was over 60% did clearly better in 2026 (PF 1.10 vs 0.87).
US holidays (when only Canada traded) are skipped so the averages don't break.
Oct 27: also "large" = the same reading for companies over $10B only. When it is well above the
all-stock reading, the rally is narrow (carried by the big names).
"""
import pandas as pd

GREEN, YELLOW = 60.0, 40.0
LARGE = 10e9   # the large-company reading (Oct 27)


def light_of(pct):
    return "g" if pct >= GREEN else "y" if pct >= YELLOW else "r"


def compute(hist: dict, meta: dict, days: int = 200, min_dollar: float = 5e6, min_price: float = 5.0):
    above, liquid = {}, {}
    for t, df in hist.items():
        if (meta.get(t) or {}).get("kind") == "ETF" or df is None or len(df) < 60:
            continue
        c = df["Close"].dropna()
        v = df["Volume"].reindex(c.index)
        lq = (c > min_price) & ((c * v).rolling(50).mean() >= min_dollar)
        above[t] = (c > c.rolling(50).mean()) & lq
        liquid[t] = lq
    if not liquid:
        return None
    out = _summary(above, liquid, days, 300)
    if out is None:
        return None
    big = [t for t in liquid if ((meta.get(t) or {}).get("market_cap") or 0) >= LARGE]
    try:
        lg = _summary({t: above[t] for t in big}, {t: liquid[t] for t in big}, days, 50)
        if lg:
            out["large"] = {k: lg[k] for k in ("pct", "date", "light", "above", "n", "chg5", "chg20", "history")}
    except Exception:  # noqa: BLE001
        pass
    return out


def _summary(above: dict, liquid: dict, days: int, min_n: int):
    if not liquid:
        return None
    A, L = pd.DataFrame(above), pd.DataFrame(liquid)
    traded = L.notna().sum(axis=1)
    keep = traded > traded.max() * 0.5
    A = A[keep].fillna(False).astype(float)
    L = L[keep].fillna(False).astype(float)
    n = L.sum(axis=1)
    pct = (A.sum(axis=1) / n.where(n > min_n) * 100).dropna().tail(days)
    if pct.empty:
        return None
    d = pct.index[-1]
    last = float(pct.iloc[-1])
    ago = lambda k: round(last - float(pct.iloc[-1 - k]), 1) if len(pct) > k else None  # noqa: E731
    return {
        "pct": round(last, 1), "date": str(d.date()), "light": light_of(last),
        "above": int(A.sum(axis=1).loc[d]), "n": int(n.loc[d]),
        "chg5": ago(5), "chg20": ago(20),
        "avg10": round(float(pct.tail(10).mean()), 1),
        "history": [[str(i.date()), round(float(x), 1)] for i, x in pct.items()],
    }
