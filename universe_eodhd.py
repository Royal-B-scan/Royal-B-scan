"""
Whole-market universe from EODHD (whole-market plan, step 1, Nov 13 2026).

Every US and Toronto company worth $2B or more, one row per company:
  - EODHD screener (market cap > $2B), searched sector by sector so the 1,000-row page limit never cuts the list
  - kept: Type "Common Stock" on NYSE / NASDAQ / NYSE American / NYSE Arca / Cboe BZX, or on the TSX
  - dropped: ETFs, funds, preferreds, OTC / pink sheets, Toronto CDRs (they follow their US company)
  - a company listed in both countries keeps its Toronto listing (it is Canadian; US companies on the TSX are CDRs)
  - share classes of one company (GOOG / GOOGL): the one that trades more
  - group = EODHD industry; industries with fewer than 8 members roll up to their sector (the Scout's existing rule)

    python universe_eodhd.py        -> research/universe_eodhd.csv (+ a summary)

Key: ~/Documents/Stock Screener/.eodhd_key (Mac) or env EODHD_API_KEY (cloud). Never printed, never saved here.
About 30 requests (x5 for the screener) per run: run weekly.
"""
from __future__ import annotations

import collections
import csv
import json
import os
import re
import sys

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "research", "universe_eodhd.csv")
MIN_CAP = 2e9
MIN_GROUP = 8
US_EXCH = {"NYSE", "NASDAQ", "NYSE MKT", "NYSE ARCA", "BATS", "AMEX"}
SECTORS = ["Technology", "Financial Services", "Financials", "Industrials", "Healthcare", "Consumer Cyclical",
           "Consumer Defensive", "Basic Materials", "Communication Services", "Energy", "Utilities", "Real Estate"]


def key() -> str:
    k = os.environ.get("EODHD_API_KEY")
    if not k:
        with open(os.path.expanduser("~/Documents/Stock Screener/.eodhd_key")) as fh:
            k = fh.read()
    return k.strip()


def api(path: str, **params):
    params.update(api_token=key(), fmt="json")
    r = requests.get("https://eodhd.com/api/" + path, params=params, timeout=120)
    r.raise_for_status()
    return r.json()


def screen(exchange: str, sector: str) -> list[dict]:
    rows = []
    for off in range(0, 1000, 100):
        f = [["market_capitalization", ">", MIN_CAP], ["exchange", "=", exchange], ["sector", "=", sector]]
        d = api("screener", filters=json.dumps(f), limit=100, offset=off, sort="market_capitalization.desc").get("data", [])
        rows += d
        if len(d) < 100:
            return rows
    print(f"  WARNING: {exchange} {sector} reached 1,000 rows; the list may be cut off", file=sys.stderr)
    return rows


def name_key(n: str) -> str:
    n = re.sub(r"[^a-z0-9 ]", " ", (n or "").lower())
    n = re.sub(r"\b(inc|corp|corporation|co|ltd|limited|plc|sa|ag|nv|the|class [a-z]|holdings?|group|company)\b", " ", n)
    return " ".join(n.split())[:28]


def build() -> list[dict]:
    meta = {}
    for ex in ("US", "TO"):
        for s in api(f"exchange-symbol-list/{ex}"):
            meta[(ex, s["Code"])] = s
    raw = []
    for ex, exf in (("US", "us"), ("TO", "TO")):
        for sec in SECTORS:
            for r in screen(exf, sec):
                raw.append((ex, r))
    seen_code, drops = set(), collections.Counter()
    rows = []
    for ex, r in raw:
        code = r["code"]
        if (ex, code) in seen_code:
            continue
        seen_code.add((ex, code))
        m = meta.get((ex, code), {})
        name = r.get("name") or m.get("Name") or code
        if m.get("Type") != "Common Stock":
            drops["not common stock (fund, ETF, preferred)"] += 1
            continue
        if ex == "US" and m.get("Exchange") not in US_EXCH:
            drops["OTC / pink sheets"] += 1
            continue
        if ex == "TO" and "CDR" in name.upper():
            drops["Toronto CDR"] += 1
            continue
        rows.append({"ticker": code + (".TO" if ex == "TO" else ""), "name": name, "country": "CA" if ex == "TO" else "US",
                     "exchange": m.get("Exchange"), "sector": "Financial Services" if r.get("sector") == "Financials" else r.get("sector"),
                     "industry": r.get("industry") or r.get("sector"), "market_cap": int(r.get("market_capitalization") or 0),
                     "avgvol": float(r.get("avgvol_200d") or 0), "_key": name_key(name)})
    # one row per company: Toronto listing first (Canadian company), then the class that trades more
    best: dict[str, dict] = {}
    for r in sorted(rows, key=lambda r: (r["country"] != "CA", -r["avgvol"])):
        if r["_key"] in best:
            drops["second listing / share class of a company"] += 1
            continue
        best[r["_key"]] = r
    out = sorted(best.values(), key=lambda r: -r["market_cap"])
    size = collections.Counter(r["industry"] for r in out)
    for r in out:
        r["group"] = r["industry"] if size[r["industry"]] >= MIN_GROUP else r["sector"]
        del r["_key"]
    build.drops = drops
    return out


def main() -> int:
    out = build()
    with open(OUT, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["ticker", "name", "country", "exchange", "sector", "industry", "group", "market_cap", "avgvol"])
        w.writeheader()
        w.writerows(out)
    c = collections.Counter(r["country"] for r in out)
    print(f"wrote {OUT}: {len(out)} companies over $2B ({c['US']} US, {c['CA']} Toronto), "
          f"{len(set(r['group'] for r in out))} groups")
    print("dropped: " + ", ".join(f"{v} {k}" for k, v in build.drops.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
