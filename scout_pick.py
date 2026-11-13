"""
Royal B Scout: the short list and the memory (Phase 3, Nov 12, 2026). The step between the workers and the brief.

    python scout_pick.py                       workers.json + scout-state.json -> shortlist.json
    python scout_pick.py --save                same, and remember today's stages (run once the brief is written)
    python scout_pick.py --workers data/workers-2026-11-06-replay.json --state data/replay-state.json --save

It does the mechanical part of the Scout's job so every run narrows the same way:
  1. Focus, 3 sectors at most. Groups in the same sector (chips, hardware, software) are one story and share a
     slot. Kept from yesterday while still in play; a new one must outrank the weakest.
     Order: a Sector Rebound (TESTED) first, then groups that were leading before the drop, then the deeper sell-off.
  2. Up to 8 candidate stocks per group, for the Scout to cut to 5 after reading the news. Order: Taylor's own
     stocks, then entry windows (TESTED: Shakeout Bounce with its group), then bouncing / pulled back / falling;
     ties go to the calmer stock. Six-month strength is NOT used: Phase 1 found it no better than a random member.
     "Calmer first" is borrowed from the Top 5 test; it has not been tested for this list.
  3. What changed since the last saved run: stage moves for groups and stocks, new and dropped groups.
  4. For each entry window, the arithmetic of Taylor's rules: stop and a do-not-chase zone. Not a tested zone.
The Scout (Claude) still decides: it reads the news, drops anything whose business broke, and writes the brief.
Memory is a local file (scout-state.json) until Phase 5 moves it into the page's database.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MAX_GROUPS, CANDIDATES, KEEP_DAYS = 3, 8, 15
IN_PLAY = ("turning up", "falling", "pulled back")
STOCK_ORDER = {"turning up: entry window": 0, "turning up alone: watch": 1, "bouncing: watch": 2, "pulled back: watch": 3,
               "falling: wait": 4, "late / stretched": 5, "in trend": 6}


def load(path, default):
    try:
        with open(path) as fh:
            return json.load(fh)
    except Exception:  # noqa: BLE001
        return default


def group_score(g: dict) -> tuple:
    return (not g.get("sector_rebound"), not g.get("was_leading"), -(g.get("drop") or 0))


def important(was: str | None, now: str, yours) -> bool:
    if not was or was == now:
        return False
    if yours or "entry window" in (was + now) or now == "late / stretched":
        return True
    return now == "falling: wait" and was in ("bouncing: watch", "turning up alone: watch", "in trend")


def slim(s: dict, prev_s: dict, owned: set, mine: set) -> dict:
    was = (prev_s.get(s["ticker"]) or {}).get("stage")
    return {"ticker": s["ticker"], "name": s.get("name"), "stage": s["stage"], "was": was, "changed": bool(was and was != s["stage"]),
            "close": s["close"], "d1": s.get("d1"), "d5": s.get("d5"), "off_low": s.get("off_low"), "drop": s.get("drop"),
            "vs20": s.get("vs20"), "vs50": s.get("vs50"), "vs200": s.get("vs200"), "volume_x": s.get("volume_x"),
            "swing_pct": s.get("swing_pct"), "currency": s.get("currency"), "earnings_in_days": s.get("earnings_in_days"),
            "earnings_date": s.get("earnings_date"), "yours": "own" if s["ticker"] in owned else "watching" if s["ticker"] in mine else None}


def plan_for(s: dict) -> dict:
    """Arithmetic from Taylor's rules for an entry window. The low is the shakeout low the workers measured."""
    close, low = s["close"], s.get("low")
    stop8 = close * 0.92
    stop = max(stop8, low) if low and low < close else stop8          # whichever is closer to the price
    return {"last_close": close, "dont_chase_above": round(close * 1.03, 2), "stop": round(stop, 2),
            "stop_is": "the shakeout low" if stop != stop8 else "8% under the close",
            "risk_per_share_pct": round((1 - stop / close) * 100, 1),
            "note": "Size with Trade on the page (1% risk, 25% cap). Wait 15-30 min after the open. Exit on a close under the 50-day."}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", default=os.path.join(HERE, "workers.json"))
    ap.add_argument("--state", default=os.path.join(HERE, "scout-state.json"))
    ap.add_argument("--out", default=os.path.join(HERE, "shortlist.json"))
    ap.add_argument("--save", action="store_true")
    a = ap.parse_args()
    w = load(a.workers, None)
    if not w:
        print(f"No workers file at {a.workers}: run scout_data.py first.", file=sys.stderr)
        return 1
    state = load(a.state, {"groups": {}, "stocks": {}, "focus": [], "asof": None, "history": []})
    day = w["asof"]
    same_day = state.get("asof") == day
    prev_g, prev_s, prev_focus = state.get("groups", {}), state.get("stocks", {}), state.get("focus", [])
    prev_entries = state.get("entries", {})
    if same_day and state.get("history"):          # re-running a day: compare with the day before, not with itself
        last = state["history"][-1]
        prev_g, prev_s, prev_focus = last.get("groups", {}), last.get("stocks", {}), last.get("focus", [])
        prev_entries = last.get("entries", {})

    groups = {g["group"]: g for g in w["groups"]}
    stocks = w["stocks"]
    mine = set((w.get("book") or {}).get("watch") or [])
    owned = {h["ticker"] for h in ((w.get("book") or {}).get("holdings") or []) + ((w.get("book") or {}).get("longterm") or [])}

    # when each entry window first opened and at what close, so the brief can say how far it has already run
    entries = {}
    for t, st in stocks.items():
        if st["stage"] == "turning up: entry window":
            entries[t] = prev_entries.get(t) or {"date": day, "close": st["close"]}

    # 1. focus: 3 families at most. A family is a sector; its groups (e.g. chips + hardware + software) are one story
    #    and take one slot between them. Kept from yesterday while in play; a new one must outrank the weakest.
    fam = lambda n: groups[n].get("family") or n  # noqa: E731
    live = [g for g in w["groups"] if g.get("sector_rebound") or g["stage"] in IN_PLAY]
    live.sort(key=group_score)
    best = {}
    for g in live:
        best.setdefault(fam(g["group"]), g)                      # a family is scored by its best group
    kept = [f for f in dict.fromkeys(fam(n) for n in prev_focus if n in groups) if f in best]
    families = list(kept)
    for f, g in best.items():
        if f in families:
            continue
        if len(families) < MAX_GROUPS:
            families.append(f)
        else:
            weakest = max(families, key=lambda x: group_score(best[x]))
            if group_score(g) < group_score(best[weakest]):
                families[families.index(weakest)] = f
    families.sort(key=lambda f: group_score(best[f]))
    families = families[:MAX_GROUPS]
    focus = [g["group"] for f in families for g in [x for x in live if fam(x["group"]) == f][:3]]
    bench = [g["group"] for g in live if g["group"] not in focus][:5]

    # 2. candidates
    out_groups = []
    for n in focus:
        g = groups[n]
        mem = [s for s in stocks.values() if s.get("group") == n]
        mem.sort(key=lambda s: (s["ticker"] not in owned, s["ticker"] not in mine, STOCK_ORDER.get(s["stage"], 9), s.get("swing_pct") or 99))
        cands = []
        for s in mem[:CANDIDATES]:
            c = slim(s, prev_s, owned, mine)
            if s["stage"] == "turning up: entry window":
                c["plan"] = plan_for(s)
                e = entries[s["ticker"]]
                c["entry_opened"] = e["date"]
                c["entry_open_close"] = e["close"]
                c["run_since_open_pct"] = round((s["close"] / e["close"] - 1) * 100, 1)
                c["late"] = bool(e["date"] != day and c["run_since_open_pct"] > 10)
            cands.append(c)
        shown = {c["ticker"] for c in cands}
        # the ones still falling, deepest first: the Scout says why and what to wait for (e.g. NVDA before earnings)
        falling = [slim(s, prev_s, owned, mine) for s in sorted(mem, key=lambda s: -(s.get("drop") or 0))
                   if s["stage"] == "falling: wait" and s["ticker"] not in shown][:4]
        counts = {}
        for s in mem:
            counts[s["stage"]] = counts.get(s["stage"], 0) + 1
        was_g = (prev_g.get(n) or {}).get("stage")
        out_groups.append({"group": n, "family": fam(n), "stage": g["stage"], "was": was_g, "changed": bool(was_g and was_g != g["stage"]),
                           "new_focus": n not in prev_focus, "sector_rebound": g.get("sector_rebound"), "sector_rebound_new": g.get("sector_rebound_new"),
                           "was_leading": g.get("was_leading"), "drop": g.get("drop"), "off_low": g.get("off_low"), "d1": g.get("d1"),
                           "up_2pct_share": g.get("up_2pct_share"), "above_50d_share": g.get("above_50d_share"),
                           "members": g.get("members"), "member_stages": counts, "candidates": cands, "falling": falling})

    # 3. what changed. Worth a line in the brief: into or out of an entry window, a new low after a bounce, anything
    #    Taylor owns or watches, and group moves. Day-to-day flips between "bouncing" and "pulled back" are minor.
    changes, minor = [], []
    for g in out_groups:
        if g["new_focus"]:
            changes.append(f"New focus group: {g['group']} ({g['stage']}" + (", Sector Rebound" if g["sector_rebound"] else "") + ")")
        elif g["changed"]:
            changes.append(f"{g['group']}: {g['was']} -> {g['stage']}")
        for c in g["candidates"] + g["falling"]:
            if c["changed"]:
                line = f"{c['ticker']}: {c['was']} -> {c['stage']}"
                (changes if important(c["was"], c["stage"], c.get("yours")) else minor).append(line)
    for n in prev_focus:
        if n not in focus:
            changes.append(f"Dropped from focus: {n} (now {groups.get(n, {}).get('stage', 'gone')})")

    # your book
    book = []
    for t in sorted(owned):
        s = stocks.get(t)
        if s:
            was = (prev_s.get(t) or {}).get("stage")
            book.append({"ticker": t, "stage": s["stage"], "was": was, "changed": bool(was and was != s["stage"]), "close": s["close"],
                         "d1": s.get("d1"), "group": s.get("group"), "earnings_in_days": s.get("earnings_in_days")})
            if was and was != s["stage"] and not any(x.startswith(t + ":") for x in changes):
                changes.append(f"{t} (yours): {was} -> {s['stage']}")

    entry_new = [c["ticker"] for g in out_groups for c in g["candidates"] if c["stage"] == "turning up: entry window" and c["was"] != c["stage"]]
    short = {"asof": day, "replay": w.get("replay"), "compared_with": None if not prev_g else (state["history"][-1]["asof"] if same_day and state.get("history") else state.get("asof")),
             "market": w.get("market"), "focus_families": families, "focus": out_groups, "also_in_play": bench, "book": book, "changes": changes, "minor_changes": minor,
             "push": {"new_entry_windows": entry_new, "group_stage_changes": [g["group"] for g in out_groups if g["changed"] or g["new_focus"]],
                      "rule": "push only if a stock entered an entry window, a focus group changed stage, or a holding has material news"},
             "other_entry_windows": [s for s in w.get("shakeout_signals", []) if s.get("with_group") and s.get("group") not in focus][:15],
             "royal_b": w.get("royal_b"), "calendar": w.get("calendar"), "problems": w.get("problems"),
             "tested": w.get("tested")}
    with open(a.out, "w") as fh:
        json.dump(short, fh, indent=1)
    by_fam = {}
    for g in out_groups:
        by_fam.setdefault(g["family"], []).append(f"{g['group']} ({g['stage']})")
    print(f"{day}: focus = " + (" | ".join(f"[{f}] " + ", ".join(v) for f, v in by_fam.items()) or "none"))
    for c in changes:
        print("  changed: " + c)
    if not changes:
        print("  nothing that matters changed since " + str(short["compared_with"]))
    if minor:
        print(f"  ({len(minor)} minor stage flips left out)")

    if a.save:
        snap = {"asof": day, "focus": focus, "entries": entries, "groups": {n: {"stage": g["stage"]} for n, g in groups.items()},
                "stocks": {t: {"stage": s["stage"]} for t, s in stocks.items()}}
        hist = [h for h in state.get("history", []) if h.get("asof") != day]
        if state.get("asof") and state.get("asof") != day:
            hist.append({"asof": state["asof"], "focus": state.get("focus", []), "groups": state.get("groups", {}), "stocks": state.get("stocks", {}),
                         "entries": state.get("entries", {})})
        snap["history"] = hist[-KEEP_DAYS:]
        with open(a.state, "w") as fh:
            json.dump(snap, fh, separators=(",", ":"))
        print(f"  remembered in {os.path.basename(a.state)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
