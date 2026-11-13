# Screener clean-up re-tests, changes 2 and 3 (Nov 12, 2026)

Script: `top5_retests.py` (signals and trade rule from Taylor's `allbt.py`). 573 large caps. Trade: buy next open, 8% stop,
50-day exit, 120 days max. A stock picked in the last 20 trading days is not counted again. Random = allbt's baseline.
Not rebuilt: $10B floor at the time, "not owned", earnings within 7 days.

| Top 5 version | 2023-25 PF | 2026 PF | 2026 stop % | 2026 share of profit from 5 biggest winners |
|---|---|---|---|---|
| Now (all four sources, calmest first) | 1.61 | 0.92 | 19% | 21% |
| Change 2: without Trend Cross | 1.52 | 0.94 | 19% | 22% |
| Change 3: Weekly Trend first, then calmest | **1.65** | **1.11** | 19% | 32% |
| Changes 2 + 3 together | 1.59 | 1.05 | 20% | 28% |
| Random (any strong large cap) | 1.63 | 1.03 | 22% | 33% |

Read:
- Change 2: taking Trend Cross out of the Top 5 pool made 2023-25 worse (1.52 vs 1.61) and 2026 the same. Keep Trend Cross in the Top 5 pool.
- Change 3: Weekly Trend first was better than now in both periods and slightly above random in both (1.65 vs 1.63; 1.11 vs 1.03). The edge is small, and in 2026 a third of the profit came from 5 trades.
- The Top 5 as it runs now did not beat random in either period in this test (1.61 vs 1.63; 0.92 vs 1.03). The earlier test (PF 2.06 / 1.14) used the $10B floor and the earnings filter, which this one cannot rebuild.
