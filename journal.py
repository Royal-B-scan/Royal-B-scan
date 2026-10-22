"""
Signal journal: every TRIGGER and HEADS-UP the rules produced over the last ~3 months,
and how each one did afterwards. Rebuilt on every full scan from price history, so it
always reflects the current rules (no separate state to keep).

For each signal (day t, signal-day close = reference price):
  r5 / r10 / r20   % change in the close 5 / 10 / 20 trading days later (None until that day arrives)
  max20            best close within the next 20 days
  stopped          the low touched 8% below the reference within 20 days
HEADS-UP is recorded on its first day only (not again for the same stock within 10 days).

Trade result (Taylor, Oct 22): each signal is followed as a trade bought at the signal-day close and
exited by the rules, recording the price at that moment:
  stop     the day's low reaches 8% below the buy price -> sold at the stop price
           (or at that day's open if the stock gapped below the stop)
  50-day   a close below the 50-day average -> sold at that close
  open     still held -> marked at the latest close
  exit_date / exit_px / exit_why / ret (% gain or loss) / held (trading days)
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
        c, lo, op = df["Close"].values, df["Low"].values, df["Open"].values
        s50v = df["Close"].rolling(50).mean().values
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
            stop_px, j_exit, px, why = ref * (1 - STOP), n - 1, float(c[n - 1]), "open"
            for j in range(i + 1, n):
                if lo[j] <= stop_px:
                    px, why, j_exit = float(min(op[j], stop_px)), "stop", j
                    break
                if not np.isnan(s50v[j]) and c[j] < s50v[j]:
                    px, why, j_exit = float(c[j]), "50-day", j
                    break
            ev.update(exit_date=idx[j_exit].strftime("%Y-%m-%d"), exit_px=round(px, 2), exit_why=why,
                      ret=round((px / ref - 1) * 100, 2), held=int(j_exit - i))
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
        closed = [e for e in evs if e.get("exit_why") in ("stop", "50-day")]
        still = [e for e in evs if e.get("exit_why") == "open"]
        out["trades"] = {
            "closed": len(closed), "wins": sum(e["ret"] > 0 for e in closed),
            "stops": sum(e["exit_why"] == "stop" for e in closed),
            "ret_sum": round(float(sum(e["ret"] for e in closed)), 2),
            "ret_avg": round(float(np.mean([e["ret"] for e in closed])), 2) if closed else None,
            "open": len(still), "open_ret_sum": round(float(sum(e["ret"] for e in still)), 2),
            "held_avg": round(float(np.mean([e["held"] for e in closed])), 1) if closed else None,
        }
        return out

    summary = {s: stats([e for e in events if e["status"] == s]) for s in ("TRIGGER", "HEADS-UP")}
    dates = [e["date"] for e in events]
    res = {"from": min(dates) if dates else None, "to": max(dates) if dates else None,
           "summary": summary, "events": events[:1500]}
    try:
        res["portfolio"] = portfolio(hist, meta)
    except Exception as e:  # noqa: BLE001  (never break the screen over the paper portfolio)
        res["portfolio_error"] = str(e)
    return res


# ---------------------------------------------------------------- paper portfolio (Taylor, Oct 22)
"""
Screener Trials as a real account. Replays the last ~10 months, then carries on every day:
  cash      USD 100,000 for US stocks, CAD 50,000 for Canadian stocks (never converted)
  buys      every Crossed (TRIGGER) stock, no ETFs, at the signal-day close. Several on one day:
            strongest 3-month gain first (same day + same currency, so it ranks like relative strength).
  size      1% of the account's value at risk with an 8% stop -> value = equity x 1% / 8%,
            capped at 25% of equity, whole shares. Not enough cash -> skipped (counted).
  sells     day's low reaches the stop -> sold at the stop (or the open if it gapped below);
            close below the 50-day -> sold at that close. Cash goes back in for the next buys.
No commissions or currency conversion. Settings below; change them here.
"""
START_CASH = {"USD": 100_000.0, "CAD": 50_000.0}
RISK, MAXPOS, START_BARS = 0.01, 0.25, 210


def _cur(t, m):
    return m.get("currency") or ("CAD" if t.endswith((".TO", ".V")) else "USD")


def portfolio(hist: dict[str, pd.DataFrame], meta: dict) -> dict:
    data = {}
    for t, df in hist.items():
        m = meta.get(t, {})
        if m.get("kind") == "ETF" or len(df) < 80:
            continue
        trig, _ = _signals(df)
        c = df["Close"]
        data[t] = {"cur": _cur(t, m), "name": m.get("name") or t, "idx": df.index,
                   "o": df["Open"].values, "l": df["Low"].values, "c": c.values,
                   "s50": c.rolling(50).mean().values, "trig": trig.values,
                   "r3m": (c / c.shift(63) - 1).values}
    out = {"settings": {"start": START_CASH, "risk_pct": RISK * 100, "stop_pct": STOP * 100, "maxpos_pct": MAXPOS * 100,
                        "buy": "signal-day close", "signal": "Crossed (TRIGGER), stocks only"},
           "accounts": {}, "activity": []}
    for cur, cash0 in START_CASH.items():
        tk = [t for t, d in data.items() if d["cur"] == cur]
        if not tk:
            continue
        cal = sorted(set().union(*[set(data[t]["idx"]) for t in tk]))[-START_BARS:]
        pos_of = {t: dict(zip(data[t]["idx"], range(len(data[t]["idx"])))) for t in tk}
        cash, held, last_px, hist_eq, skipped, acts = cash0, {}, {}, [], 0, []
        for d in cal:
            # 1) sells
            sold = set()
            for t in list(held):
                i = pos_of[t].get(d)
                if i is None:
                    continue
                D, p = data[t], held[t]
                px = why = None
                if D["l"][i] <= p["stop"]:
                    px, why = float(min(D["o"][i], p["stop"])), "stop"
                elif not np.isnan(D["s50"][i]) and D["c"][i] < D["s50"][i]:
                    px, why = float(D["c"][i]), "50-day"
                last_px[t] = float(D["c"][i])
                if px is not None:
                    amt = p["shares"] * px
                    cash += amt
                    acts.append({"date": d.strftime("%Y-%m-%d"), "type": "SELL", "ticker": t, "name": D["name"], "cur": cur,
                                 "shares": p["shares"], "px": round(px, 2), "amount": round(amt, 2), "why": why,
                                 "buy_px": round(p["px"], 2), "buy_date": p["date"],
                                 "pl": round(amt - p["shares"] * p["px"], 2), "pl_pct": round((px / p["px"] - 1) * 100, 2),
                                 "held": int(i - pos_of[t][pd.Timestamp(p["date"])])})
                    del held[t]
                    sold.add(t)
            # 2) buys, strongest first
            equity = cash + sum(p["shares"] * last_px.get(t, p["px"]) for t, p in held.items())
            cands = []
            for t in tk:
                i = pos_of[t].get(d)
                if i is None or i < 60 or t in held or not data[t]["trig"][i]:
                    continue
                if t in sold:
                    continue
                r = data[t]["r3m"][i]
                cands.append((-(r if np.isfinite(r) else -9), t, i))
            for _, t, i in sorted(cands):
                px = float(data[t]["c"][i])
                value = min(equity * RISK / STOP, equity * MAXPOS)
                sh = int(value // px)
                if sh < 1 or sh * px > cash:
                    skipped += 1
                    continue
                cash -= sh * px
                held[t] = {"shares": sh, "px": px, "stop": px * (1 - STOP), "date": d.strftime("%Y-%m-%d")}
                last_px[t] = px
                acts.append({"date": d.strftime("%Y-%m-%d"), "type": "BUY", "ticker": t, "name": data[t]["name"], "cur": cur,
                             "shares": sh, "px": round(px, 2), "amount": round(sh * px, 2),
                             "stop": round(px * (1 - STOP), 2)})
            hist_eq.append([d.strftime("%Y-%m-%d"), round(cash + sum(p["shares"] * last_px.get(t, p["px"]) for t, p in held.items()), 2)])
        # holdings, marked at the latest close
        H = []
        for t, p in held.items():
            D = data[t]
            c_now = last_px.get(t, p["px"])
            i = pos_of[t].get(pd.Timestamp(D["idx"][-1]))
            prev = float(D["c"][i - 1]) if i else c_now
            H.append({"ticker": t, "name": D["name"], "shares": p["shares"], "buy_date": p["date"], "buy_px": round(p["px"], 2),
                      "stop": round(p["stop"], 2), "close": round(c_now, 2), "value": round(p["shares"] * c_now, 2),
                      "gain": round(p["shares"] * (c_now - p["px"]), 2), "gain_pct": round((c_now / p["px"] - 1) * 100, 2),
                      "day": round(p["shares"] * (c_now - prev), 2), "day_pct": round((c_now / prev - 1) * 100, 2) if prev else 0})
        H.sort(key=lambda h: -h["value"])
        eq = [e for _, e in hist_eq]
        chg = lambda k: (round(eq[-1] - eq[-1 - k], 2), round((eq[-1] / eq[-1 - k] - 1) * 100, 2)) if len(eq) > k else (None, None)  # noqa: E731
        sells = [a for a in acts if a["type"] == "SELL"]
        out["accounts"][cur] = {
            "start_cash": cash0, "start_date": cal[0].strftime("%Y-%m-%d"), "as_of": cal[-1].strftime("%Y-%m-%d"),
            "cash": round(cash, 2), "invested": round(sum(h["value"] for h in H), 2), "equity": round(eq[-1], 2),
            "perf": {"day": chg(1), "week": chg(5), "month": chg(21), "start": (round(eq[-1] - cash0, 2), round((eq[-1] / cash0 - 1) * 100, 2))},
            "holdings": H, "history": hist_eq,
            "stats": {"buys": len(acts) - len(sells), "sells": len(sells), "wins": sum(a["pl"] > 0 for a in sells),
                      "stops": sum(a["why"] == "stop" for a in sells), "realized": round(sum(a["pl"] for a in sells), 2),
                      "skipped_no_cash": skipped},
        }
        out["activity"] += acts
    out["activity"].sort(key=lambda a: (a["date"], a["type"] == "BUY"), reverse=True)
    out["activity"] = out["activity"][:800]
    return out
