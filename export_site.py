"""
Build site/data.json for the screener website.

python export_site.py MCD SBUX NVDA      -> chart data + rule checks for these tickers
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

import pandas as pd

from screener import CONFIG, analyze, get_history

SITE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "site")


def rule_checks(df: pd.DataFrame) -> list[dict]:
    """Plain-language pass/fail breakdown of every Rules v1 condition."""
    c, h, l, v = df["Close"], df["High"], df["Low"], df["Volume"]
    f, m, s = (c.rolling(CONFIG[k]).mean() for k in ("fast_ma", "mid_ma", "slow_ma"))
    v50, v5 = v.rolling(50).mean(), v.rolling(5).mean()
    n = CONFIG["channel_lookback"]
    gap = (f.iloc[-1] - m.iloc[-1]) / m.iloc[-1] * 100
    gap_prev = (f.iloc[-2] - m.iloc[-2]) / m.iloc[-2] * 100
    rvol = v.iloc[-1] / v50.iloc[-1]
    hh_now, hh_prev = h.iloc[-n:].max(), h.iloc[-2 * n:-n].max()
    hl_now, hl_prev = l.iloc[-n:].min(), l.iloc[-2 * n:-n].min()
    return [
        {"group": "Upward channel", "label": "Price above 50-day average",
         "pass": bool(c.iloc[-1] > s.iloc[-1]),
         "detail": f"{c.iloc[-1]:.2f} vs {s.iloc[-1]:.2f}"},
        {"group": "Upward channel", "label": "50-day average rising (vs 10 days ago)",
         "pass": bool(s.iloc[-1] > s.iloc[-11]),
         "detail": f"{s.iloc[-1]:.2f} vs {s.iloc[-11]:.2f}"},
        {"group": "Upward channel", "label": "Higher highs (last 20 days vs prior 20)",
         "pass": bool(hh_now > hh_prev), "detail": f"{hh_now:.2f} vs {hh_prev:.2f}"},
        {"group": "Upward channel", "label": "Higher lows (last 20 days vs prior 20)",
         "pass": bool(hl_now > hl_prev), "detail": f"{hl_now:.2f} vs {hl_prev:.2f}"},
        {"group": "MA cross", "label": "10-day above 20-day",
         "pass": bool(gap > 0), "detail": f"gap {gap:+.2f}% (yesterday {gap_prev:+.2f}%)"},
        {"group": "MA cross", "label": "10-day moving toward / away from 20-day",
         "pass": bool(gap > gap_prev),
         "detail": "converging up" if gap > gap_prev else "moving down"},
        {"group": "Volume", "label": f"Volume ≥ {CONFIG['rvol_trigger']}× 50-day average",
         "pass": bool(rvol >= CONFIG["rvol_trigger"]), "detail": f"{rvol:.2f}×"},
        {"group": "Volume", "label": "5-day average volume rising",
         "pass": bool(v5.iloc[-1] > v5.iloc[-6]),
         "detail": f"{v5.iloc[-1] / 1e6:.1f}M vs {v5.iloc[-6] / 1e6:.1f}M"},
    ]


def _tkey(ts, intraday: bool):
    """Daily+ bars use 'YYYY-MM-DD'. Intraday bars use epoch seconds of the exchange's wall-clock time,
    so the chart's time axis reads in market hours (9:30-16:00 ET)."""
    if not intraday:
        return ts.strftime("%Y-%m-%d")
    if ts.tzinfo is not None:
        ts = ts.tz_convert("America/New_York").tz_localize(None)
    return int((ts - pd.Timestamp("1970-01-01")).total_seconds())


TIMEFRAMES = {"5m": ("5m", "2d"), "15m": ("15m", "5d"), "1h": ("60m", "60d"), "1wk": ("1wk", "5y"), "1mo": ("1mo", "10y")}
INTRADAY = {"5m", "15m", "1h"}


def timeframes(tickers: list[str]) -> dict[str, dict]:
    """Extra chart timeframes: 5-min (2 days), 15-min (5 days), hourly (60 days), weekly (5 years), monthly (10 years)."""
    import yfinance as yf

    out: dict[str, dict] = {t: {} for t in tickers}
    for tf, (interval, period) in TIMEFRAMES.items():
        for i in range(0, len(tickers), 100):
            chunk = tickers[i:i + 100]
            try:
                data = yf.download(chunk, period=period, interval=interval, group_by="ticker",
                                   auto_adjust=True, threads=True, progress=False)
            except Exception:  # noqa: BLE001
                continue
            for t in chunk:
                try:
                    df = (data[t] if len(chunk) > 1 else data).dropna(subset=["Close"])
                except (KeyError, TypeError):
                    continue
                if len(df) >= 5:
                    out[t][tf] = series(df, intraday=(tf in INTRADAY))
    return out


def series(df: pd.DataFrame, intraday: bool = False) -> dict:
    c = df["Close"]
    out = {"candles": [], "volume": [], "sma10": [], "sma20": [], "sma50": [], "sma200": []}
    smas = {k: c.rolling(int(k[3:])).mean() for k in ("sma10", "sma20", "sma50", "sma200")}
    for i, (ts, row) in enumerate(df.iterrows()):
        t = _tkey(ts, intraday)
        out["candles"].append([t, *(round(float(row[k]), 2) for k in ("Open", "High", "Low", "Close"))])
        out["volume"].append([t, int(row["Volume"]), bool(row["Close"] >= row["Open"])])
        for k, sm in smas.items():
            if pd.notna(sm.iloc[i]):
                out[k].append([t, round(float(sm.iloc[i]), 2)])
    return out


def make_entry(t, df, name, currency, exchange, sig) -> dict:
    c = df["Close"]
    return {
        "ticker": t,
        "name": name,
        "currency": currency,
        "exchange": exchange,
        "close": round(float(c.iloc[-1]), 2),
        "change": round(float(c.iloc[-1] - c.iloc[-2]), 2),
        "change_pct": round(float((c.iloc[-1] / c.iloc[-2] - 1) * 100), 2),
        "status": sig["status"] if sig else "NO SIGNAL",
        "exit_level": sig["exit_level"] if sig else None,
        "rvol": sig["rvol"] if sig else round(float(df["Volume"].iloc[-1] / df["Volume"].iloc[-50:].mean()), 2),
        "checks": rule_checks(df),
        "series": series(df),
    }


def _market_open() -> bool:
    try:
        from scan import market_open_now
        return market_open_now()
    except Exception:  # noqa: BLE001
        return False


def build(tickers: list[str], holdings: dict | None = None) -> dict:
    import yfinance as yf

    from positions import exit_status

    holdings = holdings or {}
    everything = list(dict.fromkeys(list(tickers) + list(holdings)))
    hist = get_history(everything)
    stocks = []
    for t in everything:
        df = hist.get(t)
        if df is None:
            continue
        currency = "CAD" if t.endswith((".TO", ".V")) else "USD"
        name, exchange = t, ""
        try:
            tk = yf.Ticker(t)
            tk.history(period="5d")
            meta = tk.history_metadata or {}
            name = meta.get("shortName") or meta.get("longName") or t
            currency = meta.get("currency", currency)
            exchange = meta.get("fullExchangeName", "")
        except Exception:  # noqa: BLE001
            pass
        stocks.append(make_entry(t, df, name, currency, exchange, analyze(df)))
    extra = timeframes([s["ticker"] for s in stocks])
    for s in stocks:
        s["tf"] = extra.get(s["ticker"], {})
    held = []
    for s in stocks:
        if s["ticker"] in holdings:
            s["position"] = exit_status(s, holdings[s["ticker"]])
            held.append(s)
    watch = [s for s in stocks if s["ticker"] in tickers and s["ticker"] not in holdings]
    try:
        import earnings
        earnings.attach(stocks)
    except Exception as e:  # noqa: BLE001
        print("earnings failed:", e, file=sys.stderr)
    try:
        import hype as hype_mod
        hype = hype_mod.get_hype()
        hype_mod.attach(stocks, hype)
        hype_rows = hype_mod.hype_list(hype)
    except Exception as e:  # noqa: BLE001
        print("hype failed:", e, file=sys.stderr)
        hype_rows = []
    return {
        "holdings": held,
        "market_open": _market_open(),
        "updated": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "last_bar": max(s["series"]["candles"][-1][0] for s in stocks) if stocks else None,
        "config": CONFIG,
        "stocks": watch,
        "hype": hype_rows,
    }


if __name__ == "__main__":
    tickers = sys.argv[1:] or ["MCD", "SBUX", "NVDA"]
    os.makedirs(SITE_DIR, exist_ok=True)
    data = build(tickers)
    with open(os.path.join(SITE_DIR, "data.json"), "w") as fh:
        json.dump(data, fh, separators=(",", ":"))
    print(f"wrote {len(data['stocks'])} stocks, {len(data['hype'])} hype rows")
