"""
Judgement Day (Taylor, Oct 29-30, 2026): the buy checklist, run every night on GitHub.

INFORMATION ONLY. It never changes crowns, labels, Today, Watch Alerts or any screener. The page shows it
in a pop-up when Taylor presses the Judgement Day button on a stock.

Runs on every stock the page shows: Watching, holdings, long-term/pins, Early Turn, Trend Cross.
No chart section: the screeners already check the trend, the 50/200-day lines and volume.

  Business:     1A Growth · 1B Profitability · 1C Cash flow · 1D Balance sheet · 1E Valuation · 1F Shareholders
  Story & Plan: earnings soon, short interest, analysts · 8% stop, target = analyst mean target
                (else 52-week high), risk-to-reward

Verdict
  SKIP  free cash flow negative, or the balance sheet fails (interest coverage < 2x or debt/equity > 2),
        or the business score is under 50%            ("fail 1C or 1D: skip it, even if the chart looks great")
  WAIT  business score under 70%, or risk-to-reward under 2:1   ("wait for the next pitch")
  PASS  everything else
  NODATA Yahoo gave us too little to judge

Writes nothing itself: github_scan.py puts the result into scan.json under "judgement".
Fundamentals are cached in cache/judgement.json for 4 days (they change quarterly); the price-based parts
(P/E, analyst upside, risk-to-reward) are recomputed every night from that day's close.
"""
from __future__ import annotations

import json
import math
import os
import sys
import time
from datetime import datetime, timedelta, timezone

BASE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(BASE, "cache", "judgement.json")
MAX_AGE = 4 * 24 * 3600
STOP_PCT = 0.08          # our rule: 8% stop
MIN_RR = 2.0
FIN_SECTORS = {"Financial Services", "Real Estate", "Utilities"}   # debt-heavy by design (and pipelines): debt checks are info only


# ------------------------------------------------------------------ helpers
def _num(x):
    try:
        x = float(x)
        return None if math.isnan(x) or math.isinf(x) else x
    except (TypeError, ValueError):
        return None


def _row(df, *names, n=None):
    """Values of the first matching row, newest first, as floats (None where missing)."""
    if df is None or getattr(df, "empty", True):
        return []
    for name in names:
        if name in df.index:
            vals = [_num(v) for v in df.loc[name].tolist()]
            return vals[:n] if n else vals
    return []


def _filled(df):
    """Drop quarters Yahoo has only half filled in (right after a report): keep columns that have revenue."""
    if df is None or getattr(df, "empty", True):
        return df
    for name in ("Total Revenue", "Operating Revenue", "Net Income"):
        if name in df.index:
            return df.loc[:, df.loc[name].notna()]
    return df


def _ttm(vals):
    v = vals[:4]
    return sum(v) if len(v) == 4 and all(x is not None for x in v) else None


def _yoy(vals):
    """Latest quarter vs the same quarter a year earlier (needs 5 quarters)."""
    if len(vals) >= 5 and vals[0] is not None and vals[4] not in (None, 0):
        return (vals[0] / vals[4] - 1) * 100 if vals[4] > 0 else None
    return None


def _r(x, d=1):
    return None if x is None else round(x, d)


# ------------------------------------------------------------------ fetch (slow part, cached)
def fetch(t: str) -> dict:
    import yfinance as yf

    tk = yf.Ticker(t)
    raw: dict = {"at": time.time()}

    def safe(fn, label):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            print(f"  judgement {t} {label}: {str(e)[:80]}", file=sys.stderr)
            return None

    info = safe(lambda: tk.info or {}, "info") or {}
    for k in ("sector", "industry", "trailingPE", "forwardPE", "trailingEps", "forwardEps", "trailingPegRatio",
              "pegRatio", "priceToSalesTrailing12Months", "targetMeanPrice", "numberOfAnalystOpinions",
              "recommendationKey", "heldPercentInsiders", "heldPercentInstitutions", "shortPercentOfFloat",
              "sharesShort", "sharesShortPriorMonth", "dividendYield", "fiftyTwoWeekHigh", "returnOnEquity",
              "currentRatio", "debtToEquity", "totalCash", "totalDebt", "revenueGrowth", "earningsGrowth",
              "freeCashflow", "financialCurrency", "currency"):
        v = info.get(k)
        if v is not None and v != "":
            raw[k] = v if isinstance(v, str) else _num(v)

    q = safe(lambda: tk.quarterly_income_stmt, "income")
    q = _filled(q)
    raw["rev"] = _row(q, "Total Revenue", "Operating Revenue", n=5)
    raw["gp"] = _row(q, "Gross Profit", n=5)
    raw["op"] = _row(q, "Operating Income", "EBIT", n=5)
    raw["ni"] = _row(q, "Net Income", "Net Income Common Stockholders", n=5)
    raw["eps"] = _row(q, "Diluted EPS", "Basic EPS", n=5)
    raw["int"] = _row(q, "Interest Expense", "Interest Expense Non Operating", n=5)
    raw["shares"] = _row(q, "Diluted Average Shares", "Basic Average Shares", n=5)
    a = _filled(safe(lambda: tk.income_stmt, "annual"))
    raw["rev_fy"] = _row(a, "Total Revenue", "Operating Revenue", n=4)
    raw["shares_fy"] = _row(a, "Diluted Average Shares", "Basic Average Shares", n=4)

    cf = safe(lambda: tk.quarterly_cashflow, "cashflow")
    raw["fcf"] = _row(cf, "Free Cash Flow", n=5)
    raw["buyback"] = _row(cf, "Repurchase Of Capital Stock", n=4)
    bs = safe(lambda: tk.quarterly_balance_sheet, "balance")
    raw["cash"] = _row(bs, "Cash Cash Equivalents And Short Term Investments", "Cash And Cash Equivalents", n=1)
    raw["debt"] = _row(bs, "Total Debt", n=1)
    raw["equity"] = _row(bs, "Stockholders Equity", "Common Stock Equity", n=1)
    raw["ca"] = _row(bs, "Current Assets", n=1)
    raw["cl"] = _row(bs, "Current Liabilities", n=1)

    ed = safe(lambda: tk.earnings_dates, "earnings dates")
    if ed is not None and not getattr(ed, "empty", True) and "Surprise(%)" in ed.columns:
        now = datetime.now(timezone.utc)
        past = ed[[i.to_pydatetime() <= now for i in ed.index]]
        raw["surprises"] = [_num(x) for x in past["Surprise(%)"].tolist()[:4]]
        future = [i.to_pydatetime() for i in ed.index if i.to_pydatetime() > now]
        if future:
            raw["next_earn"] = min(future).strftime("%Y-%m-%d")
    tr = safe(lambda: tk.eps_trend, "eps trend")
    if tr is not None and not getattr(tr, "empty", True) and "+1y" in tr.index:
        r = tr.loc["+1y"]
        raw["est_next"] = _num(r.get("current"))
        raw["est_next_30"] = _num(r.get("30daysAgo"))
    ee = safe(lambda: tk.earnings_estimate, "estimates")
    if ee is not None and not getattr(ee, "empty", True) and "0y" in ee.index and "+1y" in ee.index:
        raw["est_this"] = _num(ee.loc["0y"].get("avg"))
        raw["est_next"] = raw.get("est_next") or _num(ee.loc["+1y"].get("avg"))
    it = safe(lambda: tk.insider_transactions, "insiders")
    if it is not None and not getattr(it, "empty", True):
        dcol = "Start Date" if "Start Date" in it.columns else ("Transaction Start Date" if "Transaction Start Date" in it.columns else None)
        cutoff = datetime.now() - timedelta(days=90)
        buys = sells = 0.0
        for _, x in it.iterrows():
            try:
                d = x[dcol].to_pydatetime() if dcol else None
            except Exception:  # noqa: BLE001
                d = None
            if d is None or d.replace(tzinfo=None) < cutoff:
                continue
            txt, val = str(x.get("Text") or "").lower(), _num(x.get("Value")) or 0
            if txt.startswith("sale"):
                sells += val
            elif txt.startswith("purchase") or "buy" in txt:
                buys += val
        raw["ins_buy"], raw["ins_sell"] = buys, sells
    h = safe(lambda: tk.history(period="1y", auto_adjust=False), "history")
    if h is not None and not getattr(h, "empty", True):
        c = h["Close"].dropna()
        raw["close"] = _num(c.iloc[-1])
        raw["hi52"] = _num(h["High"].max())
        raw["sma200"] = _num(c.iloc[-200:].mean()) if len(c) >= 200 else None
    return raw


# ------------------------------------------------------------------ judge (fast part)
def judge(raw: dict, close: float | None = None, earnings_days: int | None = None) -> dict:
    close = _num(close) or _num(raw.get("close"))
    if earnings_days is None and raw.get("next_earn"):
        try:
            nd = datetime.strptime(raw["next_earn"], "%Y-%m-%d").date()
            earnings_days = (nd - datetime.now(timezone.utc).date()).days
        except ValueError:
            pass
    sector = raw.get("sector") or ""
    industry = raw.get("industry") or ""
    fin = sector in FIN_SECTORS or "Midstream" in industry or industry.startswith("Utilities")
    S: dict[str, list] = {k: [] for k in ("growth", "profit", "cash", "balance", "value", "holders", "story", "plan")}

    def add(sec, label, res, detail, scored=True):
        S[sec].append({"label": label, "r": res, "d": detail, **({} if scored else {"info": True})})

    rev, gp, op, ni, eps = raw.get("rev") or [], raw.get("gp") or [], raw.get("op") or [], raw.get("ni") or [], raw.get("eps") or []
    m = lambda x: f"${x/1e9:.2f}B" if x is not None and abs(x) >= 1e9 else (f"${x/1e6:.0f}M" if x is not None else "?")  # noqa: E731

    # 1A growth
    g = _yoy(rev)
    if g is not None:
        add("growth", "Revenue growing", "pass" if g >= 10 else "warn" if g >= 0 else "fail",
            f"{g:+.0f}% vs a year ago ({m(rev[0])} last quarter)" + (" · 20%+ is strong" if g >= 20 else ""))
    rttm, fy = _ttm(rev), (raw.get("rev_fy") or [None])[0]
    if rttm and fy:
        d = (rttm / fy - 1) * 100
        add("growth", "Growth holding up (last 12 months vs last full year)", "pass" if d >= 0 else "warn",
            f"{m(rttm)} vs {m(fy)} ({d:+.0f}%)")
    eg = _yoy(eps)
    if eg is None and len(eps) >= 5 and eps[0] is not None and eps[4] is not None and eps[4] <= 0:
        add("growth", "Earnings per share growing", "pass" if eps[0] > eps[4] else "fail",
            f"{eps[0]:.2f} vs {eps[4]:.2f} a year ago (losses {'shrinking' if eps[0] > eps[4] else 'growing'})")
    elif eg is not None:
        add("growth", "Earnings per share growing", "pass" if eg >= 10 else "warn" if eg >= 0 else "fail",
            f"{eps[0]:.2f} vs {eps[4]:.2f} a year ago ({eg:+.0f}%)")
    et, en = raw.get("est_this"), raw.get("est_next")
    if et is not None and en is not None:
        add("growth", "Next year's EPS estimate above this year's", "pass" if en > et else "fail",
            f"{en:.2f} next year vs {et:.2f} this year")
    sp = [x for x in (raw.get("surprises") or []) if x is not None]
    if sp:
        beats = sum(1 for x in sp if x > 0)
        add("growth", "Beat earnings estimates lately", "pass" if beats >= 3 else "warn" if beats >= 2 else "fail",
            f"beat {beats} of the last {len(sp)} quarters")
    n30 = raw.get("est_next_30")
    if en is not None and n30:
        ch = (en / n30 - 1) * 100
        add("growth", "Analysts raising estimates (last 30 days)", "pass" if ch >= 0 else "warn",
            f"next-year EPS estimate {ch:+.1f}%")

    # 1B profitability
    if len(gp) >= 5 and len(rev) >= 5 and all(x for x in (gp[0], gp[4], rev[0], rev[4])):
        g0, g4 = gp[0] / rev[0] * 100, gp[4] / rev[4] * 100
        add("profit", "Gross margin steady or rising", "pass" if g0 >= g4 - 1 else "warn",
            f"{g0:.1f}% vs {g4:.1f}% a year ago")
    if op and rev and op[0] is not None and rev[0]:
        o0 = op[0] / rev[0] * 100
        o4 = op[4] / rev[4] * 100 if len(op) >= 5 and op[4] is not None and len(rev) >= 5 and rev[4] else None
        res = "fail" if o0 <= 0 else ("pass" if o4 is None or o0 >= o4 - 1 else "warn")
        add("profit", "Operating margin positive and improving", res,
            f"{o0:.1f}%" + (f" vs {o4:.1f}% a year ago" if o4 is not None else ""))
    nttm = _ttm(ni)
    if nttm is not None:
        prev_loss_shrinking = len(ni) >= 5 and ni[0] is not None and ni[4] is not None and ni[0] > ni[4]
        add("profit", "Making a profit", "pass" if nttm > 0 else ("warn" if prev_loss_shrinking else "fail"),
            f"{m(nttm)} over the last 12 months" + ("" if nttm > 0 else (" (losses shrinking)" if prev_loss_shrinking else " (losses)")))
    eq = (raw.get("equity") or [None])[0]
    roe = (nttm / eq * 100) if (nttm is not None and eq and eq > 0) else (_num(raw.get("returnOnEquity")) or 0) * 100 or None
    if roe is not None and eq and eq > 0:
        add("profit", "Return on equity above 15%", "pass" if roe >= 15 else "warn" if roe >= 8 else "fail", f"{roe:.0f}%")

    # 1C cash flow
    fcf = raw.get("fcf") or []
    fttm = _ttm(fcf)
    if fttm is None and raw.get("freeCashflow") is not None:
        fttm = raw["freeCashflow"]
    if fttm is not None:
        add("cash", "Free cash flow positive", "pass" if fttm > 0 else "fail", f"{m(fttm)} over the last 12 months")
        if nttm and nttm > 0:
            r = fttm / nttm
            add("cash", "Profit backed by cash (FCF vs net income)", "pass" if r >= 0.7 else "warn" if r >= 0.4 else "fail",
                f"free cash flow is {r*100:.0f}% of net income")
        if len(fcf) >= 5 and fcf[0] is not None and fcf[4] is not None:
            add("cash", "Free cash flow growing", "pass" if fcf[0] >= fcf[4] else "warn",
                f"{m(fcf[0])} last quarter vs {m(fcf[4])} a year ago")

    # 1D balance sheet
    debt, cash = (raw.get("debt") or [None])[0], (raw.get("cash") or [None])[0]
    if debt is None:
        debt = raw.get("totalDebt")
    if cash is None:
        cash = raw.get("totalCash")
    if debt is not None and eq:
        de = debt / eq if eq > 0 else None
        if de is None:
            add("balance", "Debt-to-equity below 1", "warn", "negative equity (often from big buybacks)", scored=not fin)
        else:
            add("balance", "Debt-to-equity below 1", "pass" if de < 1 else "warn" if de <= 2 else "fail",
                f"{de:.2f}" + (" (normal to run higher in this sector)" if fin else ""), scored=not fin)
    if debt is not None and cash is not None:
        add("balance", "Cash vs debt", "pass" if cash >= debt else "warn",
            f"{m(cash)} cash vs {m(debt)} debt" + (f" (net debt {m(debt-cash)})" if debt > cash else " (more cash than debt)"),
            scored=not fin)
    ca, cl = (raw.get("ca") or [None])[0], (raw.get("cl") or [None])[0]
    cr = ca / cl if ca and cl else raw.get("currentRatio")
    if cr and not fin:
        add("balance", "Can pay the next year's bills (current ratio above 1)", "pass" if cr >= 1 else "warn" if cr >= 0.8 else "fail", f"{cr:.1f}")
    ottm, ittm = _ttm(op), _ttm([abs(x) if x is not None else None for x in (raw.get("int") or [])])
    if ottm is not None:
        ints = raw.get("int") or []
        if ittm is None and any(x for x in ints):
            pass   # Yahoo left gaps in the interest numbers: don't guess
        elif not ittm:
            add("balance", "Interest easily covered", "pass", "little or no interest expense")
        else:
            cov = ottm / ittm
            iq = [abs(x) for x in (raw.get("int") or []) if x is not None]
            covq = op[0] / iq[0] if op and op[0] is not None and iq and iq[0] else None
            if cov <= 0:
                rich = cash is not None and debt is not None and cash >= debt
                add("balance", "Interest easily covered (above 5x)", "warn" if rich else "fail",
                    "operating loss: profits don't cover interest" + (", but it has more cash than debt" if rich else ""), scored=not fin)
            elif cov < 5 and covq is not None and covq >= 5:   # a one-off write-down dragged the 12-month number
                add("balance", "Interest easily covered (above 5x)", "warn",
                    f"{covq:.1f}x last quarter, but {cov:.1f}x over 12 months (a one-off loss in there)", scored=not fin)
            else:
                add("balance", "Interest easily covered (above 5x)", "pass" if cov >= 5 else "warn" if cov >= 2 else "fail",
                    f"operating profit covers interest {cov:.1f}x", scored=not fin)

    # 1E valuation
    epsttm = _ttm(eps) or raw.get("trailingEps")
    pe = close / epsttm if close and epsttm and epsttm > 0 else None
    if pe is not None:
        add("value", "P/E reasonable", "pass" if pe <= 30 else "warn" if pe <= 60 else "fail",
            f"{pe:.1f}" + (" · compare with its sector" if pe > 30 else ""))
    elif epsttm is not None and epsttm <= 0:
        ps = raw.get("priceToSalesTrailing12Months")
        add("value", "Price-to-sales reasonable (no profits yet)", "na" if ps is None else ("pass" if ps <= 8 else "warn" if ps <= 20 else "fail"),
            "no P/E (losses)" + (f" · price/sales {ps:.1f}" if ps else ""))
    fe = raw.get("forwardEps") or en
    fpe = close / fe if close and fe and fe > 0 else None
    if fpe is not None and pe is not None:
        add("value", "Forward P/E below today's P/E", "pass" if fpe < pe else "warn", f"{fpe:.1f} forward vs {pe:.1f} now")
    peg = raw.get("trailingPegRatio") or raw.get("pegRatio")
    if peg is None and pe and et and en and et > 0 and en > et:
        peg = pe / ((en / et - 1) * 100)
    if peg is not None and peg > 0:
        add("value", "PEG below 2 (price vs growth)", "pass" if peg <= 2 else "warn" if peg <= 3 else "fail",
            f"{peg:.2f}" + (" · near 1 is good value" if peg <= 1.2 else ""))
    tgt = raw.get("targetMeanPrice")
    if tgt and close:
        up = (tgt / close - 1) * 100
        add("value", "Analyst target above the price", "pass" if up >= 10 else "warn" if up >= 0 else "fail",
            f"${tgt:.2f} avg target ({up:+.0f}%)" + (f" · {int(raw['numberOfAnalystOpinions'])} analysts" if raw.get("numberOfAnalystOpinions") else ""))

    # 1F shareholders
    sh = raw.get("shares") or []
    if len(sh) >= 5 and sh[0] and sh[4]:
        d = (sh[0] / sh[4] - 1) * 100
        add("holders", "Share count not climbing", "pass" if d <= 1 else "warn" if d <= 5 else "fail",
            f"{d:+.1f}% in a year" + (" (buybacks shrinking it)" if d < -0.5 else " (new shares diluting you)" if d > 1 else ""))
    bb = [x for x in (raw.get("buyback") or []) if x is not None]
    dy = raw.get("dividendYield")
    perks = []
    if dy:
        perks.append(f"{dy:.1f}% dividend")   # yfinance gives dividendYield in percent
    if bb and sum(bb) < 0:
        perks.append(f"{m(-sum(bb))} of buybacks lately")
    add("holders", "Dividends or buybacks (bonus)", "pass" if perks else "na", " · ".join(perks) or "none", scored=False)
    if "ins_sell" in raw:
        b, s = raw.get("ins_buy") or 0, raw.get("ins_sell") or 0
        add("holders", "Insiders not dumping", "pass" if b >= s or s < 2e6 else "warn",
            f"last 90 days: {m(b)} bought, {m(s)} sold" + (" (small, routine)" if 0 < s < 2e6 else ""), scored=False)
    inst = raw.get("heldPercentInstitutions")
    if inst is not None:
        add("holders", "Big institutions own it", "pass" if inst >= 0.4 else "warn", f"{min(inst, 1)*100:.0f}% held by institutions", scored=False)

    # 2 story
    if earnings_days is not None and earnings_days >= 0:
        add("story", "No earnings in the next 2 weeks", "pass" if earnings_days > 14 else "warn" if earnings_days > 7 else "fail",
            f"earnings in {earnings_days} days")
    spf, ss, sp0 = raw.get("shortPercentOfFloat"), raw.get("sharesShort"), raw.get("sharesShortPriorMonth")
    if spf is not None:
        chg = (ss / sp0 - 1) * 100 if ss and sp0 else None
        below200 = bool(close and raw.get("sma200") and close < raw["sma200"])
        caution = chg is not None and chg >= 25 and below200
        txt = f"{spf*100:.1f}% of shares sold short" + (f", {chg:+.0f}% in a month" if chg is not None else "")
        if spf >= 0.10 and not caution:
            txt += " · high: could fuel a squeeze on a breakout"
        if caution:
            txt += " · shorts piling in below the 200-day"
        add("story", "Who's betting against it (short interest)", "fail" if caution else ("warn" if spf >= 0.10 else "pass"), txt)
    rk = raw.get("recommendationKey")
    if rk and rk != "none":
        add("story", "Analysts' rating", "pass" if rk in ("buy", "strong_buy") else "warn" if rk == "hold" else "fail",
            rk.replace("_", " ").title(), scored=False)

    # 4 plan
    target, tsrc = (tgt, "avg analyst target") if tgt and close and tgt > close else (None, None)
    hi = raw.get("fiftyTwoWeekHigh") or raw.get("hi52")
    if target is None and hi and close and hi > close * 1.03:
        target, tsrc = hi, "52-week high"
    plan = None
    if close:
        stop = close * (1 - STOP_PCT)
        if target:
            rr = (target - close) / (close - stop)
            good_entry = target / (1 + MIN_RR * STOP_PCT)       # price where the 8% stop gives 2:1
            plan = {"entry": _r(close, 2), "stop": _r(stop, 2), "target": _r(target, 2), "target_is": tsrc,
                    "rr": _r(rr, 1), "rr_entry": _r(good_entry, 2)}
            add("plan", f"Risk-to-reward at least {MIN_RR:.0f}:1", "pass" if rr >= MIN_RR else "warn" if rr >= 1.5 else "fail",
                f"{rr:.1f}:1 buying at ${close:.2f}, stop ${stop:.2f} (8%), target ${target:.2f} ({tsrc})"
                + ("" if rr >= MIN_RR else f" · reaches 2:1 at ${good_entry:.2f} or lower"))
        else:
            plan = {"entry": _r(close, 2), "stop": _r(stop, 2), "target": None, "rr": None}
            add("plan", f"Risk-to-reward at least {MIN_RR:.0f}:1", "warn", "no target: it's at its high and analysts are below the price")

    # score + verdict
    scored = [c for k in ("growth", "profit", "cash", "balance", "value", "holders") for c in S[k] if not c.get("info") and c["r"] != "na"]
    pts = sum(1 if c["r"] == "pass" else 0.5 if c["r"] == "warn" else 0 for c in scored)
    score = round(pts / len(scored) * 100) if scored else None
    sp_scored = [c for k in ("story", "plan") for c in S[k] if not c.get("info") and c["r"] != "na"]
    sp_pts = sum(1 if c["r"] == "pass" else 0.5 if c["r"] == "warn" else 0 for c in sp_scored)
    sp_score = round(sp_pts / len(sp_scored) * 100) if sp_scored else None
    why = []
    hard = [c for c in S["cash"] + S["balance"] if c["r"] == "fail" and not c.get("info")
            and (c["label"].startswith("Free cash flow positive") or c["label"].startswith("Interest") or c["label"].startswith("Debt"))]
    rr_c = next((c for c in S["plan"]), None)
    story_fail = [c for c in S["story"] if c["r"] == "fail"]
    if len(scored) < 6:
        verdict = "NODATA"
        why.append("Yahoo didn't return enough financials to judge it")
    elif hard:
        verdict = "SKIP"
        why += [f"{c['label']}: {c['d']}" for c in hard]
    elif score < 50:
        verdict = "SKIP"
        why.append(f"business scored {score}%")
    elif score < 70 or (rr_c and rr_c["r"] != "pass") or story_fail:
        verdict = "WAIT"
        if score < 70:
            why.append(f"business scored {score}% (want 70%+)")
        if rr_c and rr_c["r"] != "pass":
            why.append(rr_c["d"])
        why += [f"{c['label']}: {c['d']}" for c in story_fail]
    else:
        verdict = "PASS"
        why.append(f"business scored {score}%, risk-to-reward {plan['rr']}:1" if plan and plan.get("rr") else f"business scored {score}%")
    return {"verdict": verdict, "score": score, "sp_score": sp_score, "why": why, "plan": plan, "sector": sector or None,
            "industry": raw.get("industry"), "sections": S, "checked": len(scored),
            "asof": datetime.fromtimestamp(raw.get("at", time.time()), timezone.utc).strftime("%Y-%m-%d")}


# ------------------------------------------------------------------ batch
def run(tickers: list[str], closes: dict | None = None, earnings: dict | None = None,
        max_fetch: int = 120, budget_s: int = 1500) -> dict:
    """tickers in priority order (Watching first). Fetches at most max_fetch stale ones and stops fetching after
    budget_s seconds; the rest use their cached numbers (or wait for tomorrow night)."""
    closes, earnings = closes or {}, earnings or {}
    try:
        with open(CACHE) as fh:
            cache = json.load(fh)
    except Exception:  # noqa: BLE001
        cache = {}
    t0 = now = time.time()
    fetched, fails, out = 0, 0, {}
    for t in dict.fromkeys(tickers):
        c = cache.get(t)
        if ((not c or now - c.get("at", 0) > MAX_AGE) and fetched < max_fetch and fails < 6
                and time.time() - t0 < budget_s):
            try:
                c = fetch(t)
                cache[t] = c
                fetched += 1
                fails = 0 if c.get("rev") else fails + 1
            except Exception as e:  # noqa: BLE001
                fails += 1
                print(f"  judgement {t}: {str(e)[:80]}", file=sys.stderr)
            time.sleep(0.3)
        if c:
            try:
                out[t] = judge(c, closes.get(t), earnings.get(t))
            except Exception as e:  # noqa: BLE001
                print(f"  judgement {t} judge: {str(e)[:120]}", file=sys.stderr)
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    with open(CACHE + ".tmp", "w") as fh:
        json.dump(cache, fh)
    os.replace(CACHE + ".tmp", CACHE)
    print(f"  judgement: {len(out)} judged ({fetched} fetched from Yahoo)", file=sys.stderr)
    return {"updated": datetime.now(timezone.utc).isoformat(timespec="minutes"), "by": out}


if __name__ == "__main__":
    res = run([a.upper() for a in sys.argv[1:]] or ["NXPI"])
    for t, j in res["by"].items():
        print(f"\n== {t}: {j['verdict']} (business {j['score']}%, story & plan {j['sp_score']}%, {j['checked']} checks) — {'; '.join(j['why'])}")
        for sec, rows in j["sections"].items():
            for c in rows:
                print(f"   [{c['r']:4}] {sec:8} {c['label']}: {c['d']}")
