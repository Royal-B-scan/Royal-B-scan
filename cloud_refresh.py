"""
Cloud refresh for the Royal B Ventures page (run by a scheduled Claude task).

  python cloud_refresh.py lists.json [--quick]

lists.json = the page's saved lists, i.e. the body of db document state/lists:
  {"watch": ["MCD", ...], "holdings": {"NVDA": {"entry": 200, "stop": 184, "date": "2026-10-20"}}}

Writes site/scan.json (full market scan; skipped with --quick), site/comeback.json (beaten-down
quality large caps; skipped with --quick) and site/data.json (Watching + Holding, with charts,
signals, exit status, earnings and buzz; plus "longterm": long-term holdings and pinned comeback stocks).
With --quick and an existing site/scan.json, data.json also gets "setups": the scan's TRIGGER / HEADS-UP
stocks re-checked with fresh prices (status may change intraday; "was" = status at the last full scan).
lists.json may also hold "longterm": {"MCD": {"cost": 250, "date": "..."}} and "pins": ["NKE", ...].
"""
from __future__ import annotations

import json
import os
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
os.chdir(BASE)
os.makedirs(os.path.join(BASE, "site"), exist_ok=True)


def refresh_setups(scan_path: str) -> list[dict]:
    """Fresh prices + rule status for the scan's TRIGGER / HEADS-UP stocks (not the 'setting up' tier).
    Keeps the scan's extra fields (sector, size, earnings, buzz, other timeframes); 'was' = the scan's status."""
    from export_site import make_entry
    from screener import analyze, get_history

    scan = json.load(open(scan_path))
    old = {s["ticker"]: s for s in scan.get("stocks", []) if s.get("status") != "SETTING UP"}
    hist = get_history(list(old))
    out = []
    for t, prev in old.items():
        df = hist.get(t)
        if df is None or len(df) < 60:
            continue
        fresh = make_entry(t, df, prev.get("name", t), prev.get("currency", "USD"), prev.get("exchange", ""), analyze(df))
        keep = {k: v for k, v in prev.items() if k not in fresh}
        fresh.update(keep)
        fresh["was"] = prev.get("status")
        out.append(fresh)
    try:
        from export_site import timeframes
        extra = timeframes([e["ticker"] for e in out])
        for e in out:
            if extra.get(e["ticker"]):
                e["tf"] = extra[e["ticker"]]
    except Exception as e:  # noqa: BLE001
        print("setup timeframes failed:", e, file=sys.stderr)
    return out


def main(path: str, quick: bool) -> None:
    t0 = time.time()
    lists = json.load(open(path)) if path and os.path.exists(path) else {}
    watch = [str(t).upper() for t in (lists.get("watch") or [])]
    holdings = {str(k).upper(): v for k, v in (lists.get("holdings") or {}).items()
                if isinstance(v, dict) and v.get("entry") and v.get("stop")}
    longterm = {str(k).upper(): (v if isinstance(v, dict) else {}) for k, v in (lists.get("longterm") or {}).items()}
    pins = [str(t).upper() for t in (lists.get("pins") or [])]
    if not watch and not holdings and not longterm and not pins:
        watch = ["MCD", "SBUX", "NVDA", "SHOP.TO"]
    summary = {}
    if not quick:
        from scan import run_scan
        out = run_scan(lambda stage, done, total, note: print(f"{stage} {done or ''}/{total or ''} {note or ''}", flush=True)
                       if total is None or (done or 0) % 1000 < 150 else None)
        summary["scan"] = out["counts"]
    from export_site import build
    data = build(watch, holdings)
    # long-term holdings + pinned comeback stocks (slower, long-term alerts)
    try:
        import comeback
        data["longterm"] = comeback.track(list(longterm) + pins, longterm, set(pins))
    except Exception as e:  # noqa: BLE001
        print("long-term failed:", e, file=sys.stderr)
        data["longterm"] = []
    # quick refresh: re-check today's scan setups (TRIGGER / HEADS-UP) with fresh prices, if scan.json is here
    scan_path = os.path.join(BASE, "site", "scan.json")
    if quick and os.path.exists(scan_path):
        try:
            data["setups"] = refresh_setups(scan_path)
            summary["setups"] = {e["ticker"]: e["status"] for e in data["setups"]}
        except Exception as e:  # noqa: BLE001
            print("setups refresh failed:", e, file=sys.stderr)
    if not quick:
        try:
            import comeback
            cb = comeback.build(lambda stage, done, total, note: print(f"{stage} {note or ''}", flush=True))
            with open(os.path.join(BASE, "site", "comeback.json"), "w") as fh:
                json.dump(cb, fh, separators=(",", ":"))
            summary["comeback"] = cb["counts"]
            summary["comeback_moved_up"] = cb["moved_up"]
        except Exception as e:  # noqa: BLE001
            print("comeback failed:", e, file=sys.stderr)
    with open(os.path.join(BASE, "site", "data.json"), "w") as fh:
        json.dump(data, fh, separators=(",", ":"))
    summary["watch"] = [s["ticker"] for s in data["stocks"]]
    summary["holdings"] = {h["ticker"]: h["position"]["status"] for h in data["holdings"]}
    summary["longterm_alerts"] = {r["ticker"]: r["lt"]["alerts"] for r in data["longterm"] if r.get("lt") and r["lt"]["alerts"]}
    summary["pinned_stages"] = {r["ticker"]: r["cb"]["stage_name"] + (" (MOVED UP)" if r["cb"]["moved_up"] else "")
                                for r in data["longterm"] if r.get("pinned")}
    summary["missing"] = sorted((set(watch) | set(holdings) | set(longterm) | set(pins))
                                - {s["ticker"] for s in data["stocks"] + data["holdings"] + data["longterm"]})
    summary["seconds"] = round(time.time() - t0)
    print("SUMMARY", json.dumps(summary))


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    main(args[0] if args else "", "--quick" in sys.argv)
