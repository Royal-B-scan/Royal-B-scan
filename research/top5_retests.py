"""
Screener clean-up re-tests (Nov 12, 2026), with the signal and trade code from Taylor's allbt.py.

Change 2: is the Top 5 better WITH or WITHOUT Trend Cross in its pool?
Change 3: is the Top 5 better with Weekly Trend ranked first (then calmest), or calmest first for all?

Top 5 each day, as top5.py: pool = Early Turn breakout that is green, Trend Cross (OBV-flat skipped), Comeback Turn,
Weekly Trend; one row per company; 5 a day. A stock already picked in the last 20 trading days is not counted again.
Trade, as allbt.py: buy the next open, 8% stop, exit on a close under the 50-day (after closing above it), 120 days max.
Random baseline, as allbt.py: 1% of days on which any large cap was above a rising 200-day.
Periods: 2023-25 and 2026 separately. Not rebuilt: $10B floor at the time, "not owned", earnings within 7 days.
"""
import json
import re

import numpy as np
import pandas as pd

HERE = "/Users/rosewood/Documents/Trading Bot: Live Royal B/research"
SRC = "/Users/rosewood/Documents/Stock Screener/royal-b/claude-allbt/allbt.py"
px = pd.read_pickle(f"{HERE}/px.pkl")
tick = sorted(set(px.columns.get_level_values(0)))
if "SPY" in tick:
    spy = px["SPY"]["Close"].dropna()
else:
    import yfinance as yf
    spy = yf.download("SPY", start="2021-06-01", auto_adjust=True, progress=False)["Close"].squeeze()
code = open(SRC).read()
ns = {"pd": pd, "np": np, "spy": spy}
exec(code[code.index("def rsi"):code.index("rows=[]")], ns)   # rsi(), sigs(), trade() exactly as in allbt.py
sigs, trade = ns["sigs"], ns["trade"]

pool, rand, frames = [], [], {}
rng = np.random.default_rng(7)
for t in tick:
    if t == "SPY":
        continue
    df = px[t].dropna()
    if len(df) < 300:
        continue
    S, s50 = sigs(df)
    frames[t] = (df, s50)
    c, h, l = df.Close, df.High, df.Low
    s20 = c.rolling(20).mean()
    green = (c >= s50) & (c / s20 - 1 < 0.15) & (c / s50 - 1 < 0.15)
    swing = ((h - l) / c * 100).rolling(20).mean()
    src = {"early": (S["Early Turn breakout"] & green), "cross": S["Trend Cross, OBV-flat skipped"],
           "turn": S["Comeback Turn"], "weekly": S["Weekly Trend"]}
    for k, ser in src.items():
        for i in np.where(ser.fillna(False).values)[0]:
            if df.index[i] >= pd.Timestamp("2023-01-01") and np.isfinite(swing.iat[i]):
                pool.append((df.index[i], t, i, k, float(swing.iat[i])))
    lead = S["_lead"].values
    for i in np.where(lead)[0]:
        if df.index[i] >= pd.Timestamp("2023-01-01") and rng.random() < 0.01:
            rand.append((df.index[i], t, i))

P = pd.DataFrame(pool, columns=["date", "t", "i", "src", "swing"])
P["co"] = P.t.map(lambda t: re.sub(r"\.TO$", "", t).replace("-", "."))
G = P.groupby(["date", "t", "i", "co"], as_index=False).agg(swing=("swing", "min"), srcs=("src", lambda s: set(s)))


def top5(no_cross=False, weekly_first=False):
    g = G.copy()
    if no_cross:
        g["srcs"] = g.srcs.map(lambda s: s - {"cross"})
        g = g[g.srcs.map(len) > 0]
    g["wk"] = g.srcs.map(lambda s: 0 if (weekly_first and "weekly" in s) else 1)
    g = g.sort_values(["date", "wk", "swing"]).drop_duplicates(["date", "co"])
    picks, last = [], {}
    for d, day in g.groupby("date"):
        n = 0
        for r in day.itertuples():
            if n == 5:
                break
            df = frames[r.t][0]
            if r.t in last and r.i - last[r.t] < 20:
                n += 1          # still on the list; counts toward the 5 but is not a new trade
                continue
            last[r.t] = r.i
            picks.append((d, r.t, r.i))
            n += 1
    return picks


def stats(picks):
    out = {}
    for lab, lo, hi in (("2023-25", "2023-01-01", "2025-12-31"), ("2026", "2026-01-01", "2099-01-01")):
        rs = []
        for d, t, i in picks:
            if not (pd.Timestamp(lo) <= d <= pd.Timestamp(hi)):
                continue
            df, s50 = frames[t]
            r = trade(df, s50, i)
            if r:
                rs.append(r)
        done = [x for x in rs if x[2] != "open"]
        win, loss = sum(x[0] for x in done if x[0] > 0), -sum(x[0] for x in done if x[0] < 0)
        out[lab] = {"n": len(rs), "pf": round(win / loss, 2) if loss else None,
                    "win": round(100 * np.mean([x[0] > 0 for x in done])) if done else None,
                    "avg": round(100 * np.mean([x[0] for x in done]), 2) if done else None,
                    "stop": round(100 * np.mean([x[2] == "stop" for x in rs])) if rs else None}
        # how much of the profit came from the 5 biggest winners
        if done and win:
            out[lab]["top5_winners_share"] = round(100 * sum(sorted([x[0] for x in done], reverse=True)[:5]) / win)
    return out


res = {"Top 5 now (all four, calmest first)": stats(top5()),
       "Change 2: Top 5 without Trend Cross": stats(top5(no_cross=True)),
       "Change 3: Weekly Trend first, then calmest": stats(top5(weekly_first=True)),
       "Changes 2+3 together": stats(top5(no_cross=True, weekly_first=True)),
       "Random (any strong large cap)": stats(rand)}
json.dump(res, open(f"{HERE}/top5_retests_results.json", "w"), indent=1)
for k, v in res.items():
    print(f"{k:44} | " + " | ".join(f"{p}: n={x['n']} PF {x['pf']} win {x['win']}% avg {x['avg']}% stop {x['stop']}% top5win {x.get('top5_winners_share')}%" for p, x in v.items()))
