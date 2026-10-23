"""
Royal B Ventures: daily market scan, run by GitHub Actions (.github/workflows/scan.yml).

Runs the full US + Canada scan (with the signal journal) and the comeback screen, then writes
  engine/site/scan.json       scan results + journal
  engine/site/comeback.json   comeback watch
  engine/site/status.json     {"ok", "date", "updated", "counts", "comeback", "seconds", "lists"}
  engine/site/data.json       Taylor's Watching / Portfolio / long-term / pinned stocks (from lists.json in
                              the repo, Oct 23): charts, signals, exit status, earnings. Replaces the old
                              Claude "refresh now" task. lists.json holds tickers, entry and stop prices only.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

BASE = os.path.dirname(os.path.abspath(__file__))
ENGINE = BASE
sys.path.insert(0, ENGINE)
os.chdir(ENGINE)
SITE = os.path.join(ENGINE, "site")
os.makedirs(SITE, exist_ok=True)


def say(stage, done=None, total=None, note=None):
    if total is None or (done or 0) % 1000 < 250:
        print(f"{stage} {done or ''}/{total or ''} {note or ''}", flush=True)


def main() -> None:
    t0 = time.time()
    from scan import run_scan
    out = run_scan(say)
    status = {"ok": True, "counts": out["counts"], "last_bar": out.get("last_bar")}
    try:
        import comeback
        cb = comeback.build(say)
        with open(os.path.join(SITE, "comeback.json"), "w") as fh:
            json.dump(cb, fh, separators=(",", ":"))
        status["comeback"] = cb["counts"]
        status["comeback_moved_up"] = cb["moved_up"]
    except Exception as e:  # noqa: BLE001
        print("comeback failed:", e, file=sys.stderr)
        status["comeback_error"] = str(e)[:200]
    try:
        status["lists"] = build_lists()
    except Exception as e:  # noqa: BLE001
        print("lists failed:", e, file=sys.stderr)
        status["lists_error"] = str(e)[:200]
    now = datetime.now(timezone.utc)
    status.update(updated=now.isoformat(timespec="minutes"),
                  date=now.astimezone(ZoneInfo("America/Vancouver")).strftime("%Y-%m-%d"),
                  seconds=round(time.time() - t0))
    with open(os.path.join(SITE, "status.json"), "w") as fh:
        json.dump(status, fh, indent=1)
    print("SUMMARY", json.dumps(status))


def build_lists() -> dict:
    """data.json for the page's Watching / Portfolio / long-term / pinned stocks, from lists.json."""
    path = os.path.join(BASE, "lists.json")
    if not os.path.exists(path):
        return {"missing": "lists.json"}
    with open(path) as fh:
        lists = json.load(fh)
    up = lambda xs: [str(t).strip().upper() for t in (xs or []) if str(t).strip()]  # noqa: E731
    watch = up(lists.get("watch"))
    holdings = {str(k).upper(): v for k, v in (lists.get("holdings") or {}).items()
                if isinstance(v, dict) and v.get("entry") and v.get("stop")}
    longterm = {str(k).upper(): (v if isinstance(v, dict) else {}) for k, v in (lists.get("longterm") or {}).items()}
    pins = up(lists.get("pins"))
    from export_site import build
    data = build(watch, holdings)
    try:
        import comeback
        data["longterm"] = comeback.track(list(longterm) + pins, longterm, set(pins))
    except Exception as e:  # noqa: BLE001
        print("long-term failed:", e, file=sys.stderr)
        data["longterm"] = []
    data["source"] = "github"
    data["lists"] = {"watch": watch, "holdings": sorted(holdings), "longterm": sorted(longterm), "pins": pins}
    with open(os.path.join(SITE, "data.json"), "w") as fh:
        json.dump(data, fh, separators=(",", ":"))
    got = {s["ticker"] for s in data.get("stocks", []) + data.get("holdings", []) + data.get("longterm", [])}
    return {"watch": len(watch), "holdings": len(holdings), "longterm": len(longterm), "pins": len(pins),
            "missing": sorted((set(watch) | set(holdings) | set(longterm) | set(pins)) - got)}


if __name__ == "__main__":
    main()
