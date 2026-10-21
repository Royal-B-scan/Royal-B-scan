"""
Watching + Holding lists.

watchlist.txt   one ticker per line (stocks you're waiting to enter)
holdings.json   {"NVDA": {"entry": 180.5, "stop": 166.0, "date": "2026-10-20"}, ...}

Exit status for a holding (checked against the latest price):
  STOP HIT    price at or below your stop
  EXIT        close below the 50-day average (Rules v1 exit)
  NEAR EXIT   within NEAR_PCT of whichever exit line is higher (stop or 50-day)
  HOLD        otherwise
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime
from zoneinfo import ZoneInfo

BASE = os.path.dirname(os.path.abspath(__file__))
WATCH_FILE = os.path.join(BASE, "watchlist.txt")
HOLD_FILE = os.path.join(BASE, "holdings.json")
NEAR_PCT = 0.03
TICKER_RE = re.compile(r"[A-Z0-9][A-Z0-9.\-]{0,11}")


def read_watchlist() -> list[str]:
    if not os.path.exists(WATCH_FILE):
        return ["MCD", "SBUX", "NVDA"]
    with open(WATCH_FILE) as fh:
        out = [ln.strip().upper() for ln in fh if ln.strip() and not ln.startswith("#")]
    return list(dict.fromkeys(out))


def write_watchlist(tickers: list[str]) -> None:
    with open(WATCH_FILE, "w") as fh:
        fh.write("# One ticker per line. Canadian stocks: add .TO (TSX) or .V (TSXV), e.g. SHOP.TO\n")
        fh.write("\n".join(tickers) + "\n")


def read_holdings() -> dict:
    try:
        with open(HOLD_FILE) as fh:
            data = json.load(fh)
        return {k.upper(): v for k, v in data.items() if isinstance(v, dict)}
    except Exception:  # noqa: BLE001
        return {}


def write_holdings(h: dict) -> None:
    tmp = HOLD_FILE + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(h, fh, indent=1)
    os.replace(tmp, HOLD_FILE)


def add_holding(ticker: str, entry: float, stop: float | None, date: str | None = None) -> dict:
    ticker = ticker.strip().upper()
    if not TICKER_RE.fullmatch(ticker):
        raise ValueError("That doesn't look like a ticker.")
    entry = float(entry)
    if entry <= 0:
        raise ValueError("Entry price must be above zero.")
    stop = float(stop) if stop not in (None, "") else round(entry * 0.92, 2)
    if stop >= entry:
        raise ValueError("Your stop should be below your entry price.")
    h = read_holdings()
    h[ticker] = {"entry": round(entry, 4), "stop": round(stop, 4),
                 "date": date or datetime.now(ZoneInfo("America/Vancouver")).strftime("%Y-%m-%d")}
    write_holdings(h)
    # once you own it, it moves from Watching to Holding
    wl = read_watchlist()
    if ticker in wl:
        write_watchlist([t for t in wl if t != ticker])
    return h


def remove_holding(ticker: str, back_to_watch: bool = False) -> dict:
    ticker = ticker.strip().upper()
    h = read_holdings()
    h.pop(ticker, None)
    write_holdings(h)
    if back_to_watch:
        wl = read_watchlist()
        if ticker not in wl:
            write_watchlist(wl + [ticker])
    return h


def exit_status(entry: dict, pos: dict) -> dict:
    """entry = a stock entry from export_site.make_entry; pos = holdings.json record.

    The 50-day exit only "arms" once the stock has closed above its 50-day on or after the
    buy date. Until then (e.g. bought while already below the 50-day) the stop is the exit line.
    """
    close = float(entry["close"])
    sma_rows = entry["series"].get("sma50") or []
    sma50 = sma_rows[-1][1] if sma_rows else None
    stop = float(pos["stop"])
    since = str(pos.get("date") or "")
    smap = {r[0]: r[1] for r in sma_rows}
    armed = any(str(c[0]) >= since and c[0] in smap and c[4] > smap[c[0]]
                for c in entry["series"].get("candles", []))
    lines = [stop] + ([sma50] if (armed and sma50) else [])
    line = max(lines)
    if close <= stop:
        status = "STOP HIT"
    elif armed and sma50 and close < sma50:
        status = "EXIT"
    elif (close - line) / close <= NEAR_PCT:
        status = "NEAR EXIT"
    else:
        status = "HOLD"
    return {
        "entry": pos["entry"], "stop": stop, "date": pos.get("date"),
        "sma50": round(sma50, 2) if sma50 else None, "armed": armed,
        "exit_line": round(line, 2), "exit_line_is": "stop" if line == stop else "50-day",
        "room_pct": round((close - line) / close * 100, 2),
        "pl_pct": round((close / pos["entry"] - 1) * 100, 2),
        "status": status,
    }
