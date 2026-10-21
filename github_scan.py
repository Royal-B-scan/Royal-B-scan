"""
Royal B Ventures: daily market scan, run by GitHub Actions (.github/workflows/scan.yml).

Runs the full US + Canada scan (with the signal journal) and the comeback screen, then writes
  engine/site/scan.json       scan results + journal
  engine/site/comeback.json   comeback watch
  engine/site/status.json     {"ok", "date", "updated", "counts", "comeback", "seconds"}
No personal data: your lists, positions and money stay on the Royal B page.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

BASE = os.path.dirname(os.path.abspath(__file__))
ENGINE = (BASE, "engine")
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
    now = datetime.now(timezone.utc)
    status.update(updated=now.isoformat(timespec="minutes"),
                  date=now.astimezone(ZoneInfo("America/Vancouver")).strftime("%Y-%m-%d"),
                  seconds=round(time.time() - t0))
    with open(os.path.join(SITE, "status.json"), "w") as fh:
        json.dump(status, fh, indent=1)
    print("SUMMARY", json.dumps(status))


if __name__ == "__main__":
    main()
