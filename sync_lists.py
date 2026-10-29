"""
Pull Taylor's lists from the Google Sheet that the Royal B page writes to (Oct 28, 2026).

Every time a list changes on the page (watch, buy, sell, long-term, pins, channels), the page saves the same
JSON that "Copy for GitHub" makes into cell A1 of the sheet "Royal B lists sync". This script runs at the start
of the daily scan and every intraday check, and overwrites lists.json with it. If anything goes wrong (sheet not
shared, network, bad JSON) it changes nothing and the repo's own lists.json is used, as before.

The sheet must be shared as "Anyone with the link: Viewer". It holds the same data lists.json already holds.
"""
import csv
import io
import json
import os
import sys
import urllib.request

SHEET = os.environ.get("LISTS_SHEET_ID") or "1nzSSAlhkvmhGT7vDi4t-xbi-xcomW5EjcJQerxF7yMw"
URL = f"https://docs.google.com/spreadsheets/d/{SHEET}/export?format=csv&gid=0&range=A1"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lists.json")
ERR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sync_lists_error.txt")  # read by github_scan.py

try:
    raw = urllib.request.urlopen(URL, timeout=30).read().decode("utf-8")
    cell = next(csv.reader(io.StringIO(raw)))[0]
    data = json.loads(cell)
    if not isinstance(data.get("watch"), list):
        raise ValueError("no watch list in the sheet")
except Exception as e:  # noqa: BLE001
    print(f"Lists sync skipped, using the repo's lists.json ({e}). Is the sheet shared as 'Anyone with the link'?")
    with open(ERR, "w") as fh:
        fh.write(f"Couldn't read the lists sheet, so the older lists.json was used ({e})")
    sys.exit(0)

if os.path.exists(ERR):
    os.remove(ERR)

with open(OUT, "w") as fh:
    json.dump(data, fh, indent=1)
print(f"lists.json from the page (synced {data.get('synced', '?')}): {len(data['watch'])} watching, "
      f"{len(data.get('holdings') or {})} holding, {len(data.get('longterm') or {})} long-term, "
      f"{len(data.get('pins') or [])} pinned")
