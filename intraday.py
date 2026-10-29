"""
Royal B Ventures: intraday ENTRY alerts, run by GitHub Actions (.github/workflows/intraday.yml).

Weekdays at 10:00am, 1:00pm and 3:15pm New York time (30 min after the open, mid-day,
and 45 min before the close; 7:00 / 10:00 / 12:15 Pacific in summer), it re-checks the best candidates with
today's prices so far:
  - every stock in the latest daily scan (TRIGGER / HEADS-UP setups + the "setting up" leaders)
  - plus every ticker in watchlist.txt (one per line; edit it on GitHub)
and sends a phone notification (ntfy) only when a stock NEWLY turns TRIGGER or HEADS-UP.
Oct 28: it also pings when a stock drops below the BOTTOM line of a channel Taylor drew on the page
(lists.json "channels", synced from the page). Breaks above the top line are left alone: let winners run.
Exits are not checked: Taylor's stop / limit orders at InvestorLine handle those.

Today's volume is incomplete during the day, so it is scaled to a full-day pace
(volume so far / fraction of the 9:30am-4:00pm ET session elapsed). A morning signal can fade by
the close; the daily 3:20pm summary has the final status.

  python intraday.py           normal scheduled run (only inside the check windows)
  python intraday.py --force   manual test run: checks now and sends a "connected" note if nothing new
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
os.chdir(BASE)
ET = ZoneInfo("America/New_York")      # market time: check windows follow the exchange
PT = ZoneInfo("America/Vancouver")     # Taylor's local time, for the "as of" text
STATE = os.path.join(BASE, "site", "intraday.json")
SCAN = os.path.join(BASE, "site", "scan.json")
WATCH = os.path.join(BASE, "watchlist.txt")
PAGE = "https://claude.ai/artifact/HARpU5ct7TSNX8B1ePjeWJ"
OPEN_MIN, CLOSE_MIN = 9 * 60 + 30, 16 * 60          # regular session, New York time
# check windows (New York time): a run counts for the first window it falls in; one alert pass per window per day
SLOTS = [("open", 10 * 60, 11 * 60 + 40), ("midday", 13 * 60, 14 * 60 + 40), ("late", 15 * 60 + 15, 16 * 60)]
ALERT_ON = ("TRIGGER", "HEADS-UP")
NAME = {"TRIGGER": "CROWNED", "HEADS-UP": "NEXT IN LINE"}   # names shown in the alerts (Oct 22)


def slot_for(minute: int) -> str | None:
    for name, start, end in SLOTS:
        if start <= minute < end:
            return name
    return None


def load_json(path: str, default):
    try:
        with open(path) as fh:
            return json.load(fh)
    except Exception:  # noqa: BLE001
        return default


def watchlist() -> list[str]:
    """Taylor's Watching + Portfolio tickers from lists.json (Oct 23); falls back to watchlist.txt."""
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "lists.json")) as fh:
            L = json.load(fh)
        out = [str(t).strip().upper() for t in (L.get("watch") or []) + list((L.get("holdings") or {}).keys()) if str(t).strip()]
        if out:
            return list(dict.fromkeys(out))
    except Exception:  # noqa: BLE001
        pass
    try:
        with open(WATCH) as fh:
            return [ln.strip().upper() for ln in fh if ln.strip() and not ln.strip().startswith("#")]
    except FileNotFoundError:
        return []


def ch_idx(dates: list[str], t: str) -> int:
    """Same rule as the page's chIdx: the bar on that date, else the first bar after it, else the last bar."""
    t = str(t)
    for i, d in enumerate(dates):
        if d >= t:
            return i
    return len(dates) - 1


def bottom_line(dates: list[str], ch: dict, i: int) -> float | None:
    """The channel's bottom line at bar i, matching the page's chAt (straight line through a and b, by bar count)."""
    try:
        ia, ib = ch_idx(dates, ch["a"]["t"]), ch_idx(dates, ch["b"]["t"])
        pa, pb = float(ch["a"]["p"]), float(ch["b"]["p"])
    except (KeyError, TypeError, ValueError):
        return None
    if ia == ib:
        return pa
    return pa + (pb - pa) * (i - ia) / (ib - ia)


def channel_breaks(hist: dict, channels: dict, state: dict, today: str, now) -> list[dict]:
    """Stocks that have NEWLY dropped below a channel's bottom line today (once per channel per day)."""
    out = []
    seen = state.setdefault("chan", {})
    for t, chans in channels.items():
        df = hist.get(t)
        if df is None or len(df) < 3 or df.index[-1].strftime("%Y-%m-%d") != today:
            continue
        dates = [d.strftime("%Y-%m-%d") for d in df.index]
        price, prev = float(df["Close"].iloc[-1]), float(df["Close"].iloc[-2])
        for k, ch in enumerate(chans if isinstance(chans, list) else []):
            line, line_prev = bottom_line(dates, ch, len(dates) - 1), bottom_line(dates, ch, len(dates) - 2)
            if not line or line <= 0 or not line_prev:
                continue
            key = f"{t}#{k}"
            status = "below" if price < line else "ok"
            before = seen.get(key) or ("below" if prev < line_prev else "ok")   # yesterday's close is the baseline
            seen[key] = status
            if status == "below" and before != "below":
                out.append({"ticker": t, "kind": "channel", "price": round(price, 2), "line": round(line, 2),
                            "under": round((1 - price / line) * 100, 1), "time": now.strftime("%H:%M"),
                            "currency": "CAD" if t.endswith((".TO", ".V")) else "USD"})
    return out


def notify(title: str, body: str, high: bool = False) -> None:
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    print(f"ALERT {title}: {body}")
    if not topic:
        print("  (no NTFY_TOPIC secret set, so nothing was sent)")
        return
    try:
        r = requests.post(f"https://ntfy.sh/{topic}", data=body.encode("utf-8"), timeout=20,
                          headers={"Title": title.encode("ascii", "ignore").decode(), "Click": PAGE,
                                   "Tags": "chart_with_upwards_trend", "Priority": "high" if high else "default"})
        r.raise_for_status()
    except Exception as e:  # noqa: BLE001
        print("  ntfy failed:", e, file=sys.stderr)


def main() -> None:
    force = "--force" in sys.argv
    now = datetime.now(ET)
    minute = now.hour * 60 + now.minute
    slot = slot_for(minute)
    if not force and (now.weekday() >= 5 or not slot):
        print(f"Outside the check windows ({now:%a %H:%M} ET). Nothing to do.")
        return
    slot = slot or "manual"
    today = now.strftime("%Y-%m-%d")
    state = load_json(STATE, {})
    if state.get("date") != today:
        state = {"date": today, "slots": [], "status": {}, "alerts": []}
    if slot in state["slots"] and not force:
        print(f"The {slot} check already ran today.")
        return

    scan = load_json(SCAN, {})
    cands = {s["ticker"]: s for s in scan.get("stocks", []) if s.get("kind") != "ETF"}
    watch = watchlist()
    tickers = list(dict.fromkeys(list(cands) + watch))
    if not tickers:
        print("No candidates (scan.json missing and watchlist.txt empty).")
        return

    from screener import analyze, rvol_for, get_history

    hist = get_history(tickers)
    channels = (load_json(os.path.join(BASE, "lists.json"), {}).get("channels") or {})
    channels = {str(t).strip().upper(): v for t, v in channels.items() if v}
    extra = [t for t in channels if t not in hist]
    if extra:
        try:
            hist.update(get_history(extra))
        except Exception as e:  # noqa: BLE001
            print("channel history failed:", e, file=sys.stderr)
    pace = min(max((minute - OPEN_MIN) / (CLOSE_MIN - OPEN_MIN), 0.04), 1.0)
    new, checked = [], 0
    for t in tickers:
        df = hist.get(t)
        if df is None or len(df) < 81 or df.index[-1].strftime("%Y-%m-%d") != today:
            continue   # no bar for today yet (holiday, halt, or pre-market)
        checked += 1
        adj = df.copy()
        vcol = adj.columns.get_loc("Volume")
        adj.iloc[-1, vcol] = float(adj.iloc[-1, vcol]) / pace
        try:
            rv = rvol_for((cands.get(t) or {}).get("market_cap", 0))
            sig = analyze(adj, rv)
            before = state["status"].get(t)
            if before is None:                      # first look today: yesterday's close is the baseline
                prev_sig = analyze(df.iloc[:-1], rv)
                before = prev_sig["status"] if prev_sig else "NONE"
        except Exception as e:  # noqa: BLE001
            print(f"  {t}: {e}", file=sys.stderr)
            continue
        status = sig["status"] if sig else "NONE"
        state["status"][t] = status
        if status in ALERT_ON and status != before:
            c = adj["Close"]
            v50 = float(df["Volume"].iloc[-51:-1].mean()) or 1.0
            info = cands.get(t, {})
            new.append({"ticker": t, "name": info.get("name") or t, "status": status, "was": before,
                        "price": round(float(c.iloc[-1]), 2), "chg": round(float((c.iloc[-1] / c.iloc[-2] - 1) * 100), 2),
                        "rvol": round(float(adj["Volume"].iloc[-1]) / v50, 2), "watch": t in watch,
                        "currency": info.get("currency") or ("CAD" if t.endswith((".TO", ".V")) else "USD"),
                        "time": now.strftime("%H:%M")})

    new.sort(key=lambda a: (a["status"] != "TRIGGER", not a["watch"], -a["rvol"]))
    when = now.astimezone(PT).strftime("%-I:%M%p").lower()

    breaks = []
    try:
        breaks = channel_breaks(hist, channels, state, today, now)
    except Exception as e:  # noqa: BLE001
        print("channel check failed:", e, file=sys.stderr)
    if len(breaks) <= 4:
        for b in breaks:
            notify(f"{b['ticker']}: broke below your channel",
                   f"{b['ticker']} at ${b['price']} {b['currency']}, {b['under']}% under the bottom line you drew "
                   f"(about ${b['line']}). The pullback may be starting. As of {when} PT; not final until the close. "
                   f"Not financial advice.", high=True)
    else:
        notify(f"Royal B: {len(breaks)} stocks broke below your channels",
               f"{', '.join(b['ticker'] for b in breaks)} dropped under the bottom line you drew. As of {when} PT; "
               f"not final until the close. Tap to open Royal B. Not financial advice.", high=True)
    if len(new) <= 4:
        for a in new:
            what = "10-day crossed above the 20-day" if a["status"] == "TRIGGER" else "10-day within 1% of the 20-day and closing in"
            notify(f"{a['ticker']}: {NAME.get(a['status'], a['status'])}" + (" (watchlist)" if a["watch"] else ""),
                   f"{a['name']} at ${a['price']} {a['currency']} ({a['chg']:+.1f}% today). {what}; "
                   f"volume on pace for {a['rvol']:.1f}x average. As of {when} PT; not final until the close. Not financial advice.",
                   high=a["status"] == "TRIGGER")
    elif new:
        trig = [a["ticker"] for a in new if a["status"] == "TRIGGER"]
        heads = [a["ticker"] for a in new if a["status"] == "HEADS-UP"]
        notify(f"Royal B: {len(heads)} next in line, {len(trig)} crowned",
               (f"NEXT IN LINE: {', '.join(heads)}. " if heads else "") + (f"CROWNED: {', '.join(trig)}. " if trig else "")
               + f"As of {when} PT; not final until the close. Tap to open Royal B. Not financial advice.",
               high=bool(trig))
    elif force and not breaks:
        notify("Royal B alerts are connected",
               f"Test check at {when} PT: {checked} stocks and {len(channels)} channels checked, nothing new. You'll get alerts "
               f"like this when a stock is NEXT IN LINE for its cross, gets CROWNED, or drops below a channel you drew.")

    state["slots"].append(slot)
    state["alerts"] = (state.get("alerts") or []) + new + breaks
    state["checked_at"] = now.isoformat(timespec="minutes")
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    with open(STATE, "w") as fh:
        json.dump(state, fh, separators=(",", ":"))
    print(f"SUMMARY slot={slot} checked={checked} new={len(new)} channel_breaks={len(breaks)} pace={pace:.2f}")


if __name__ == "__main__":
    main()
