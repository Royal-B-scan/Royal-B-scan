"""
Turn a Scout brief (briefs/YYYY-MM-DD-am|pm.md, the format in skills/scout/SKILL.md) into briefs/latest.json for the
Scout box on Royal B's Home page (Phase 5, Nov 13 2026).

    python brief_to_json.py briefs/2026-11-13-am.md      -> briefs/latest.json

Shape (PLAN.md "state/scout", simplified): {asof, session, title, big_picture, sectors:[{name, stage, numbers, why,
stocks:[{ticker, stage, line}]}], your_stocks, coming_up, changed, royal_b, tested, brief_file, updated}.
Text keeps markdown links [Name](url); the page turns them into links. No holdings beyond what the brief says.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))


def parse(text: str, fname: str) -> dict:
    lines = [l.rstrip() for l in text.splitlines()]
    m = re.match(r"(\d{4}-\d{2}-\d{2})-(am|pm)", os.path.basename(fname))
    out = {"asof": m.group(1) if m else None, "session": (m.group(2) if m else None), "title": lines[0] if lines else "",
           "big_picture": "", "urgent": "", "sectors": [], "your_stocks": "", "coming_up": "", "changed": "",
           "royal_b": "", "tested": "", "notes": [], "brief_file": os.path.basename(fname),
           "updated": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    sec = None
    for l in lines[1:]:
        s = l.strip()
        if not s or s == "Not financial advice.":
            continue
        fm = re.match(r"Focus \d+ · (.+?):\s*(.+?)(?:\s{2,}\((.+)\))?$", s)
        if fm:
            sec = {"name": fm.group(1).strip(), "stage": fm.group(2).strip(), "numbers": (fm.group(3) or "").strip(),
                   "why": "", "stocks": [], "notes": []}
            out["sectors"].append(sec)
            continue
        key = next((k for k, p in (("big_picture", "Big picture:"), ("urgent", "URGENT"), ("your_stocks", "Your stocks:"),
                                   ("coming_up", "Coming up:"), ("changed", "Changed since the last brief:"),
                                   ("royal_b", "Royal B's screen"), ("tested", "Tested:")) if s.startswith(p)), None)
        if key:
            out[key] = s.split(":", 1)[1].strip() if ":" in s else s
            if key != "big_picture":
                sec = None
            continue
        if sec is not None and s.startswith("Why:"):
            sec["why"] = s[4:].strip()
            continue
        sm = re.match(r"- ([A-Z0-9.\-]+): (.+)$", s)
        if sec is not None and sm:
            rest = sm.group(2)
            stage, _, line = rest.partition(". ")
            sec["stocks"].append({"ticker": sm.group(1), "stage": stage.strip(), "line": line.strip()})
            continue
        (sec["notes"] if sec is not None else out["notes"]).append(s)
    return out


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    src = sys.argv[1]
    d = parse(open(src, encoding="utf-8").read(), src)
    dst = os.path.join(os.path.dirname(os.path.abspath(src)), "latest.json")
    with open(dst, "w", encoding="utf-8") as fh:
        json.dump(d, fh, ensure_ascii=False, indent=1)
    print(f"wrote {dst}: {d['asof']} {d['session']}, {len(d['sectors'])} sectors, "
          f"{sum(len(s['stocks']) for s in d['sectors'])} stocks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
