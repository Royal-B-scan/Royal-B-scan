"""
Hype / buzz from two free sources, merged per ticker:
  Reddit   ApeWisdom mentions in the last 24h vs the 24h before (top ~200 tickers)
  Twitter-style  StockTwits trending symbols (top 30) incl. a one-line "why it's trending" summary

A ticker is BUZZING if any of:
  - trending on StockTwits
  - Reddit mentions >= 15 and at least 1.5x the previous 24h
  - Reddit rank <= 25
US tickers only (neither source covers TSX/TSXV well).
"""
from __future__ import annotations

import sys
from html import unescape

import requests

UA = {"User-Agent": "Mozilla/5.0 (RoyalBVentures screener)"}


def _ape(pages: int = 2) -> list[dict]:
    out = []
    for p in range(1, pages + 1):
        try:
            r = requests.get(f"https://apewisdom.io/api/v1.0/filter/all-stocks/page/{p}", headers=UA, timeout=20)
            r.raise_for_status()
            out += r.json().get("results", [])
        except Exception as e:  # noqa: BLE001
            print(f"  apewisdom: {e}", file=sys.stderr)
            break
    return out


def _stocktwits() -> list[dict]:
    try:
        r = requests.get("https://api.stocktwits.com/api/2/trending/symbols.json", headers=UA, timeout=20)
        r.raise_for_status()
        return r.json().get("symbols", [])
    except Exception as e:  # noqa: BLE001
        print(f"  stocktwits: {e}", file=sys.stderr)
        return []


def get_hype() -> dict[str, dict]:
    hype: dict[str, dict] = {}
    for x in _ape():
        t = str(x.get("ticker", "")).upper()
        if not t:
            continue
        m = float(x.get("mentions") or 0)
        prev = float(x.get("mentions_24h_ago") or 0)
        hype[t] = {"ticker": t, "name": unescape(x.get("name") or ""), "reddit_mentions": int(m),
                   "reddit_prev": int(prev), "reddit_rank": int(x.get("rank") or 0),
                   "reddit_change_pct": round((m - prev) / max(prev, 1) * 100)}
    for x in _stocktwits():
        t = str(x.get("symbol", "")).upper()
        if not t or x.get("region") not in (None, "US"):
            continue
        h = hype.setdefault(t, {"ticker": t, "name": x.get("title") or ""})
        h["st_rank"] = x.get("rank")
        h["st_score"] = round(float(x.get("trending_score") or 0), 1)
        h["st_summary"] = ((x.get("trends") or {}).get("summary") or "").strip()
        h["st_watchers"] = x.get("watchlist_count")
    for h in hype.values():
        m, prev, rank = h.get("reddit_mentions", 0), h.get("reddit_prev", 0), h.get("reddit_rank") or 999
        h["buzzing"] = bool(h.get("st_score") or (m >= 15 and m >= 1.5 * max(prev, 1)) or rank <= 25)
    return hype


def hype_list(hype: dict[str, dict], n: int = 40) -> list[dict]:
    """Ranked list for the Hype tab: StockTwits trending first, then biggest Reddit jumps."""
    rows = [h for h in hype.values() if h["buzzing"]]
    rows.sort(key=lambda h: (-(h.get("st_score") or 0), -(h.get("reddit_change_pct") or 0) * (h.get("reddit_mentions", 0) >= 15)))
    return rows[:n]


def attach(entries: list[dict], hype: dict[str, dict]) -> None:
    for e in entries:
        h = hype.get(e["ticker"])
        if h and h.get("buzzing"):
            e["buzz"] = {k: h.get(k) for k in ("reddit_mentions", "reddit_change_pct", "reddit_rank", "st_rank", "st_score", "st_summary")}
