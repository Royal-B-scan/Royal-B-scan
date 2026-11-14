# Whole-market re-test of the Scout's signals (step 3, Nov 13, 2026)

Script: `sector_tests_eodhd.py` (a copy of `sector_tests.py` using `px_eodhd_long.pkl` and `universe_eodhd.csv`).
2,058 stocks over $2B (US + TSX) in 101 groups (EODHD industry; under 8 members rolls up to the sector). EODHD prices
Nov 2021 to Nov 12 2026. Same rules and exits as Phase 1 (buy next open, 8% stop, 50-day exit, 60 days).
Random baseline: 1% of days, three draws; "leader" baseline = stocks passing the Shakeout leader test.
Today's members only, so all numbers are optimistic; comparisons inside the same data are fair.
PF = dollars won per dollar lost.

| | 2023-25 trades | PF | 2026 trades | PF |
|---|---|---|---|---|
| **Sector Rebound** (leading group fell 8%+, turned), every member | 11,610 | **1.74** | 4,261 | **1.58** |
| Sector Rebound, the group's 5 leaders | 2,905 | 1.81 | 1,065 | 1.47 |
| **Shakeout Bounce with its group** (a third+ of the group up 2%+) | 1,512 | **2.08** | 937 | **1.24** |
| Shakeout Bounce alone (under a third up 2%+) | 1,387 | 1.25 | 499 | 1.02 |
| Random day, any stock (3 draws) | ~15,000 | 1.50-1.58 | ~4,000 | 0.99-1.12 |
| Random day, leader stocks (3 draws) | ~7,000 | 1.50-1.59 | ~2,100 | 0.91-1.11 |

Old 571-stock results for comparison (phase1-results.md): Sector Rebound 2.03 / 2.39 vs random 1.72 / 0.92;
with its group 4.03 / 2.25; alone 1.69 / 0.58.

## Read
1. **Both tested signals still pass** the rule on the whole market: they beat random in 2023-25 and in 2026, and a
   bounce with its group still beats a bounce alone in both periods.
2. **The edge is smaller than on the 571 large caps**, most in 2026: Shakeout with its group 1.24 against a random
   0.99-1.12 (on the old list 2.25 against 0.92). Sector Rebound 1.58 against 0.99-1.12 holds up better.
3. **2026 still rests on big winners**: without its 10 best trades, Shakeout with its group falls to 0.82, under random.
   38% of those 2026 trades hit the 8% stop.
4. **Bounce alone is still no better than random** (1.25 / 1.02): it stays "watch", never an entry window.
5. Deeper sell-offs still do better (group fell 10%+: leaders 1.96 / 1.62).
6. Picking the 5 leaders still does not beat picking any member.

## Not yet tested
- Whether a size floor (for example $10B, close to the old list) keeps the bigger 2026 edge while widening the net.
- 2026 is a fair test of the signals but not of the 120-day setting (chosen by looking at Nov 2026).
