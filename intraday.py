"""
Royal B Ventures: intraday ENTRY alerts, run by GitHub Actions (.github/workflows/intraday.yml).

Weekdays at 10:00am, 1:00pm and 3:15pm New York time (30 min after the open, mid-day,
and 45 min before the close; 7:00 / 10:00 / 12:15 Pacific in summer), it re-checks the best candidates with
today's prices so far:
  - every stock in the latest daily scan (TRIGGER / HEADS-UP setups + the "setting up" leaders)
  - plus every ticker in watchlist.txt (one per line; edit it on GitHub)
and sends a phone notification (ntfy) only when a stock NEWLY turns TRIGGER or HEADS-UP.
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
    try:
        with open(WATCH) as fh:
            return [ln.strip().upper() for ln in fh if ln.strip() and not ln.strip().startswith("#")]
    except FileNotFoundError:
        return []


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
    cands = {s["ticker"]: s for s in scan.get("stocks", [])}
    watch = watchlist()
    tickers = list(dict.fromkeys(list(cands) + watch))
    if not tickers:
        print("No candidates (scan.json missing and watchlist.txt empty).")
        return

    from screener import analyze, get_history

    hist = get_history(tickers)
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
            sig = analyze(adj)
            before = state["status"].get(t)
            if before is None:                      # first look today: yesterday's close is the baseline
                prev_sig = analyze(df.iloc[:-1])
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
    if len(new) <= 4:
        for a in new:
            what = "10-day crossed above the 20-day" if a["status"] == "TRIGGER" else "10-day within 1% of the 20-day and closing in"
            notify(f"{a['ticker']}: {a['status']}" + (" (watchlist)" if a["watch"] else ""),
                   f"{a['name']} at ${a['price']} {a['currency']} ({a['chg']:+.1f}% today). {what}; "
                   f"volume on pace for {a['rvol']:.1f}x average. As of {when} PT; not final until the close. Not financial advice.",
                   high=a["status"] == "TRIGGER")
    elif new:
        trig = [a["ticker"] for a in new if a["status"] == "TRIGGER"]
        heads = [a["ticker"] for a in new if a["status"] == "HEADS-UP"]
        notify(f"Royal B: {len(trig)} trigger, {len(heads)} heads-up",
               (f"TRIGGER: {', '.join(trig)}. " if trig else "") + (f"HEADS-UP: {', '.join(heads)}. " if heads else "")
               + f"As of {when} PT; not final until the close. Tap to open Royal B. Not financial advice.",
               high=bool(trig))
    elif force:
        notify("Royal B alerts are connected",
               f"Test check at {when} PT: {checked} stocks checked, nothing new. You'll get alerts like this when a stock turns TRIGGER or HEADS-UP.")

    state["slots"].append(slot)
    state["alerts"] = (state.get("alerts") or []) + new
    state["checked_at"] = now.isoformat(timespec="minutes")
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    with open(STATE, "w") as fh:
        json.dump(state, fh, separators=(",", ":"))
    print(f"SUMMARY slot={slot} checked={checked} new={len(new)} pace={pace:.2f}")


if __name__ == "__main__":
    main()
