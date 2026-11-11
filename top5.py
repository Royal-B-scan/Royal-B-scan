"""
Top 5 front page (Taylor, decided Nov 9, 2026): one short list pulled from every screener, ranked calmest first.
Test: backtest-top5-front-page.md (daily Top 5, calmest first: 2023-25 PF 2.06, 2026 out-of-sample 1.14 deduped,
6-7% hit the stop; random picks 0.72). Calmest first is the only ranking that beat random in both periods.

Pool (large caps, $10B+, no ETFs), any screener that fired today:
  Early Turn   BREAKOUT / PULLBACK that are green (close above the 50-day, under 15% above the 20-day and the 50-day)
  Trend Cross  crossed today (TRIGGER), not an OBV-flat Skip
  Comebacks    moved up to Turning up / Recovered today, or a Comeback Turn signal
  Weekly Trend new weekly cross (WK NEW)
Then: one row per company (US listing over .TO), not owned, no earnings within 7 days, calmest first
(average daily high-to-low swing over 20 days, % of the close). "new" = not in yesterday's Top 5.

    build(scan, comeback, lists, prev=None) -> {"rows": [...], "pool": n, "skipped": {...}}
"""
from __future__ import annotations

import re

MIN_CAP = 10e9
N = 5
SRC = {"early": "Early Turn", "cross": "Trend Cross", "comeback": "Comebacks", "turn": "Comeback Turn", "weekly": "Weekly Trend"}


def swing(row: dict, n: int = 20) -> float | None:
    cs = ((row.get("series") or {}).get("candles") or [])[-n:]
    vals = [(h - l) / c * 100 for _, _o, h, l, c in cs if c]
    return round(sum(vals) / len(vals), 2) if len(vals) >= 10 else None


def _base(t: str) -> str:
    return re.sub(r"\.(TO|V|NE)$", "", t.upper()).replace("-", ".").replace(".UN", "")


def _name_key(name: str) -> str:
    n = re.sub(r"[^a-z0-9 ]", " ", (name or "").lower())
    n = re.sub(r"\b(inc|corp|corporation|co|ltd|limited|plc|sa|ag|nv|the|class [a-z]|holdings?|group)\b", " ", n)
    return " ".join(n.split())[:24]


def _green(r: dict) -> bool:
    ee = r.get("ee") or {}
    c, s20, s50 = r.get("close"), ee.get("sma20"), ee.get("sma50")
    if not (c and s20 and s50):
        return False
    return c >= s50 and c / s20 - 1 < 0.15 and c / s50 - 1 < 0.15


def _earn_soon(r: dict) -> bool:
    e = r.get("earnings") or {}
    d = e.get("days") if isinstance(e, dict) else None
    return isinstance(d, int) and 0 <= d <= 7


def build(scan: dict, comeback: dict | None, lists: dict | None, prev: list | None = None) -> dict:
    cand = []
    for r in scan.get("early") or []:
        if r.get("status") in ("BREAKOUT", "PULLBACK") and _green(r):
            cand.append((r, "early", f"Early Turn {r['status'].lower()}"))
    for r in scan.get("stocks") or []:
        if r.get("status") == "TRIGGER" and not r.get("obv_skip"):
            cand.append((r, "cross", "Trend Cross: 10-day crossed the 20-day on volume"))
    for r in (comeback or {}).get("rows") or []:
        cb = r.get("cb") or {}
        if cb.get("moved_up") and cb.get("stage") in (3, 4):
            cand.append((r, "comeback", f"Comebacks: moved up to {cb.get('stage_name', '').title()}"))
    for r in (comeback or {}).get("turn") or []:
        cand.append((r, "turn", "Comeback Turn: first close back above the 20-day after an oversold low"))
    # A weekly cross stays "WK NEW" all week; it counts as a signal only on the first trading day after the cross week
    from datetime import date
    last = scan.get("last_bar")
    for r in ((scan.get("weekly") or {}).get("rows")) or []:
        cd = (r.get("wk") or {}).get("cross_date")
        fresh = bool(last and cd and 0 < (date.fromisoformat(last) - date.fromisoformat(cd)).days <= 3)
        if r.get("status") == "WK NEW" and fresh:
            cand.append((r, "weekly", "Weekly Trend: new weekly 8/21 cross"))

    # Nov 10: Weekly Trend rows carry no earnings date; look them up for the big ones that made the pool
    try:
        wk = [r for r, src, _ in cand if src == "weekly" and not r.get("earnings") and (r.get("market_cap") or 0) >= MIN_CAP]
        if wk:
            import earnings
            earnings.attach(wk, max_fetch=60)
    except Exception as e:  # noqa: BLE001
        print("top5 weekly earnings failed:", e)
    # earnings dates: borrow from any other row for the same ticker when a row still has none
    earn = {}
    for r, _, _ in cand:
        if isinstance(r.get("earnings"), dict) and r["earnings"].get("days") is not None:
            earn.setdefault(r["ticker"], r["earnings"])
    owned = {str(t).upper() for t in ((lists or {}).get("holdings") or []) + ((lists or {}).get("longterm") or [])}
    owned_base = {_base(t) for t in owned}
    skipped = {"small": 0, "etf": 0, "owned": 0, "earnings": 0, "no_data": 0}
    best: dict[str, dict] = {}
    pool = set()
    for r, src, why in cand:
        t = r.get("ticker")
        if not t:
            continue
        if r.get("kind") == "ETF":
            skipped["etf"] += 1
            continue
        if (r.get("market_cap") or 0) < MIN_CAP:
            skipped["small"] += 1
            continue
        pool.add(t)
        if t in owned or _base(t) in owned_base:
            skipped["owned"] += 1
            continue
        if _earn_soon({"earnings": r.get("earnings") or earn.get(t)}):
            skipped["earnings"] += 1
            continue
        sw = swing(r)
        if sw is None:
            skipped["no_data"] += 1
            continue
        key = _name_key(r.get("name")) or _base(t)
        cur = best.get(key)
        row = {"ticker": t, "name": r.get("name") or t, "currency": r.get("currency", "USD"), "sector": r.get("sector"),
               "market_cap": r.get("market_cap"), "close": r.get("close"), "change_pct": r.get("change_pct"),
               "swing": sw, "sources": [src], "why": [why], "obv": (r.get("ctx") or {}).get("obv_trend"),
               "earnings": r.get("earnings") or earn.get(t)}
        if cur is None:
            best[key] = row
            continue
        if src not in cur["sources"]:
            cur["sources"].append(src)
            cur["why"].append(why)
        if cur["ticker"].endswith((".TO", ".V")) and not t.endswith((".TO", ".V")):   # prefer the US listing
            row.update(sources=cur["sources"], why=cur["why"])
            best[key] = row
    rows = sorted(best.values(), key=lambda x: x["swing"])[:N]
    prev = set(prev or [])
    for i, x in enumerate(rows):
        x["rank"] = i + 1
        x["new"] = x["ticker"] not in prev
        x["source_names"] = [SRC[s] for s in x["sources"]]
    return {"rows": rows, "pool": len(pool), "eligible": len(best), "skipped": skipped}


if __name__ == "__main__":   # python top5.py scan.json comeback.json data.json
    import json
    import sys
    sj, cj, dj = (json.load(open(p)) for p in sys.argv[1:4])
    res = build(sj, cj, dj.get("lists"))
    print(json.dumps({k: v for k, v in res.items() if k != "rows"}))
    for x in res["rows"]:
        print(x["rank"], x["ticker"], x["swing"], x["source_names"], x["close"], (x.get("earnings") or {}).get("date"))
