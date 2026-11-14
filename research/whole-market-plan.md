# Plan: the whole US + TSX market over $2B (Nov 13, 2026)

**Goal:** the Scout (and later Royal B's daily screen) looks at every US and Toronto company worth $2B or more, about
2,000 to 2,500 stocks, instead of today's 571 large caps. Data from EODHD (paid, US + TSX + CDRs). Nothing switches
without Taylor's OK at each step.

## What we know (tested Nov 13)
- One request gives every US stock (43,846 rows) or every Toronto stock (2,596) for a day; closes match Yahoo exactly.
- EODHD's screener filters by market cap: Toronto 438 over $2B (some are US companies under Toronto codes), US over
  1,000 (the screener stops at 1,000 per search, so search sector by sector).
- 100,000 requests a day; the tests used about 250.

## Steps

**Step 1. Build the list (the "universe").** ~half a day.
- `universe_eodhd.py`: every US + TSX company over $2B, searched sector by sector so nothing is cut off.
- Remove funds, ETFs, preferred shares and duplicates: one row per company, Toronto listing kept only for Canadian
  companies (CDRs and US companies under Toronto codes go out, as in the Top 5 rule).
- Each stock gets its sector and industry from EODHD; small industries (under 8 stocks) roll up to the sector, the
  same rule the Scout uses today.
- Refreshed once a week (Sunday). Output `research/universe_eodhd.csv`.
- Done when: the list has a sensible count, includes everything in today's 571 that is still over $2B, and Taylor's
  holdings and watch list are all in it.

**Step 2. Prices.** ~half a day.
- First run: two years of daily bars per stock (one request each, ~2,500 requests, a few minutes with 10 at a time).
- After that: one bulk request per day for US and one for Toronto, added to the saved history.
- Always ask for a specific date and check the row count (right after the close the day's file is still filling).
- Same `STOPPED` check as now if the day is incomplete.

**Step 3. Re-test the Scout's signals on the bigger list (the rule: backtest before going live).**
- Re-run the Phase 1 tests (Shakeout Bounce with its group, Sector Rebound) on the new universe, 2023-25 and 2026
  separately, against random picks. EODHD has the history.
- The groups change (EODHD industries instead of the old list's groups), so the "a third of the group up 2%+" rule
  and Sector Rebound must hold up on the new groups. If a signal stops beating random, it does not go live.
- Taylor sees the numbers and decides.

**Step 4. Switch the Scout over** (only after Step 3 passes and Taylor says yes).
- `scout_data.py` reads the new universe and EODHD prices (Yahoo stays as a fallback for one week).
- Cloud runs need two settings Taylor makes once: allow `eodhd.com` in the cloud environment's network access, and
  add `EODHD_API_KEY` as an environment variable there (cloud runs cannot see GitHub secrets).
- Expect more candidates per group; the brief still shows at most 3 sectors x 5 stocks.

**Step 5. Royal B's daily screen** (separate decision, later).
- Every Royal B screener was backtested on Yahoo data. Run EODHD side by side for 2 weeks, compare signals day by day,
  re-test what differs, then ask Taylor before switching the GitHub engine.
- Also decide then: switch or retire `live_screen.py` / `live.yml` (still on Massive, failing).

## Costs and limits
- About 2,500 requests for the first history download, then about 10 a day plus 50 a week for the list: far inside
  100,000.
- EODHD prices are blended from many sources: volume can differ a little from InvestorLine/TradingView.
- Toronto CDRs (Cboe Canada) stay out of the universe; they follow their US company.
- Not live: prices are end of day (15-minute delayed during the day).

## Order and checkpoints
1 -> show Taylor the list. 2 -> show one day of prices next to Yahoo. 3 -> show the re-test numbers (go / no-go).
4 -> one week of briefs with both sources, then Yahoo off. 5 -> separate OK.

## Step 1 result (Nov 13, 2026, afternoon)
`universe_eodhd.py` -> `research/universe_eodhd.csv`: **2,133 companies over $2B (1,930 US, 203 Toronto), 102 groups.**
Dropped: 2,728 OTC/pink-sheet listings, 215 funds/ETFs/preferreds, 62 Toronto CDRs, 113 second listings or share
classes. Of the old 571, 568 are in; the other 3 are duplicates kept under one listing (GOOG -> GOOGL, FOX -> FOXA,
SHOP -> SHOP.TO). All 40 big Canadian names checked are in (banks, energy, rails, miners, REITs such as REI-UN.TO).
Taylor's holdings under $2B or held as CDRs (BOS.TO, EFX.TO, GOOG.TO, MU.TO) stay tracked through "your book", as now.

## Step 2 result (Nov 13, 2026, afternoon)
`prices_eodhd.py --history` -> `data/px_eodhd.pkl` (45 MB): **2,127 of 2,133 stocks, Nov 4 2024 to Nov 13 2026, about 2 minutes.**
Six had no EODHD history (VYLR, RML, OPAY, ACCV, MSGR, CSANY: new or renamed listings). Prices are split- and
dividend-adjusted like Yahoo's.
Side by side with Yahoo on the 581 stocks both have (Nov 12 close): 555 the same to 0.1%, 579 within 1%; no day from
Aug to Nov differs by more than 1.05% for any stock (the small gaps are dividend adjustments on utilities and banks:
WEC, DUK, SJM, TFC). Volume: median ratio 1.00, 567 of 581 within 5%, US and Toronto alike.
Daily top-up: `prices_eodhd.py --update YYYY-MM-DD` (two bulk requests). Nov 13 was only partly in at 2pm BC
(1,453 of 2,127 stocks), so the daily top-up must run after EODHD finishes, and it stops if a file looks short.
