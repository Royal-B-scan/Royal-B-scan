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
    # Oct 30: Judgement Day (info only) on every stock the page shows; goes into scan.json "judgement"
    judgement = None
    try:
        judgement = run_judgement()
        status["judgement"] = len(judgement["by"])
    except Exception as e:  # noqa: BLE001
        print("judgement failed:", e, file=sys.stderr)
        status["judgement_error"] = str(e)[:200]
    # Oct 28: collect every failure in one place (status.json and scan.json), so the page can show it in red
    problems = dict(out.get("problems") or {})
    for key, label in (("comeback_error", "comeback kings"), ("lists_error", "your lists"), ("judgement_error", "judgement day")):
        if status.get(key):
            problems[label] = status[key]
    if isinstance(status.get("lists"), dict) and status["lists"].get("longterm_error"):
        problems["long-term"] = status["lists"].pop("longterm_error")
    sync_err = os.path.join(BASE, "sync_lists_error.txt")
    if os.path.exists(sync_err):
        problems["lists sync"] = open(sync_err).read().strip()[:200]
    status["problems"] = problems
    if problems:
        print("PROBLEMS", json.dumps(problems), file=sys.stderr)
    scan_path = os.path.join(SITE, "scan.json")
    try:
        with open(scan_path) as fh:
            sj = json.load(fh)
        sj["problems"] = problems
        if judgement:
            sj["judgement"] = judgement
        with open(scan_path, "w") as fh:
            json.dump(sj, fh, separators=(",", ":"))
    except Exception as e:  # noqa: BLE001
        print("could not add problems to scan.json:", e, file=sys.stderr)
    now = datetime.now(timezone.utc)
    status.update(updated=now.isoformat(timespec="minutes"),
                  date=now.astimezone(ZoneInfo("America/Vancouver")).strftime("%Y-%m-%d"),
                  seconds=round(time.time() - t0))
    with open(os.path.join(SITE, "status.json"), "w") as fh:
        json.dump(status, fh, indent=1)
    print("SUMMARY", json.dumps(status))


def run_judgement() -> dict:
    """Judgement Day for Taylor's Watching list + holdings only (Oct 30: the page shows it on green and yellow
    crowns, which live on Watching). Uses that day's closes and earnings dates."""
    def load(name):
        try:
            with open(os.path.join(SITE, name)) as fh:
                return json.load(fh)
        except Exception:  # noqa: BLE001
            return {}
    sj, dj = load("scan.json"), load("data.json")
    lists = dj.get("lists") or {}
    order, closes, earn = [], {}, {}
    for t in (lists.get("watch") or []) + (lists.get("holdings") or []):
        order.append(t)
    early = sj.get("early") or []
    stocks = sj.get("stocks") or []
    for s in (dj.get("stocks") or []) + (dj.get("holdings") or []) + (dj.get("longterm") or []) + early + stocks:
        t = s.get("ticker")
        if t and s.get("close"):
            closes.setdefault(t, s["close"])
        e = s.get("earnings") or {}
        if t and isinstance(e, dict) and isinstance(e.get("days"), int):
            earn.setdefault(t, e["days"])
    import judgement
    return judgement.run(order, closes, earn)


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
        lt_error = str(e)[:200]
    else:
        lt_error = None
    data["source"] = "github"
    data["lists"] = {"watch": watch, "holdings": sorted(holdings), "longterm": sorted(longterm), "pins": pins}
    with open(os.path.join(SITE, "data.json"), "w") as fh:
        json.dump(data, fh, separators=(",", ":"))
    got = {s["ticker"] for s in data.get("stocks", []) + data.get("holdings", []) + data.get("longterm", [])}
    res = {"watch": len(watch), "holdings": len(holdings), "longterm": len(longterm), "pins": len(pins),
           "missing": sorted((set(watch) | set(holdings) | set(longterm) | set(pins)) - got)}
    if lt_error:
        res["longterm_error"] = lt_error
    return res


if __name__ == "__main__":
    main()
