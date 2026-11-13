"""
Clean-up change 4 check (Nov 12, 2026): paper portfolio trading the daily Top 5 vs trading every Trend Cross.

Rebuilds each past day's Top 5 from price history with the signal code in allbt.py (Taylor's Nov 12 debrief script),
then runs the same paper account as journal.portfolio(): USD 100k / CAD 50k, buy at the signal-day close, 1% risk with
an 8% stop, 25% max position, sell at the stop or on a close under the 50-day.

Top 5 pool, as top5.py: Early Turn breakout that is green, Trend Cross (OBV-flat skipped), Comeback Turn, Weekly Trend.
One row per company, calmest first (20-day average high-low swing), 5 a day.
Not rebuilt (no history for them): the $10B size floor at the time, "not owned", "no earnings within 7 days".
"""
import json
import re
import sys

import numpy as np
import pandas as pd

HERE = "/Users/rosewood/Documents/Trading Bot: Live Royal B/research"
SRC = "/Users/rosewood/Documents/Stock Screener/royal-b/claude-allbt/allbt.py"

px = pd.read_pickle(f"{HERE}/px.pkl")
tick = sorted(set(px.columns.get_level_values(0)))
spy = px["SPY"]["Close"].dropna() if "SPY" in tick else None
if spy is None:
    import yfinance as yf
    spy = yf.download("SPY", start="2021-06-01", auto_adjust=True, progress=False)["Close"].squeeze()

code = open(SRC).read()
code = code[code.index("def rsi"):code.index("def trade")]
ns = {"pd": pd, "np": np, "spy": spy}
exec(code, ns)   # defines rsi() and sigs() exactly as in allbt.py
sigs = ns["sigs"]

uni = pd.read_csv(f"{HERE}/universe.csv")
names = dict(zip(uni.ticker, uni.name))

START = sys.argv[1] if len(sys.argv) > 1 else "2026-01-02"
END = sys.argv[2] if len(sys.argv) > 2 else "2099-12-31"
STOP, RISK, MAXPOS = 0.08, 0.01, 0.25
CASH0 = {"USD": 100_000.0, "CAD": 50_000.0}

data, top5_pool, tc_pool = {}, [], []
for t in tick:
    if t == "SPY":
        continue
    df = px[t].dropna()
    if len(df) < 300:
        continue
    S, s50 = sigs(df)
    c, h, l = df.Close, df.High, df.Low
    s20 = c.rolling(20).mean()
    green = (c >= s50) & (c / s20 - 1 < 0.15) & (c / s50 - 1 < 0.15)
    swing = ((h - l) / c * 100).rolling(20).mean()
    pool = (S["Early Turn breakout"] & green) | S["Trend Cross, OBV-flat skipped"] | S["Comeback Turn"] | S["Weekly Trend"]
    cur = "CAD" if t.endswith(".TO") else "USD"
    data[t] = {"cur": cur, "idx": df.index, "o": df.Open.values, "l": l.values, "c": c.values, "s50": s50.values}
    for d in df.index[pool.fillna(False).values]:
        top5_pool.append((d, t, float(swing.loc[d])))
    r3m = c / c.shift(63) - 1
    for d in df.index[S["Trend Cross"].fillna(False).values]:
        tc_pool.append((d, t, -float(r3m.loc[d]) if np.isfinite(r3m.loc[d]) else 9))


def base(t):
    return re.sub(r"\.TO$", "", t).replace("-", ".")


P = pd.DataFrame(top5_pool, columns=["date", "t", "swing"]).dropna()
P["co"] = P.t.map(base)
P = P.sort_values(["date", "swing"]).drop_duplicates(["date", "co"])
top5 = {d: list(g.t[:5]) for d, g in P.groupby("date")}
T = pd.DataFrame(tc_pool, columns=["date", "t", "k"]).sort_values(["date", "k"])
tcs = {d: list(g.t) for d, g in T.groupby("date")}


def run(picks):
    res = {}
    for cur, cash0 in CASH0.items():
        tk = [t for t, d in data.items() if d["cur"] == cur]
        cal = sorted(set().union(*[set(data[t]["idx"]) for t in tk]))
        cal = [d for d in cal if pd.Timestamp(START) <= d <= pd.Timestamp(END)]
        pos = {t: dict(zip(data[t]["idx"], range(len(data[t]["idx"])))) for t in tk}
        cash, held, last, eq, trades, skipped = cash0, {}, {}, [], [], 0
        for d in cal:
            sold = set()
            for t in list(held):
                i = pos[t].get(d)
                if i is None:
                    continue
                D, p = data[t], held[t]
                px_ = None
                if D["l"][i] <= p["stop"]:
                    px_, why = float(min(D["o"][i], p["stop"])), "stop"
                elif not np.isnan(D["s50"][i]) and D["c"][i] < D["s50"][i]:
                    px_, why = float(D["c"][i]), "50-day"
                last[t] = float(D["c"][i])
                if px_ is not None:
                    cash += p["sh"] * px_
                    trades.append((px_ / p["px"] - 1, why))
                    del held[t]
                    sold.add(t)
            equity = cash + sum(p["sh"] * last.get(t, p["px"]) for t, p in held.items())
            for t in picks.get(d, []):
                if t not in pos or t in held or t in sold or data[t]["cur"] != cur:
                    continue
                i = pos[t][d]
                px_ = float(data[t]["c"][i])
                sh = int(min(equity * RISK / STOP, equity * MAXPOS) // px_)
                if sh < 1 or sh * px_ > cash:
                    skipped += 1
                    continue
                cash -= sh * px_
                held[t] = {"sh": sh, "px": px_, "stop": px_ * (1 - STOP)}
                last[t] = px_
            eq.append(cash + sum(p["sh"] * last.get(t, p["px"]) for t, p in held.items()))
        r = [x for x, _ in trades]
        win, loss = sum(x for x in r if x > 0), -sum(x for x in r if x < 0)
        res[cur] = {"return_pct": round((eq[-1] / cash0 - 1) * 100, 1), "closed": len(r),
                    "win_pct": round(100 * np.mean([x > 0 for x in r]), 0) if r else None,
                    "pf": round(win / loss, 2) if loss else None,
                    "stops_pct": round(100 * np.mean([w == "stop" for _, w in trades]), 0) if trades else None,
                    "open": len(held), "skipped_no_cash": skipped}
    return res


bench = {}
for cur, b in (("USD", "SPY"), ("CAD", "XIU.TO")):
    try:
        s = px[b]["Close"].dropna() if b in tick else None
        if s is None:
            import yfinance as yf
            s = yf.download(b, start="2025-12-01", auto_adjust=True, progress=False)["Close"].squeeze()
        s = s[(s.index >= pd.Timestamp(START)) & (s.index <= pd.Timestamp(END))]
        bench[cur] = round((s.iloc[-1] / s.iloc[0] - 1) * 100, 1)
    except Exception as e:  # noqa: BLE001
        bench[cur] = str(e)[:60]

out = {"from": START, "to": str(max(top5).date()), "top5": run(top5), "trend_cross": run(tcs), "market": bench,
       "top5_days": sum(1 for d in top5 if d >= pd.Timestamp(START))}
print(json.dumps(out, indent=1))
json.dump(out, open(f"{HERE}/top5_paper_results_{START[:4]}.json", "w"), indent=1)
