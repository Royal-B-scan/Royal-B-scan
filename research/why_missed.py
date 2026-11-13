"""Why Shakeout Bounce (v1 and v2) did not fire on the chip names in Nov 2026: every condition, day by day.
Needs px.pkl.    python why_missed.py [TICKER ...]"""
import sys

import numpy as np
import pandas as pd

px = pd.read_pickle("px.pkl")
NAMES = sys.argv[1:] or ["MU", "TSM", "AVGO", "GOOGL", "NVDA", "AMD", "ANET"]
START = "2026-10-26"

for t in NAMES:
    df = px[t].dropna()
    O, H, L, C, V = (df[k].values for k in ("Open", "High", "Low", "Close", "Volume"))
    c = pd.Series(C)
    s200, s50, s20 = (c.rolling(n).mean().values for n in (200, 50, 20))
    hi252 = c.rolling(252).max().values
    v50 = pd.Series(V).rolling(50).mean().shift(1).values
    n = len(C)
    first = int(np.searchsorted(df.index, pd.Timestamp(START)))
    peak_i = first - 40 + int(np.argmax(C[first - 40:]))
    low_i = peak_i + int(np.argmin(C[peak_i:]))
    print(f"\n=== {t}: peak close {C[peak_i]:.2f} on {df.index[peak_i]:%b %d}, low close {C[low_i]:.2f} on {df.index[low_i]:%b %d} "
          f"({(C[low_i] / C[peak_i] - 1) * 100:+.1f}%), last {C[-1]:.2f} ({(C[-1] / C[low_i] - 1) * 100:+.1f}% off the low)")
    print(f"    52-week closing high {hi252[-1]:.2f}, last made {n - 1 - int(np.argmax(C[-252:]) + n - 252)} trading days ago; "
          f"close vs 200-day {(C[-1] / s200[-1] - 1) * 100:+.1f}%, vs 50-day {(C[-1] / s50[-1] - 1) * 100:+.1f}%")
    print("    date     close   chg%  | leadV1 leadV2 | drop%  need12 lowAge<=5 | up3% >prevHi top30% vol1.2x | fails")
    for i in range(first, n):
        lead1 = C[i] > s200[i] and s200[i] > s200[i - 20] and C[i - 60:i + 1].max() >= hi252[i] * 0.999
        lead2 = C[i - 20] > s200[i - 20] and s200[i - 20] > s200[i - 40] and C[i - 90:i + 1].max() >= hi252[i] * 0.999
        lo, pk = C[i - 10:i].min(), C[i - 30:i - 10].max()
        drop = (1 - lo / pk) * 100
        age = i - (i - 10 + int(np.argmin(C[i - 10:i])))
        rg = H[i] - L[i]
        up3, hi, top, vol = C[i] >= C[i - 1] * 1.03, C[i] > H[i - 1], rg > 0 and (C[i] - L[i]) / rg >= 0.7, V[i] >= 1.2 * v50[i]
        checks = {"leader(v2)": lead2, "drop<12%": drop >= 12, "low too old": age <= 5, "up<3%": up3, "not>prevHigh": hi,
                  "close not top30%": top, "vol<1.2x": vol}
        fails = [k for k, ok in checks.items() if not ok]
        y = lambda b: " yes " if b else "  -  "  # noqa: E731
        print(f"    {df.index[i]:%b %d}  {C[i]:8.2f} {(C[i] / C[i - 1] - 1) * 100:+5.1f}  | {y(lead1)}  {y(lead2)}  | {drop:5.1f}  {y(drop >= 12)}   {age:2d} {y(age <= 5)} |"
              f" {y(up3)} {y(hi)}  {y(top)}  {V[i] / v50[i]:4.1f}x{y(vol)} | {'FIRES' if not fails else ', '.join(fails)}")
