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
Nov 4: it also pings when a stock with a saved trade plan (lists.json "plans", synced from the page) moves INTO
its buy zone, or drops below its skip line (skip_below price, or the 20/50-day the plan names). Once per stock per day.
Nov 10: GET-OUT alerts on what Taylor owns (swing holdings + long-term). The same lines the page's "Your plan" shows:
the get-out line (the low of a recent big up day, else the rising 21-day EMA, else the 50-day), plus for swing holdings
the 50-day exit (once armed) and the stop. Lines are worked out from the completed daily bars, so they stay fixed all day.
  - open / midday: the price NEWLY drops below a line -> high-priority push
  - late (3:15pm New York): still below -> urgent push, 45 minutes to decide before the close
  - first check of the day: yesterday CLOSED below a line -> urgent push (the plan says get out)

Today's volume is incomplete during the day, so it is scaled to a full-day pace
(volume so far / share of a normal day's volume that has usually traded by now: VOLUME_CURVE, Nov 6). A morning signal can fade by
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


# Nov 6: share of a normal day's volume that has traded by each time (New York), measured from 5-minute bars
# (70 US stocks, last 60 trading days, median). The old straight-line pace overstated volume early and
# understated it in the afternoon (at 3:15pm 72% of the day has traded, not 88%), so afternoon signals were missed.
VOLUME_CURVE = [(0, 0.0), (30, 0.098), (60, 0.172), (90, 0.236), (120, 0.298), (150, 0.354), (180, 0.411),
                (210, 0.462), (240, 0.514), (270, 0.570), (300, 0.626), (330, 0.685), (345, 0.721), (360, 0.761),
                (375, 0.820), (385, 0.870), (390, 1.0)]


def day_fraction(minute: int) -> float:
    """Fraction of a normal day's volume done by this minute (New York time), for scaling today's volume so far."""
    m = minute - OPEN_MIN
    if m >= 390:
        return 1.0
    for (m0, f0), (m1, f1) in zip(VOLUME_CURVE, VOLUME_CURVE[1:]):
        if m <= m1:
            return max(f0 + (f1 - f0) * (max(m, m0) - m0) / (m1 - m0), 0.04)
    return 1.0


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


def plan_status(df, plan: dict) -> tuple[str, str]:
    """'zone' (inside a buy zone), 'skip' (below the plan's skip price or moving average) or 'out', and a short why."""
    c = df["Close"]
    price = float(c.iloc[-1])
    if plan.get("skip_below") is not None and price < float(plan["skip_below"]):
        return "skip", f"below {float(plan['skip_below']):g}"
    ma = str(plan.get("skip_ma") or "")
    if ma.startswith("sma") and ma[3:].isdigit():
        n = int(ma[3:])
        if len(c) >= n:
            sma = float(c.iloc[-n:].mean())
            if price < sma:
                return "skip", f"below the {n}-day (~{sma:.2f})"
    for z in plan.get("zones") or []:
        try:
            if float(z["lo"]) <= price <= float(z["hi"]):
                return "zone", str(z.get("label") or f"{z['lo']}-{z['hi']}")
        except (KeyError, TypeError, ValueError):
            continue
    return "out", ""


def plan_alerts(hist: dict, plans: dict, held: set, earn: dict, state: dict, today: str, now) -> list[dict]:
    """Saved trade plans that NEWLY moved into a buy zone or below their skip line today (yesterday's close = baseline)."""
    out, seen = [], state.setdefault("plan", {})
    for t, plan in plans.items():
        if t in held or not isinstance(plan, dict) or (plan.get("until") and str(plan["until"]) < today):
            continue
        df = hist.get(t)
        if df is None or len(df) < 3 or df.index[-1].strftime("%Y-%m-%d") != today:
            continue
        status, why = plan_status(df, plan)
        before = seen.get(t) or plan_status(df.iloc[:-1], plan)[0]
        seen[t] = status
        if status != before and status in ("zone", "skip"):
            out.append({"ticker": t, "kind": "plan", "status": status, "why": why, "earn": earn.get(t),
                        "price": round(float(df["Close"].iloc[-1]), 2), "time": now.strftime("%H:%M"),
                        "currency": "CAD" if t.endswith((".TO", ".V")) else "USD"})
    return out


def _ema21(cl: list[float]) -> list[float | None]:
    """21-day EMA seeded with the simple average of the first 21 closes (same as the page's levelsOf)."""
    out, e, sm, k = [], None, 0.0, 2 / 22
    for i, x in enumerate(cl):
        if i < 21:
            sm += x
            e = sm / 21 if i == 20 else None
        else:
            e = x * k + e * (1 - k)
        out.append(e)
    return out


def get_out_line(df) -> tuple[float, str] | None:
    """The page's support line (levelsOf) from completed daily bars: low of a 4%+ day on 1.5x volume in the last 10 bars,
    else a rising 21-day EMA under the price, else the 50-day under the price."""
    n = len(df)
    if n < 60:
        return None
    cl = [float(x) for x in df["Close"]]
    lo = [float(x) for x in df["Low"]]
    vol = [float(x or 0) for x in df["Volume"]]
    close = cl[-1]
    av = vol[max(0, n - 51):n - 1]
    avg_v = sum(av) / len(av) if av else 0
    for i in range(n - 1, max(1, n - 10) - 1, -1):
        if cl[i] / cl[i - 1] - 1 >= 0.04 and avg_v and vol[i] >= 1.5 * avg_v and lo[i] < close:
            return lo[i], f"the low of the {df.index[i]:%b %-d} jump"
    e = _ema21(cl)
    if e[-1] and e[-6] and e[-1] > e[-6] and e[-1] < close:
        return e[-1], "the rising 21-day EMA"
    s50 = sum(cl[-50:]) / 50
    if s50 < close:
        return s50, "the 50-day"
    return None


def exit_lines(df, kind: str, pos: dict, support_df=None) -> list[tuple[float, str]]:
    """Every line under an owned stock: get-out line, and for swing holdings the armed 50-day exit and the stop.
    support_df: bars to build the get-out line from (default df); the 50-day always uses df, so a close is judged
    against that same day's 50-day, like the page."""
    out = []
    g = get_out_line(df if support_df is None else support_df)
    if g:
        out.append((round(g[0], 2), f"get-out line ({g[1]})"))
    if kind == "swing" and len(df) >= 50:
        c = df["Close"]
        s50 = c.rolling(50).mean()
        since = str(pos.get("date") or "")
        armed = bool(((c > s50) & (df.index.strftime("%Y-%m-%d") >= since)).any())
        if armed:
            out.append((round(float(s50.iloc[-1]), 2), "50-day exit"))
        try:
            if float(pos.get("stop") or 0) > 0:
                out.append((round(float(pos["stop"]), 2), "your stop"))
        except (TypeError, ValueError):
            pass
    return out


def owned_alerts(hist: dict, lists: dict, state: dict, today: str, now, slot: str) -> list[dict]:
    """Nov 10: get-out alerts for stocks Taylor owns. See the module notes for when each one fires."""
    owned = [(str(t).upper(), "swing", v if isinstance(v, dict) else {}) for t, v in (lists.get("holdings") or {}).items()]
    owned += [(str(t).upper(), "lt", v if isinstance(v, dict) else {}) for t, v in (lists.get("longterm") or {}).items()
              if str(t).upper() not in {o[0] for o in owned}]
    out, seen = [], state.setdefault("own", {})
    for t, kind, pos in owned:
        df = hist.get(t)
        if df is None or len(df) < 62 or df.index[-1].strftime("%Y-%m-%d") != today:
            continue
        done = df.iloc[:-1]                         # completed bars: the lines are fixed for the day
        me = seen.setdefault(t, {})
        cur = "CAD" if t.endswith((".TO", ".V")) else "USD"
        # yesterday's close vs the lines as they stood the day before (once per day)
        if not me.get("closed_checked"):
            me["closed_checked"] = True
            yc = float(done["Close"].iloc[-1])
            hit = [L for L in exit_lines(done, kind, pos, support_df=done.iloc[:-1]) if yc < L[0]]
            if hit:
                top = max(hit)
                out.append({"ticker": t, "kind": "own", "level": "closed", "price": round(yc, 2), "line": top[0],
                            "what": top[1], "all": [h[1] for h in hit], "currency": cur, "own": kind, "time": now.strftime("%H:%M")})
        price = float(df["Close"].iloc[-1])
        lines = exit_lines(done, kind, pos)
        below = [L for L in lines if price < L[0]]
        st = "below" if below else "ok"
        prev = me.get("st", "ok")
        me["st"] = st
        if st == "below" and (prev != "below" or (slot == "late" and not me.get("late"))):
            if slot == "late":
                me["late"] = True
            top = max(below)
            out.append({"ticker": t, "kind": "own", "level": "late" if slot == "late" else "now", "price": round(price, 2),
                        "line": top[0], "what": top[1], "all": [b[1] for b in below], "currency": cur, "own": kind,
                        "time": now.strftime("%H:%M")})
    return out


def notify(title: str, body: str, high: bool = False, urgent: bool = False) -> None:
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    print(f"ALERT {title}: {body}")
    if not topic:
        print("  (no NTFY_TOPIC secret set, so nothing was sent)")
        return
    try:
        r = requests.post(f"https://ntfy.sh/{topic}", data=body.encode("utf-8"), timeout=20,
                          headers={"Title": title.encode("ascii", "ignore").decode(), "Click": PAGE,
                                   "Tags": "warning" if urgent else "chart_with_upwards_trend",
                                   "Priority": "urgent" if urgent else "high" if high else "default"})
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
    # Nov 6: market caps for Watching / Portfolio stocks that aren't in today's screen (data.json), so big companies
    # use the 1.2x volume rule here too instead of 1.5x
    caps = {s["ticker"]: s.get("market_cap") for s in (lambda d: d.get("stocks", []) + d.get("holdings", []))(
        load_json(os.path.join(BASE, "site", "data.json"), {})) if s.get("market_cap")}
    watch = watchlist()
    _L0 = load_json(os.path.join(BASE, "lists.json"), {})
    owned_t = [str(t).upper() for t in list((_L0.get("holdings") or {})) + list((_L0.get("longterm") or {}))]
    tickers = list(dict.fromkeys(list(cands) + watch + owned_t))
    if not tickers:
        print("No candidates (scan.json missing and watchlist.txt empty).")
        return

    from screener import analyze, rvol_for, get_history

    hist = get_history(tickers)
    channels = (load_json(os.path.join(BASE, "lists.json"), {}).get("channels") or {})
    channels = {str(t).strip().upper(): v for t, v in channels.items() if v}
    lists = load_json(os.path.join(BASE, "lists.json"), {})
    plans = {str(t).strip().upper(): v for t, v in (lists.get("plans") or {}).items() if v}
    held = {str(t).strip().upper() for t in (lists.get("holdings") or {})}
    extra = [t for t in list(channels) + list(plans) if t not in hist]
    if extra:
        try:
            hist.update(get_history(extra))
        except Exception as e:  # noqa: BLE001
            print("channel history failed:", e, file=sys.stderr)
    pace = day_fraction(minute)
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
            rv = rvol_for((cands.get(t) or {}).get("market_cap") or caps.get(t) or 0)
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
    plan_hits = []
    try:
        earn = {}
        for s in scan.get("stocks", []) + scan.get("early", []):
            e = s.get("earnings") or {}
            if isinstance(e.get("days"), int):
                earn.setdefault(s["ticker"], e["days"])
        plan_hits = plan_alerts(hist, plans, held, earn, state, today, now)
    except Exception as e:  # noqa: BLE001
        print("plan check failed:", e, file=sys.stderr)
    own_hits = []
    try:
        own_hits = owned_alerts(hist, lists, state, today, now, slot)
    except Exception as e:  # noqa: BLE001
        print("owned check failed:", e, file=sys.stderr)
    for a in own_hits:
        also = f" Also under: {', '.join(x for x in a['all'] if x != a['what'])}." if len(a["all"]) > 1 else ""
        if a["level"] == "closed":
            notify(f"GET OUT? {a['ticker']} closed below your line",
                   f"{a['ticker']} closed at ${a['price']} {a['currency']} yesterday, under its {a['what']} (${a['line']}).{also} "
                   f"Your plan says get out; buy back in on a close back above the line plus a green day over the prior high. "
                   f"Check the chart before the open settles. Not financial advice.", urgent=True)
        elif a["level"] == "late":
            notify(f"{a['ticker']}: still below your get-out line, 45 min left",
                   f"{a['ticker']} at ${a['price']} {a['currency']}, under its {a['what']} (${a['line']}).{also} "
                   f"If it closes there, your plan says get out. Decide before the close (1pm PT). As of {when} PT. Not financial advice.",
                   urgent=True)
        else:
            notify(f"{a['ticker']}: below your get-out line",
                   f"{a['ticker']} at ${a['price']} {a['currency']}, under its {a['what']} (${a['line']}).{also} "
                   f"Not final until the close: watch it into the last hour. As of {when} PT. Not financial advice.", high=True)
    for a in plan_hits:
        er = a["earn"]
        er_txt = f" Earnings in {er} days: a gap could jump your stop." if isinstance(er, int) and 0 <= er <= 7 else ""
        if a["status"] == "zone":
            notify(f"{a['ticker']}: in your buy zone",
                   f"{a['ticker']} at ${a['price']} {a['currency']}: inside your plan's zone ({a['why']}).{er_txt} "
                   f"Let it settle 15-30 min, then size it with Trade on the page. As of {when} PT. Not financial advice.",
                   high=not er_txt)
        else:
            notify(f"{a['ticker']}: below your skip line",
                   f"{a['ticker']} at ${a['price']} {a['currency']}: {a['why']}. Your plan says skip if it closes there. "
                   f"As of {when} PT; not final until the close. Not financial advice.")

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
    if new and len(new) <= 4:
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
    elif force and not breaks and not plan_hits and not own_hits:
        notify("Royal B alerts are connected",
               f"Test check at {when} PT: {checked} stocks, {len(channels)} channels and {len(plans)} trade plans checked, nothing new. You'll get alerts "
               f"like this when a stock is NEXT IN LINE for its cross, gets CROWNED, drops below a channel you drew, "
               f"or moves into a trade plan's buy zone.")

    state["slots"].append(slot)
    state["alerts"] = (state.get("alerts") or []) + new + breaks + plan_hits + own_hits
    state["checked_at"] = now.isoformat(timespec="minutes")
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    with open(STATE, "w") as fh:
        json.dump(state, fh, separators=(",", ":"))
    print(f"SUMMARY slot={slot} checked={checked} new={len(new)} channel_breaks={len(breaks)} plans={len(plan_hits)} owned={len(own_hits)} pace={pace:.2f}")


if __name__ == "__main__":
    main()
