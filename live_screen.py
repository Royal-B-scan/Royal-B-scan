"""
Royal B Ventures: LIVE SCREEN, stage 1 (Nov 12, 2026). TRIAL, LOG ONLY.

Re-runs Trend Cross and Early Turn on the whole US market every 10 minutes while the market is open, using one
"whole market" price snapshot from Massive (formerly Polygon.io; Stocks Starter plan, 15-minute delayed).

It sends NO alerts and changes NOTHING the page, the daily screen or the three phone-alert checks use.
It only writes two files, so intraday signals can be compared with where they stood at the close:
  site/live.json        the latest check: every stock with a signal now, what it was at yesterday's close, prices
  site/live_log.jsonl   one line per check (the signals at that moment), for the end-of-day report

How a check works
  1. One call returns today's bar so far (open, high, low, last, volume) for every US stock.
  2. That bar is added to the saved daily history (cache/history.pkl, the same file the daily screen keeps),
     replacing any bar already there for today.
  3. Today's volume is scaled to a full-day pace with intraday.py's VOLUME_CURVE, at the time the prices are FROM
     (now minus the 15-minute delay), exactly as the phone-alert checks do.
  4. screener.analyze (Trend Cross) and earlyentry.signals (Early Turn) run unchanged on the result.
Canadian stocks are not in the snapshot, so they are left to the daily screen.

The rules were tested on closing prices. A signal seen at 11am can be gone by the close; that is what this trial
measures. All market timing is New York time (ET).

  python live_screen.py --loop      run until the close has been checked (start it by hand; see live.yml)
  python live_screen.py             one check now
  python live_screen.py --report    today's intraday signals and whether each one held at the close
  python live_screen.py --snapshot-file snap.json [--at HH:MM]    one check from a saved snapshot (testing)

Needs the secret MASSIVE_API_KEY. Optional: LIVE_DELAY_MIN (default 15), LIVE_EVERY_MIN (default 10).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import requests

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
os.chdir(BASE)
SITE = os.path.join(BASE, "site")
LIVE = os.path.join(SITE, "live.json")
LOG = os.path.join(SITE, "live_log.jsonl")
ET = ZoneInfo("America/New_York")
SNAP_URL = "https://api.massive.com/v2/snapshot/locale/us/markets/stocks/tickers"
DELAY_MIN = int(os.environ.get("LIVE_DELAY_MIN") or 15)      # how old the plan's prices are
EVERY_MIN = int(os.environ.get("LIVE_EVERY_MIN") or 10)
OPEN_MIN, CLOSE_MIN = 9 * 60 + 30, 16 * 60
MAX_HOURS = 5.75                                            # a GitHub job may run 6 hours at most
COLS = ["Open", "High", "Low", "Close", "Volume"]
TC_NEW = ("TRIGGER", "HEADS-UP")                            # Trend Cross statuses that count as a new intraday signal
EE_NEW = ("BREAKOUT", "PULLBACK", "SQUEEZE")


# ---------------------------------------------------------------- the snapshot
def fetch_snapshot(key: str) -> list[dict]:
    """Every US stock's bar for today so far, in one call. The key goes in a header, never in the address."""
    last = None
    for attempt in range(4):
        try:
            r = requests.get(SNAP_URL, headers={"Authorization": f"Bearer {key}"}, timeout=90)
            if r.status_code in (401, 403):
                raise SystemExit(f"Massive refused the key (HTTP {r.status_code}). The whole-market snapshot needs "
                                 f"the Stocks Starter plan or higher, and the secret MASSIVE_API_KEY.")
            r.raise_for_status()
            return r.json().get("tickers") or []
        except SystemExit:
            raise
        except Exception as e:  # noqa: BLE001
            last = e
            print(f"  snapshot retry {attempt + 1}: {e}", file=sys.stderr)
            time.sleep(5 + attempt * 10)
    raise RuntimeError(f"Massive did not return the snapshot: {last}")


def snapshot_key(ticker: str) -> str | None:
    """Yahoo ticker -> the snapshot's ticker. Canadian listings are not in it. Share classes: BRK-B -> BRK.B."""
    if ticker.endswith((".TO", ".V", ".NE", ".CN")):
        return None
    return ticker.replace("-", ".")


def todays_bars(snapshot: list[dict], today: str) -> dict[str, dict]:
    """{snapshot ticker: {"o","h","l","c","v"}} for stocks that have traded today."""
    out = {}
    for x in snapshot:
        d = x.get("day") or {}
        try:
            o, h, l, c, v = (float(d.get(k) or 0) for k in ("o", "h", "l", "c", "v"))
        except (TypeError, ValueError):
            continue
        if c <= 0 or v <= 0 or h <= 0 or l <= 0:
            continue
        ts = x.get("updated")
        if ts:   # nanoseconds; skip a bar left over from another day
            try:
                if datetime.fromtimestamp(int(ts) / 1e9, ET).strftime("%Y-%m-%d") != today:
                    continue
            except (TypeError, ValueError, OverflowError, OSError):
                pass
        out[str(x.get("ticker") or "")] = {"o": o or c, "h": h, "l": l, "c": c, "v": v}
    return out


# ---------------------------------------------------------------- history + today's bar
def completed(df: pd.DataFrame, today: str) -> pd.DataFrame:
    """The saved daily bars before today (the cache may already hold a part-day bar for today)."""
    return df[df.index.strftime("%Y-%m-%d") < today][COLS]


def with_today(done: pd.DataFrame, bar: dict, today: str, pace: float) -> pd.DataFrame:
    """Completed bars + today's bar so far, with today's volume scaled to a full-day pace."""
    stamp = pd.Timestamp(today)
    if done.index.tz is not None:
        stamp = stamp.tz_localize(done.index.tz)
    row = pd.DataFrame([[bar["o"], bar["h"], bar["l"], bar["c"], bar["v"] / max(pace, 0.04)]],
                       index=pd.DatetimeIndex([stamp], name=done.index.name), columns=COLS)
    return pd.concat([done, row])


def load_inputs() -> tuple[dict, dict]:
    """(history, meta). History is the daily screen's own saved file; it is only downloaded when that file is missing."""
    import scan

    uni = scan.get_universe(lambda *a: None)
    meta = uni.set_index("ticker").to_dict("index")
    hist = scan._load_cache()
    if len(hist) < 500:
        print("No saved price history here, downloading a year for every stock (slow, once)", flush=True)
        hist = scan.update_history(uni["ticker"].tolist())
    return {t: hist[t] for t in meta if t in hist}, meta


# ---------------------------------------------------------------- one check
def baseline(hist: dict, meta: dict, today: str) -> dict:
    """Where every stock stood at the last close: {ticker: {"done", "tc", "ee", "cap"}}. Worked out once per run."""
    import earlyentry
    import scan
    from screener import CONFIG, analyze, rvol_for

    base = {}
    for t, df in hist.items():
        if snapshot_key(t) is None:
            continue
        done = completed(df, today)
        if len(done) < 80:
            continue
        m = meta.get(t, {})
        dollar_vol = float(done["Close"].iloc[-1] * done["Volume"].iloc[-50:].mean())
        if dollar_vol < scan._floor(m.get("kind"), m.get("currency")) or done["Close"].iloc[-1] <= CONFIG["min_price"]:
            continue
        cap = m.get("market_cap") or 0
        early = m.get("kind") != "ETF" and cap >= earlyentry.MIN_CAP
        try:
            tc = analyze(done, rvol_for(cap))
            ee = earlyentry.signals(done) if early else None
        except Exception:  # noqa: BLE001
            continue
        base[t] = {"done": done, "cap": cap, "early": early,
                   "tc": tc["status"] if tc else "NONE", "ee": ee["status"] if ee else "NONE"}
    return base


def check(base: dict, meta: dict, bars: dict, today: str, data_minute: int) -> dict:
    """Run both screeners on history + today's bar. Returns the live.json body."""
    import earlyentry
    from intraday import day_fraction
    from screener import analyze, rvol_for

    pace = 1.0 if data_minute >= CLOSE_MIN else day_fraction(data_minute)
    signals, prices, covered = [], {}, 0
    for t, b in base.items():
        bar = bars.get(snapshot_key(t))
        if not bar:
            continue
        covered += 1
        done = b["done"]
        prev = float(done["Close"].iloc[-1])
        prices[t] = [round(bar["c"], 2), round((bar["c"] / prev - 1) * 100, 2)]
        adj = with_today(done, bar, today, pace)
        try:
            tc = analyze(adj, rvol_for(b["cap"]))
            ee = earlyentry.signals(adj) if b["early"] else None
        except Exception as e:  # noqa: BLE001
            print(f"  {t}: {e}", file=sys.stderr)
            continue
        for screener, sig, was, alert_on in (("Trend Cross", tc, b["tc"], TC_NEW), ("Early Turn", ee, b["ee"], EE_NEW)):
            status = sig["status"] if sig else "NONE"
            if status == "NONE" and was == "NONE":
                continue
            m = meta.get(t, {})
            signals.append({"ticker": t, "name": m.get("name") or t, "screener": screener, "status": status, "was": was,
                            "new": status in alert_on and status != was,
                            "price": prices[t][0], "chg": prices[t][1],
                            "rvol": (sig or {}).get("rvol"), "market_cap": b["cap"]})
    new = [s for s in signals if s["new"]]
    return {
        "trial": "log only: no alerts, not shown on the page",
        "date": today,
        "data_time": f"{data_minute // 60:02d}:{data_minute % 60:02d}",   # ET, the time the prices are from
        "delay_min": DELAY_MIN,
        "pace": round(pace, 3),
        "final": data_minute >= CLOSE_MIN,
        "counts": {"screened": len(base), "with_price": covered, "signals": len(signals), "new": len(new),
                   "new_trend_cross": sum(1 for s in new if s["screener"] == "Trend Cross"),
                   "new_early_turn": sum(1 for s in new if s["screener"] == "Early Turn")},
        "signals": sorted(signals, key=lambda s: (not s["new"], s["screener"], s["ticker"])),
        "prices": prices,
    }


def save(out: dict) -> None:
    os.makedirs(SITE, exist_ok=True)
    out["updated"] = datetime.now(ET).isoformat(timespec="minutes")
    with open(LIVE + ".tmp", "w") as fh:
        json.dump(out, fh, separators=(",", ":"))
    os.replace(LIVE + ".tmp", LIVE)
    line = {"date": out["date"], "t": out["data_time"], "final": out["final"], "pace": out["pace"],
            "with_price": out["counts"]["with_price"],
            "sig": {f"{s['screener']}|{s['ticker']}": [s["status"], s["was"], s["price"]] for s in out["signals"]}}
    with open(LOG, "a") as fh:
        fh.write(json.dumps(line, separators=(",", ":")) + "\n")
    c = out["counts"]
    print(f"CHECK prices from {out['data_time']} ET · {c['with_price']}/{c['screened']} stocks priced · "
          f"{c['new_trend_cross']} new Trend Cross · {c['new_early_turn']} new Early Turn · pace {out['pace']:.2f}"
          + (" · FINAL (the close)" if out["final"] else ""), flush=True)


# ---------------------------------------------------------------- report
def report(day: str | None = None) -> dict:
    """Today's new intraday signals, when each first showed, and whether it still stood at the close."""
    try:
        with open(LOG) as fh:
            lines = [json.loads(ln) for ln in fh if ln.strip()]
    except FileNotFoundError:
        print("No live_log.jsonl yet: the live screen has not run.")
        return {}
    day = day or (lines[-1]["date"] if lines else None)
    lines = [ln for ln in lines if ln["date"] == day]
    if not lines:
        print(f"No checks logged for {day}.")
        return {}
    last = lines[-1]
    alert_on = {"Trend Cross": TC_NEW, "Early Turn": EE_NEW}
    first = {}
    for ln in lines:
        for key, (status, was, price) in ln["sig"].items():
            if status in alert_on[key.split("|")[0]] and status != was and (key, status) not in first:
                first[(key, status)] = (ln["t"], price)
    rows = []
    for (key, status), (when, price) in sorted(first.items(), key=lambda kv: kv[1][0]):
        screener, ticker = key.split("|")
        end = (last["sig"].get(key) or ["NONE", None, None])
        rows.append({"screener": screener, "ticker": ticker, "status": status, "first": when, "price": price,
                     "at_close": end[0], "held": end[0] == status, "close": end[2]})
    print(f"Live screen trial, {day}: {len(lines)} checks from {lines[0]['t']} to {last['t']} ET")
    if not last.get("final"):
        print("The close has not been checked yet, so 'held' below is only as of the last check.")
    for screener in ("Trend Cross", "Early Turn"):
        mine = [r for r in rows if r["screener"] == screener]
        held = sum(1 for r in mine if r["held"])
        print(f"\n{screener}: {len(mine)} new intraday signals, {held} still standing at the "
              f"{'close' if last.get('final') else 'last check'}" + (f" ({held / len(mine):.0%})" if mine else ""))
        for r in mine:
            print(f"  {r['first']}  {r['ticker']:<7} {r['status']:<9} at {r['price']}  ->  "
                  f"{'held' if r['held'] else 'gone (' + r['at_close'] + ')'}" + (f", {r['close']}" if r["close"] else ""))
    return {"date": day, "checks": len(lines), "final": bool(last.get("final")), "rows": rows}


# ---------------------------------------------------------------- running it
def data_minute_now(now: datetime) -> int:
    return now.hour * 60 + now.minute - DELAY_MIN


def run_once(base, meta, today, key, snap_file=None, at=None) -> dict:
    now = datetime.now(ET)
    if snap_file:
        with open(snap_file) as fh:
            snap = json.load(fh)
        snap = snap.get("tickers") if isinstance(snap, dict) else snap
    else:
        snap = fetch_snapshot(key)
    minute = at if at is not None else min(data_minute_now(now), CLOSE_MIN)
    out = check(base, meta, todays_bars(snap, today), today, minute)
    save(out)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Royal B live screen (trial, log only)")
    ap.add_argument("--loop", action="store_true")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--snapshot-file")
    ap.add_argument("--at", help="HH:MM (ET) the snapshot file's prices are from")
    ap.add_argument("--date", help="YYYY-MM-DD the snapshot file is for (default: today, ET)")
    a = ap.parse_args()
    if a.report:
        report(a.date)
        return 0
    key = (os.environ.get("MASSIVE_API_KEY") or "").strip()
    if not key and not a.snapshot_file:
        print("No MASSIVE_API_KEY set, so there is nothing to fetch. Add it as a GitHub secret (Settings > Secrets and "
              "variables > Actions), or pass --snapshot-file for a test.", file=sys.stderr)
        return 2
    now = datetime.now(ET)
    today = a.date or now.strftime("%Y-%m-%d")
    if a.loop and now.weekday() >= 5:
        print("Weekend: the market is closed.")
        return 0
    t0 = time.time()
    hist, meta = load_inputs()
    base = baseline(hist, meta, today)
    newest = max((b["done"].index[-1] for b in base.values()), default=None)
    print(f"Ready: {len(base)} US stocks, saved history up to {newest:%Y-%m-%d} "
          f"({round(time.time() - t0)}s to load)" if newest is not None else "No usable price history.", flush=True)
    if newest is None:
        return 1
    if (pd.Timestamp(today) - newest.tz_localize(None)).days > 4:
        print(f"WARNING: the saved history stops at {newest:%Y-%m-%d}. The daily screen has not run recently, so "
              f"today's results will be off until it does.", file=sys.stderr)
    if not a.loop:
        at = None
        if a.at:
            hh, mm = a.at.split(":")
            at = int(hh) * 60 + int(mm)
        run_once(base, meta, today, key, a.snapshot_file, at)
        return 0

    empty = 0
    while True:
        now = datetime.now(ET)
        minute = data_minute_now(now)
        if minute < OPEN_MIN + 10:                         # prices from before 9:40am ET are too thin to screen
            wait = (OPEN_MIN + 10 - minute) * 60
            if wait > MAX_HOURS * 3600:
                print("Started too early; start it again after 9:30am ET.")
                return 0
            print(f"Waiting {round(wait / 60)} min for the first prices", flush=True)
            time.sleep(wait)
            continue
        try:
            out = run_once(base, meta, today, key)
            empty = empty + 1 if out["counts"]["with_price"] == 0 else 0
        except Exception as e:  # noqa: BLE001
            print(f"CHECK FAILED: {e}", file=sys.stderr, flush=True)
            out = {"final": False}
        if out.get("final"):
            print("The close has been checked. Done for today.")
            report(today)
            return 0
        if empty >= 3:
            print("No stock has traded today (a market holiday?). Stopping.")
            return 0
        if time.time() - t0 > MAX_HOURS * 3600:
            print("Stopping before GitHub's 6-hour limit. Start it again to cover the rest of the day.")
            report(today)
            return 0
        nxt = (now + timedelta(minutes=EVERY_MIN)).replace(second=0, microsecond=0)
        nxt -= timedelta(minutes=nxt.minute % EVERY_MIN)
        close_check = now.replace(hour=16, minute=DELAY_MIN + 2, second=0, microsecond=0)   # first moment the close is in
        if now < close_check < nxt:
            nxt = close_check
        time.sleep(max((nxt - datetime.now(ET)).total_seconds(), 5))


if __name__ == "__main__":
    sys.exit(main())
