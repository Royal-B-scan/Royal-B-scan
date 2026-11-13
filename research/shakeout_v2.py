"""Shakeout Bounce v2 test (Phase 1a, Nov 12, 2026). Needs px.pkl (python get_prices.py).

v1 judged "leader" on the bounce day, so it missed MU, TSM and AVGO: the drop had already cut them under the 200-day.
v2 judges "leader" BEFORE the drop: 20 trading days earlier the close was above a rising 200-day, and a 52-week
closing high was made within the last 90 days. Everything else is v1: shakeout (10-day low 12%+ under the prior
20-day high), turn day (up 3%+, above the prior high, top 30% of the range, 1.2x volume, low within 5 days), one
signal per stock per 10 days, buy the next open, exits: 8% stop / close under the shakeout low / 50-day / 60 days.

Each version is compared with its OWN random baseline: random days on stocks that pass the same leader test, same
exits. 2023-25 and 2026 are reported separately. Variants: 2-day confirmation; shakeout-low stop only.

    python shakeout_v2.py
"""
import numpy as np
import pandas as pd

px = pd.read_pickle("px.pkl")
TICKERS = [t for t in sorted(set(px.columns.get_level_values(0))) if t not in ("SPY", "XIU.TO")]


def trade(O, L, C, s50, i, low, use_stop=True):
    """Buy the open after day i. Returns (return, days held, why)."""
    if i + 1 >= len(C):
        return None
    e = O[i + 1]
    stop = e * 0.92
    above = False
    for j in range(i + 1, min(i + 61, len(C))):
        if use_stop:
            if O[j] <= stop and j > i + 1:
                return (O[j] / e - 1, j - i, "stop")
            if L[j] <= stop:
                return (stop / e - 1, j - i, "stop")
        if C[j] < low:
            return (C[j] / e - 1, j - i, "low")
        if C[j] > s50[j]:
            above = True
        elif above:
            return (C[j] / e - 1, j - i, "50d")
    j = min(i + 60, len(C) - 1)
    return (C[j] / e - 1, j - i, "time" if j == i + 60 else "open")


def run(version: str, confirm: bool = False, use_stop: bool = True, seed: int = 1,
        hi_days: int = 90, top: float = 0.7, prev_high: bool = True):
    """hi_days: how recent the 52-week high must be (v2). top: the close must be in this top share of the day's
    range (0.7 = top 30%; 0 = no test). prev_high: the close must be above the day before's high."""
    rng = np.random.default_rng(seed)
    rows, base = [], []
    for t in TICKERS:
        df = px[t].dropna()
        if len(df) < 300:
            continue
        O, H, L, C, V = (df[k].values for k in ("Open", "High", "Low", "Close", "Volume"))
        c = pd.Series(C)
        s200, s50 = c.rolling(200).mean().values, c.rolling(50).mean().values
        hi252 = c.rolling(252).max().values
        v50 = pd.Series(V).rolling(50).mean().shift(1).values
        last, dates = -99, df.index
        for i in range(280, len(C)):
            if version == "v1":
                lead = C[i] > s200[i] and s200[i] > s200[i - 20] and C[i - 60:i + 1].max() >= hi252[i] * 0.999
            else:
                lead = (C[i - 20] > s200[i - 20] and s200[i - 20] > s200[i - 40]
                        and C[i - hi_days:i + 1].max() >= hi252[i] * 0.999)
            if not lead:
                continue
            if rng.random() < 0.02:
                r = trade(O, L, C, s50, i, C[i] * 0.85, use_stop)
                if r:
                    base.append((dates[i], t) + r)
            k = i - 1 if confirm else i                      # k = the turn day; with confirm, day i is a 2nd up day
            lo, pk = C[k - 10:k].min(), C[k - 30:k - 10].max()
            if not lo <= pk * 0.88:
                continue
            if k - np.argmin(C[k - 10:k]) - (k - 10) > 5:
                continue
            rg = H[k] - L[k]
            if not (C[k] >= C[k - 1] * 1.03 and (C[k] > H[k - 1] or not prev_high) and rg > 0
                    and (C[k] - L[k]) / rg >= top and V[k] >= 1.2 * v50[k]):
                continue
            if confirm and not C[i] > C[k]:
                continue
            if i - last < 10:
                continue
            last = i
            r = trade(O, L, C, s50, i, lo, use_stop)
            if r:
                rows.append((dates[i], t) + r)
    cols = ["date", "t", "ret", "held", "why"]
    return pd.DataFrame(rows, columns=cols), pd.DataFrame(base, columns=cols)


def line(D, lab, m):
    x = D[m & (D.why != "open")].ret
    if not len(x):
        return f"{lab}: no closed trades"
    pf = x[x > 0].sum() / -x[x < 0].sum()
    top = x.sort_values(ascending=False)
    x10 = top.iloc[10:] if len(top) > 20 else top
    pf10 = x10[x10 > 0].sum() / -x10[x10 < 0].sum()
    return (f"{lab}: n={len(x):4}  win {100 * (x > 0).mean():3.0f}%  avg {100 * x.mean():+5.2f}%  PF {pf:4.2f}  "
            f"(PF without the 10 best {pf10:4.2f})  stopped {100 * (D[m].why == 'stop').mean():3.0f}%  held {D[m].held.mean():3.0f}d")


def report(name, S, B):
    print(f"\n== {name}")
    for lab, f in (("2023-25", lambda D: (D.date >= "2023-01-01") & (D.date < "2026-01-01")), ("2026   ", lambda D: D.date >= "2026-01-01")):
        print("  signal   " + line(S, lab, f(S)))
        print("  baseline " + line(B, lab, f(B)))


if __name__ == "__main__":
    S1, B1 = run("v1")
    report("v1 (leader judged on the bounce day)", S1, B1)
    S2, B2 = run("v2")
    report("v2 (leader judged before the drop)", S2, B2)
    new = S2.merge(S1[["date", "t"]], on=["date", "t"], how="left", indicator=True)
    new = new[new._merge == "left_only"].drop(columns="_merge")
    report("only the signals v2 adds over v1", new, B2)
    S3, B3 = run("v2", confirm=True)
    report("v2 + wait for a second up day", S3, B3)
    S4, B4 = run("v2", use_stop=False)
    report("v2 with the shakeout-low stop only (no 8% stop)", S4, B4)
    # several baseline seeds, so the comparison doesn't rest on one random draw
    pfs = {"2023-25": [], "2026": []}
    for seed in range(2, 8):
        _, B = run("v2", seed=seed)
        for lab, m in (("2023-25", (B.date >= "2023-01-01") & (B.date < "2026-01-01")), ("2026", B.date >= "2026-01-01")):
            x = B[m & (B.why != "open")].ret
            pfs[lab].append(x[x > 0].sum() / -x[x < 0].sum())
    print("\nv2 baseline PF over 6 other random draws: " + "; ".join(f"{k} {min(v):.2f} to {max(v):.2f}" for k, v in pfs.items()))
    print("\nChip names, Nov 2026 (the miss that started this):")
    for t in ("MU", "TSM", "AVGO", "AMD", "GOOGL", "NVDA", "ANET"):
        a, b = S1[(S1.t == t) & (S1.date >= "2026-11-01")], S2[(S2.t == t) & (S2.date >= "2026-11-01")]
        print(f"  {t:5} v1: {', '.join(d.strftime('%b %d') for d in a.date) or 'no signal':10}  v2: {', '.join(d.strftime('%b %d') for d in b.date) or 'no signal'}")
    S2.to_csv("shakeout_v2_trades.csv", index=False)
