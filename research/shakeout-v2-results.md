# Shakeout Bounce v2: Phase 1a result (Nov 12, 2026)

Scripts: `get_prices.py` (prices, writes `px.pkl` and `universe.csv`), `shakeout_v2.py` (the test). Run with the
Python in `~/Documents/Stock Screener/.venv-scout` (this folder's name has a colon, so a Python environment cannot live here).

## Data
571 stocks (503 S&P 500, 60 TSX 60, 10 foreign; VYLR had no data), daily bars Jan 3 2022 to Nov 12 2026, plus SPY and XIU.TO.
Today's index members only, so returns are optimistic; the comparison with the random baseline is fair.
Check: re-running the original `shakeout_bt.py` on this download gives v1's published numbers (PF 2.93 and 2.12).

## Result
Profit factor = dollars won per dollar lost. Baseline = random days on stocks passing the same leader test, same exits.

| | Trades | PF 2023–25 | Baseline | Trades | PF 2026 | Baseline |
|---|---|---|---|---|---|---|
| v1 (leader judged on the bounce day) | 305 | 2.94 | 1.66 | 133 | 2.12 | 0.84 |
| v2 (leader judged before the drop) | 449 | 2.82 | 1.79 | 207 | 1.53 | 1.00 |
| Only the signals v2 adds | 157 | 2.37 | 1.79 | 77 | **0.66** | 1.00 |
| v2 + wait for a second up day | 185 | 2.64 | 1.79 | 112 | 1.33 | 1.00 |
| v2, shakeout-low stop only | 449 | 2.91 | 2.00 | 207 | 1.42 | 1.23 |

The v2 baseline moved between 1.65–1.92 (2023–25) and 0.96–1.16 (2026) over six other random draws.

## What it means
1. **v2 as written does not pass.** The signals it adds over v1 lost money in 2026 (0.66 against a baseline of 1.00).
2. **v2 still does not fire on MU, TSM, AVGO or GOOGL** in Nov 2026. AMD and ANET fire on Nov 9 in both versions. Why the others miss has not been worked out yet.
3. **The 2026 edge rests on a few trades.** Without its 10 best trades, v1's 2026 profit factor is 0.43 and v2's is 0.49, both under the baseline (0.64 and 0.80). In 2023–25 the edge survives that cut (1.83 and 2.03 against 1.51 and 1.67).
4. **Waiting for a second up day did not help**, and neither did dropping the 8% stop.

## Not done yet
- Large caps only ($10B+) against $2B+: no market-cap data in this download.
- Phase 1b Sector Rebound and 1c "bouncing with its sector": not started.
- Why MU, TSM, AVGO and GOOGL miss, condition by condition.

## Why MU, TSM, AVGO and GOOGL were missed (Nov 12, later the same day)
Script: `why_missed.py` prints every condition for each day. Two separate blockers, not one:

| Stock | What blocked it | Detail |
|---|---|---|
| MU | Leader test | Its 52-week high was 98 trading days old; v2 allows 90. Nov 11 passes everything else |
| TSM | Turn-day test | Passed the leader test all along. No single day was up 3%+, above the prior high and closing in the top 30% of its range (Nov 9 and Nov 11 failed only the top-30% test) |
| AVGO | Leader test | Already 22% under a 52-week high made 114 days earlier, and under its 200-day, before this drop. Nov 9 passes everything else |
| GOOGL | Leader test, and a weak bounce | 12% under its 200-day, high 127 days old, only +7% off the low with no 3% up day on volume |
| NVDA | Correctly silent | Still making new lows on Nov 12 |

## Looser settings (script: `shakeout_grid.py`)
PF = profit factor; "-10" = without the 10 best trades; base = random baseline for that leader test.

| 52-wk high within | Close in top | 2023–25 trades | PF | -10 | base | base -10 | 2026 trades | PF | -10 | base | base -10 | Catches |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 90 days | 30% (v2) | 449 | 2.82 | 2.03 | 1.79 | 1.67 | 207 | 1.53 | 0.49 | 1.00 | 0.80 | AMD |
| 90 days | 50% | 504 | 2.70 | 1.99 | 1.79 | 1.67 | 240 | 1.52 | 0.56 | 1.00 | 0.80 | AMD, TSM |
| 120 days | 30% | 476 | 2.93 | 2.09 | 1.74 | 1.64 | 223 | 1.45 | 0.50 | 0.97 | 0.80 | AMD, MU |
| **120 days** | **50%** | 534 | 2.78 | 2.04 | 1.74 | 1.64 | 260 | 1.44 | 0.57 | 0.97 | 0.80 | AMD, MU (Nov 11), TSM (Nov 9) |
| 150 days | 50% | 551 | 2.79 | 2.06 | 1.83 | 1.73 | 269 | 1.41 | 0.56 | 1.06 | 0.83 | AMD, MU, TSM |
| 120 days | any, no prior-high test | 656 | 2.71 | 2.09 | 1.74 | 1.64 | 325 | 1.23 | 0.55 | 0.97 | 0.80 | AMD, MU, TSM (all Nov 3–6) |

(All 15 combinations are in the script's output.)

What it shows:
1. **2023–25 is solid for every setting**: about 2.7–2.95 against a baseline near 1.75, and it survives removing the 10 best trades (about 2.0–2.1 against 1.65–1.73).
2. **2026 is weak for every setting.** Each one beats its baseline in total, but without its 10 best trades every one is about 0.5–0.6, under the baseline's 0.80. In 2026 the typical signal did worse than a random day; a handful of big winners carried it.
3. **"120 days + top 50%" is the smallest change that catches MU and TSM.** It costs little in 2023–25 (2.78 against v2's 2.82) and little in 2026 (1.44 against 1.53).
4. **AVGO is not caught by any setting**, because it was not a leader on price before the drop.
5. **Looser is worse in 2026**: each step of loosening lowers the 2026 number.

**Caution:** these settings were chosen by looking at Nov 2026, so 2026 is not an independent test for them. Only the 2023–25 column is a fair read. A fair test of "120 days + top 50%" needs signals from after today.
