# Shakeout Bounce: quick test v1 (Nov 12, 2026)

Planning check only, to see if the idea is worth building. Script: `shakeout_bt.py` (needs a `px.pkl` price download; see the top of the script).

## Setup
- **Universe:** S&P 500 + TSX 60 + 10 big foreign stocks (TSM, ASML, ARM, SHOP, SAP, NVO, BABA, PDD, MELI, SE): 572 stocks, daily bars Jan 2022 – Nov 12 2026 (yfinance, adjusted).
- **Signal (v1):** on day *i*
  - leader: close above the 200-day, 200-day rising vs 20 days ago, 52-week closing high made in the last 60 days
  - shakeout: lowest close of the last 10 days is 12%+ below the highest close of the 20 days before that
  - turn day: close up 3%+, above the day before's high, in the top 30% of the day's range, volume 1.2x+ the 50-day average; the low was within the last 5 days; one signal per stock per 10 days
- **Trade:** buy the next day's open. Exit: 8% stop (or the open if it gaps below), else a close below the shakeout low, else once back above the 50-day a close below it, else 60 trading days.
- **Baseline:** the same exits from random days on the same leaders (2% sample).

## Results
| | trades | winners | avg per trade | profit factor | hit the stop | avg days |
|---|---|---|---|---|---|---|
| Shakeout 2023–25 | 306 | 46% | +6.0% | **2.93** | 27% | 21 |
| Baseline 2023–25 | 3,754 | 42% | +1.6% | 1.65 | 15% | 25 |
| Shakeout 2026 | 133 | 37% | +4.0% | **2.12** | 31% | 16 |
| Baseline 2026 | 944 | 34% | -0.3% | 0.91 | 23% | 19 |

Beats the baseline in both periods. Like Comeback Turn, it lives on a few big winners: about 3 in 10 hit the stop.

## Recent signals (Oct–Nov 2026)
BMY, BNY, IVZ, CRWD, LITE, APH, VLO, NEM, SHOP (stopped next day), **AMD and ANET on Nov 9** (+15.5% and +10.5% three days later).

## What v1 missed, and the fix for v2
v1 did **not** fire on MU, TSM or AVGO. On the bounce days they were *under* the 200-day (the crash cut through it), and MU/AVGO's 52-week high was more than 60 days old. v2 should judge "leader" **before the drop**: above a rising 200-day 20 days earlier, 52-week high within the last 90 days. Then re-test both periods and check it doesn't just add noise.

Other things to test in phase 1:
- shakeout-low stop vs the 8% stop
- a 2-day confirmation (second up day) vs buying the first turn day
- large caps only (≥$10B) vs $2B+
- does a Sector Rebound on the same day (group turning together) improve it?
