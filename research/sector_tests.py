"""Phase 1b and 1c (Nov 12, 2026). Needs px.pkl and universe.csv (python get_prices.py).

Groups: a stock's GICS sub-industry when that has 8+ members in the universe, else its sector; TSX stocks by their
TSX sector ("CA ..."); the 10 foreign stocks placed by hand. A group's index = the average daily move of its members.

1b  SECTOR REBOUND. A group that was leading (index above a rising 200-day, 20 days earlier) sells off 8%+
    (10-day low vs the high of the 20 days before), then turns: the index closes 3%+ above that low within 5 days
    of it. One event per group per 20 days. Test: buy the group's 5 leaders (best 6-month return measured 20 days
    earlier) at the next open, against buying EVERY member that day (= the average random pick). Same exits as
    Shakeout Bounce: 8% stop, 50-day exit once above it, 60 days; no shakeout-low exit here.

1c  WITH THE GROUP OR ALONE. Shakeout Bounce signals (52-week high within 120 days, close in the top half of the
    range: the version Taylor picked Nov 12) split by what the stock's group was doing that day.

2023-25 and 2026 are reported separately. PF = dollars won per dollar lost. "-N best" = without the N best trades.

    python sector_tests.py
"""
import numpy as np
import pandas as pd

from shakeout_v2 import trade

px = pd.read_pickle("px.pkl")
uni = pd.read_csv("universe.csv", keep_default_na=False)
FOREIGN = {"TSM": "Semiconductors", "ASML": "Semiconductor Materials & Equipment", "ARM": "Semiconductors",
           "SHOP": "Application Software", "SAP": "Application Software", "NVO": "Pharmaceuticals",
           "BABA": "Broadline Retail", "PDD": "Broadline Retail", "MELI": "Broadline Retail", "SE": "Broadline Retail"}
HI_DAYS, TOP = 120, 0.5


def groups() -> dict:
    sub = uni[uni.group == "SP500"].groupby("industry").size()
    big = set(sub[sub >= 8].index)
    out = {}
    for r in uni.itertuples():
        if r.group == "SP500":
            out[r.ticker] = r.industry if r.industry in big else r.sector
        elif r.group == "TSX60":
            out[r.ticker] = "CA " + (r.sector or "Other")
        else:
            g = FOREIGN.get(r.ticker, "")
            out[r.ticker] = g if g in big else {"Semiconductors": "Information Technology", "Semiconductor Materials & Equipment": "Information Technology",
                                                "Application Software": "Information Technology", "Pharmaceuticals": "Health Care",
                                                "Broadline Retail": "Consumer Discretionary"}.get(g, "Other")
    return out


GROUP = groups()
HAVE = set(px.columns.get_level_values(0))
D = {}
for t in sorted(GROUP):
    if t not in HAVE:
        continue
    df = px[t].dropna()
    if len(df) < 300:
        continue
    c = df["Close"]
    D[t] = {"df": df, "O": df["Open"].values, "H": df["High"].values, "L": df["Low"].values, "C": c.values, "V": df["Volume"].values,
            "s50": c.rolling(50).mean().values, "s200": c.rolling(200).mean().values, "hi252": c.rolling(252).max().values,
            "v50": df["Volume"].rolling(50).mean().shift(1).values, "pos": {d: i for i, d in enumerate(df.index)}}
MEMBERS = {}
for t in D:
    MEMBERS.setdefault(GROUP[t], []).append(t)
MEMBERS = {g: m for g, m in MEMBERS.items() if len(m) >= 5}

# group index: average member move, on days when at least half the members traded
IDX = {}
for g, mem in MEMBERS.items():
    rets = pd.concat([D[t]["df"]["Close"].pct_change().rename(t) for t in mem], axis=1)
    ok = rets.notna().sum(axis=1) >= max(3, len(mem) / 2)
    r = rets[ok].mean(axis=1)
    lvl = (1 + r.fillna(0)).cumprod()
    IDX[g] = pd.DataFrame({"lvl": lvl, "ret": r, "s200": lvl.rolling(200).mean(), "up_share": (rets[ok] >= 0.02).mean(axis=1)})


def group_state(g: str) -> pd.DataFrame:
    """Per day: drop% (10-day low vs the 20-day high before it), days since that low, % above that low, was-leader."""
    x = IDX[g]
    lvl = x["lvl"]
    lo = lvl.shift(1).rolling(10).min()
    pk = lvl.shift(11).rolling(20).max()
    age = lvl.shift(1).rolling(10).apply(lambda w: len(w) - int(np.argmin(w)), raw=True)
    lead = (lvl.shift(20) > x["s200"].shift(20)) & (x["s200"].shift(20) > x["s200"].shift(40))
    return pd.DataFrame({"drop": (1 - lo / pk) * 100, "age": age, "off_low": (lvl / lo - 1) * 100, "lead": lead,
                         "ret": x["ret"] * 100, "up_share": x["up_share"]})


STATE = {g: group_state(g) for g in MEMBERS}


def stats(rets, cut):
    x = pd.Series(rets, dtype=float).sort_values(ascending=False)
    if not len(x):
        return "n=   0"
    pf = x[x > 0].sum() / -x[x < 0].sum() if (x < 0).any() else float("inf")
    y = x.iloc[cut:] if len(x) > 3 * cut else x
    pfc = y[y > 0].sum() / -y[y < 0].sum() if (y < 0).any() else float("inf")
    return f"n={len(x):4}  win {100 * (x > 0).mean():3.0f}%  avg {100 * x.mean():+5.2f}%  PF {pf:4.2f}  (-{cut} best {pfc:4.2f})"


def periods(T):
    return (("2023-25", T[(T.date >= "2023-01-01") & (T.date < "2026-01-01")]), ("2026   ", T[T.date >= "2026-01-01"]))


# ---------------------------------------------------------------- 1b
def sector_rebound(drop_min=8.0, bounce=3.0, top_n=5, need_lead=True):
    ev, picks, allm = [], [], []
    for g, st in STATE.items():
        last = None
        for d, r in st.iterrows():
            if not (r["drop"] >= drop_min and r["age"] <= 5 and r["off_low"] >= bounce and (r["lead"] or not need_lead)):
                continue
            if last is not None and (d - last).days < 28:
                continue
            last = d
            cand = []
            for t in MEMBERS[g]:
                i = D[t]["pos"].get(d)
                if i is None or i < 260:
                    continue
                C = D[t]["C"]
                cand.append((C[i - 20] / C[i - 146] - 1, t, i))
            if len(cand) < top_n + 1:
                continue
            cand.sort(reverse=True)
            ev.append((d, g, round(r["drop"], 1), len(cand)))
            for rank, (rs, t, i) in enumerate(cand):
                x = D[t]
                tr = trade(x["O"], x["L"], x["C"], x["s50"], i, 0.0)
                if tr and tr[2] != "open":
                    allm.append((d, g, t, tr[0]))
                    if rank < top_n:
                        picks.append((d, g, t, tr[0]))
    cols = ["date", "group", "t", "ret"]
    return pd.DataFrame(ev, columns=["date", "group", "drop", "members"]), pd.DataFrame(picks, columns=cols), pd.DataFrame(allm, columns=cols)


# ---------------------------------------------------------------- 1c
def shakeout_signals():
    rows = []
    for t, x in D.items():
        O, H, L, C, V, s50, s200, hi252, v50 = (x[k] for k in ("O", "H", "L", "C", "V", "s50", "s200", "hi252", "v50"))
        dates, last = x["df"].index, -99
        g = GROUP[t]
        for i in range(280, len(C)):
            if not (C[i - 20] > s200[i - 20] and s200[i - 20] > s200[i - 40] and C[i - HI_DAYS:i + 1].max() >= hi252[i] * 0.999):
                continue
            lo, pk = C[i - 10:i].min(), C[i - 30:i - 10].max()
            if not lo <= pk * 0.88 or i - np.argmin(C[i - 10:i]) - (i - 10) > 5:
                continue
            rg = H[i] - L[i]
            if not (C[i] >= C[i - 1] * 1.03 and C[i] > H[i - 1] and rg > 0 and (C[i] - L[i]) / rg >= TOP and V[i] >= 1.2 * v50[i]):
                continue
            if i - last < 10:
                continue
            last = i
            tr = trade(O, L, C, s50, i, lo)
            if not tr or tr[2] == "open":
                continue
            st = STATE[g].loc[dates[i]] if g in STATE and dates[i] in STATE[g].index else None
            rows.append((dates[i], t, g, tr[0], tr[2], np.nan if st is None else st["drop"], np.nan if st is None else st["ret"],
                         np.nan if st is None else st["up_share"], np.nan if st is None else st["off_low"]))
    return pd.DataFrame(rows, columns=["date", "t", "group", "ret", "why", "g_drop", "g_ret", "g_up_share", "g_off_low"])


if __name__ == "__main__":
    print(f"{len(D)} stocks in {len(MEMBERS)} groups (5+ members): " + ", ".join(f"{g} {len(m)}" for g, m in sorted(MEMBERS.items(), key=lambda kv: -len(kv[1]))[:12]) + " ...")

    print("\n================ 1b SECTOR REBOUND: the group's 5 leaders vs every member")
    for label, kw in (("group fell 8%+, was leading", {}), ("group fell 8%+, any group", {"need_lead": False}),
                      ("group fell 6%+, was leading", {"drop_min": 6.0}), ("group fell 10%+, was leading", {"drop_min": 10.0}),
                      ("8%+, leading, top 3 only", {"top_n": 3})):
        ev, pk, al = sector_rebound(**kw)
        print(f"\n-- {label}: {len(ev)} group events")
        for (lab, a), (_, b) in zip(periods(pk), periods(al)):
            n_ev = a[["date", "group"]].drop_duplicates().shape[0]
            print(f"  {lab} ({n_ev:3} events)  leaders  {stats(a.ret, 5)}")
            print(f"  {lab}               everyone {stats(b.ret, 5 * max(1, round(len(b) / max(len(a), 1))))}")
    ev, pk, al = sector_rebound()
    print("\n  recent events (8%+, leading):")
    for r in ev[ev.date >= "2026-06-01"].itertuples():
        mine = pk[(pk.date == r.date) & (pk.group == r.group)]
        print(f"   {r.date:%Y-%m-%d}  {r.group:38} fell {r.drop:4.1f}%  leaders: {', '.join(mine.t)}  avg {100 * mine.ret.mean():+.1f}%")
    ev.to_csv("sector_rebound_events.csv", index=False)

    print("\n================ 1c SHAKEOUT BOUNCE: with its group, or alone")
    S = shakeout_signals()
    S.to_csv("shakeout_with_group.csv", index=False)
    splits = (("all signals", S.index == S.index),
              ("group also fell 8%+ (group sell-off)", S.g_drop >= 8), ("group fell under 8% (stock on its own)", S.g_drop < 8),
              ("group fell 5%+", S.g_drop >= 5), ("group fell under 5%", S.g_drop < 5),
              ("group up 1%+ that day", S.g_ret >= 1), ("group up under 1% that day", S.g_ret < 1),
              ("a third+ of the group up 2%+ that day", S.g_up_share >= 1 / 3), ("under a third up 2%+", S.g_up_share < 1 / 3))
    for lab, m in splits:
        print(f"\n-- {lab}")
        for p, T in periods(S[m]):
            print(f"  {p}  {stats(T.ret, 10 if len(T) > 60 else 3)}   stopped {100 * (T.why == 'stop').mean() if len(T) else 0:3.0f}%")
    print("\n  Nov 2026 chip signals and their group:")
    for r in S[(S.date >= "2026-11-01") & S.t.isin(["MU", "TSM", "AMD", "AVGO", "ANET", "NVDA"])].itertuples():
        print(f"   {r.date:%b %d} {r.t:5} group {r.group}: fell {r.g_drop:.1f}%, {r.g_ret:+.1f}% that day, {100 * r.g_up_share:.0f}% of members up 2%+")
