# Phase 1 results: Sector Rebound and "with the group or alone" (Nov 12, 2026)

Script: `sector_tests.py` (needs `px.pkl`, `universe.csv`). Shakeout Bounce results are in `shakeout-v2-results.md`.
Run with the Python in `~/Documents/Stock Screener/.venv-scout`.

## Setup
- 568 stocks in 34 groups. A group is the stock's GICS sub-industry when 8 or more of the universe are in it
  (Semiconductors has 17), otherwise its sector; TSX stocks go by TSX sector. A group's index is the average daily
  move of its members.
- Shakeout Bounce is the version Taylor picked Nov 12: 52-week high within 120 days, close in the top half of the day's range.
- PF = profit factor, dollars won per dollar lost. "Typical" = PF without the best trades (5, 10 or 15, as marked in the script output).
- Today's index members only, so returns are optimistic. Comparisons inside the same data are fair.

## 1b Sector Rebound
A group that was leading sells off 8%+, then closes 3%+ above its low within 5 days. Buy at the next open; 8% stop, 50-day exit, 60 days.

| | 2023–25 trades | PF | Typical | 2026 trades | PF | Typical |
|---|---|---|---|---|---|---|
| The group's 5 leaders | 585 | 1.88 | 1.62 | 249 | 2.50 | 1.53 |
| Every member of the group | 1,850 | 2.03 | 1.81 | 780 | 2.39 | 1.59 |
| A random day, any stock | 7,943 | 1.72 | 1.62 | 2,170 | 0.92 | 0.74 |

1. **Buying after a group sells off and turns beat a random day in both periods**, and by a lot in 2026 (2.39 against 0.92).
2. **Picking the 5 leaders did not beat picking any member.** Leaders were slightly worse in 2023–25 and slightly better in 2026; neither gap is meaningful. Six-month strength is not a useful way to choose the 5.
3. **The 2026 result is bunched.** 374 of the 780 trades came from March and April events (+5.0% and +13.5% on average). Events from June on averaged between −2.3% and +4.2%. One market-wide rebound carries the year.
4. **Deeper sell-offs did better**: with a 10% threshold the leaders' PF was 2.35 and 3.34.
5. **A flaw to fix before building:** the "one event per group per 28 days" rule hid the chip turn. Semiconductors met every condition on **Nov 6** (down 24.8%, 3% off the low, 59% of members up 2%+), but an Oct 21 event blocked it.

## 1c Shakeout Bounce: with its group, or alone
| Signals where… | 2023–25 trades | PF | Typical | 2026 trades | PF | Typical |
|---|---|---|---|---|---|---|
| All | 534 | 2.78 | 2.04 | 260 | 1.44 | 0.57 |
| A third or more of the group was up 2%+ that day | 276 | **4.03** | 2.64 | 148 | **2.25** | 0.64 |
| Under a third of the group up 2%+ | 255 | 1.69 | 0.89 | 111 | 0.58 | 0.14 |
| The group had also fallen 8%+ | 278 | 3.02 | 2.13 | 124 | 2.35 | 0.55 |
| The group fell under 8% (stock on its own) | 253 | 2.48 | 1.17 | 135 | 0.69 | 0.19 |
| The group was up 1%+ that day | 366 | 3.14 | 2.18 | 178 | 1.77 | 0.52 |
| The group was up under 1% | 165 | 2.00 | 0.79 | 81 | 0.79 | 0.14 |

1. **A stock bouncing with its group beat one bouncing alone, in both periods and by every measure tried.** This is the clearest result of Phase 1.
2. **Bounces alone lost money in 2026** (0.58 to 0.79) and were only at the random level in 2023–25 once the best trades are removed.
3. **Still carried by big winners in 2026**: even the with-group signals have a typical-trade PF of 0.55–0.64, under the random 0.74–0.80. In 2023–25 they are well above it.
4. These splits were not chosen by looking at Nov 2026, and all three point the same way, so this is a fairer read than the Shakeout settings.

On the chip days: the Semiconductors group was down 24.8% and 82% of its members were up 2%+ on Nov 9, 88% on Nov 11. MU, TSM and AMD would all have counted as "with the group".

## What Phase 1 says to use
| Signal | Verdict | Use in the Scout |
|---|---|---|
| Sector Rebound | Beats random in both periods; 2026 bunched in two months | Picks the **focus sector**. Not a reason to rank the stocks inside it |
| Leaders by 6-month strength | No better than any member | Do not use it alone to choose the 5 |
| Shakeout Bounce with its group | Beats random and beats "alone" in both periods | "Turning up: entry window" |
| Shakeout Bounce alone | At or under random | "Watch" at most; never an entry window |

## Not tested
- $10B+ against $2B+ (no market-cap data in this download).
- Any Scout-style ranking of the 5 stocks other than 6-month strength.
- Whether the with-group signals hold on data after Nov 12, 2026: the only fully fair test of the 120-day setting.
