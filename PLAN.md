# Royal B Scout: the plan (v2, Nov 12, 2026)

**Status: PLANNING.** Nothing is built. Claude Code builds from this file, one phase at a time, with Taylor's OK before each phase. v2 rewrites v1 around Taylor's own description of the job (below).

## Royal B's purpose (agreed with Taylor, Nov 12)
Royal B is Taylor's one home base for swing trading. InvestorLine places the trades; Royal B finds, watches, times and manages them. Four jobs:
1. **Narrow down** the US + Canadian market to a short list worth his time (mostly large companies).
2. **Find the entry point early**: about halfway up a move, not at the top; comfortable adding on the way up.
3. **Keep track and alert**: watch lists, a plan for every stock, alerts at the buy zone, add line and get-out line.
4. **Mirror his real account** (BMO InvestorLine), so trades are sized with real money and his rules.

How he trades: follow the money and the trend (Druckenmiller); the market often moves on hype first. Rules: 1% risk per trade, 8% stop, 50-day exit, 25% max position, wait 15–30 min after the open, no buys within a week of earnings. Taylor makes the final call; Royal B narrows and explains. Nothing goes in unless it's tested and makes Royal B better. Keep it simple.

**Where it falls short:** it only looks at prices after the fact (every screen waits for the stock to get back above its averages), and it reads no news. Nov 5–12 showed both: the chip sell-off and bounce (MU, TSM, AMD, AVGO, GOOGL) went unseen until the move was mostly done, and NVDA's slide had a reason (CEO Jensen Huang resigned Nov 12; earnings Nov 17) that no screen could see.

## What the Scout is (Taylor's words, Nov 12)
> "The Scout is Royal B's manager and reports to me. The Scout has a bunch of little guys working within Royal B, collects all the data and summarizes it and brings it to me. For it to do a good job, it has to find me the best opportunities."
>
> "It needs to find more specific sectors that I should be focused on, with five stocks within that sector. The emails should give me a summary of why we're looking and trading in those sectors because of what it found. But it can't be too much noise. It needs to be like me going around digging up all the information and putting the big picture together."
>
> "Like the big pullback in the chip scenario: Google, TSM, MU, AMD all pulled back, and it would have been a good opportunity to keep watching. The Scout should alert: hey, these stocks are starting to trend upwards, maybe this is a pullback and a good entry point. NVDA kept sliding; the Scout would say: this is why it's going down, wait for a bottom, its earnings are coming up November 17th."

So the Scout is **sector-first**, **story-first**, and **follows things over time**:
- It picks **1 to 3 focus sectors** (themes) where something is happening, and says why in plain words: the big picture.
- For each sector, **5 stocks**: the best ones to own if the theme plays out.
- Each stock has a **stage**, and the Scout follows it day to day until it's a buy or it's dropped.
- It only speaks up when something **changes**. Quiet days get a short "nothing new" brief.

## The team (manager + little guys)
```
                         TAYLOR
                           ^   brief: 6:45am + 2:30pm BC time (phone push + email + Royal B Home)
                           |
                 +-------- SCOUT (manager) ---------+
                 |  reads every worker's report,     |
                 |  puts the big picture together,   |
                 |  picks the sectors + 5 stocks,    |
                 |  decides what changed and matters |
                 +-----------------------------------+
      reports ^        ^          ^          ^          ^          ^
              |        |          |          |          |          |
     Sector     Price-action   News        Calendar    Royal B      Your
     watcher    worker         reader      keeper      screens      book
```
| Worker | What it reports to the Scout | Built from |
|---|---|---|
| **Sector watcher** | Which sectors/themes sold off, which are turning, which are leading; money flow between groups (sector + theme ETFs vs SPY/XIU; % of each group above its 50-day) | New. ETF list in "Data" below |
| **Price-action worker** | For every stock in a focus sector and on Taylor's lists: its stage (below), the Shakeout Bounce signal, unusual volume, distance from the 20/50/200-day, swings per day | New detectors + Royal B's existing math |
| **News reader** | The "why" for every big move: earnings, guidance, analyst moves, deals, CEO changes, regulation, macro (rates, oil, tariffs). Newest first, with links. Labels each item fact / rumour, and separates the headline from what it changes for the business | Web search, Yahoo/Google News RSS, SEC 8-Ks, IR pages, yfinance upgrades |
| **Earnings worker** | For any stock that moved on a report: EPS and revenue vs estimates, guidance, the price reaction, so the move is understood | yfinance earnings history, Royal B earnings_hist.json, press releases |
| **Business checker** | Revenue growth, profit, margins, cash flow for the 5 stocks and for Rising stars | yfinance financials; Judgement Day (judgement.py) |
| **Hype worker** | Buzz building (Reddit, StockTwits), passed on only with the facts behind it | Royal B hype.py (ApeWisdom, StockTwits) |
| **Calendar keeper** | What's coming that can move a stock or sector: earnings dates, Fed/CPI/jobs days, big conferences, index changes, lock-ups | yfinance calendar, economic calendar, Royal B earnings data |
| **Royal B screens** | Today's Top 5 Entry Ready, Bullish Turn, Early Turn, Trend Cross, Weekly Trend, the market gauge (breadth) and credit light | GitHub results branch (scan.json, comeback.json) |
| **Your book** | What Taylor owns (mirror of InvestorLine), his watch lists, plans, cash, sizing settings; news on anything he owns goes to the top | Royal B db `state/lists`, `state/settings` |

## Stock stages (what the Scout follows over time)
| Stage | Means | What the brief says |
|---|---|---|
| **Falling: wait** | Still dropping, no bottom yet | Why it's falling, what to wait for (a bottom, earnings date, news) e.g. "NVDA: CEO resigned Nov 12, earnings Nov 17. Wait for a bottom after earnings." |
| **Pulled back: watch** | A strong stock knocked down hard, selling slowing | Keep watching; where the bottom is; what would turn it |
| **Turning up: entry window** | First strong up days off the low (Shakeout Bounce), group turning with it | "Starting to trend up. Possible entry." + buy zone, stop, shares |
| **In trend** | Back above its averages, Royal B's regular screens take over | Hand-off to Royal B (Top 5 / Watch Alerts); the Scout stops repeating it |
| **Late / stretched** | Ran too far too fast (15%+ above the 50-day) | "Missed this leg, wait for a pullback" |
| **Broken: drop** | News says the business broke, or it made a new low after turning | Why it's dropped from the watch |

A **sector** gets the same stages, judged on its ETF and how many of its stocks are turning.

## The brief (what lands on Taylor's phone, email and Royal B Home)
Short. Readable in 2 minutes. Example of the shape, using the real Nov 6–12 chip story:

> **Royal B Scout · Tue Nov 11 · 2:30pm**
> **Big picture:** Chips had their worst day since 2020 on Nov 5 (AI spending worries, Kioxia warned memory prices are slowing). Since Nov 6 they're bouncing on returning memory demand and analyst upgrades. The rest of the market is calm (gauge 55%, yellow). Money is going back into chips first.
>
> **Focus 1 · Semiconductors: Turning up** (SMH +13% off the low; 6 of 10 chip leaders up 3 days in a row)
> - AMD: Turning up, entry window. +44% off the low, back above the 50-day. Late for a first buy; wait for a pullback to ~$550.
> - AVGO: Turning up. Buy zone 355–365, stop 330, ~40 shares.
> - TSM: Turning up. Report it could make memory chips for Nvidia (+6%). Buy zone 400–410, stop 375.
> - MU: Pulled back → turning. Best day since July. Still under the 20-day (843). Watch for a close above it.
> - NVDA: Falling, wait. Earnings Nov 17. Don't catch it before the report.
>
> **Your stocks:** MU CDR and GOOG CDR bouncing with the group. Nothing urgent.
> **Coming up:** NVDA earnings Mon Nov 17 (moves the whole chip group). CPI Thu.
> **Changed since this morning:** TSM moved from Pulled back to Turning up.

Rules for the brief:
- **1 to 3 sectors, 5 stocks each, max.** If nothing qualifies: "No sector is setting up. Your stocks: nothing urgent." That's a good brief.
- **Lead with what changed.** Stocks that haven't changed stage get one short line or are left out.
- **Every "why" has a source link** (in the email and on the page; the phone push stays short).
- **Your book first** whenever there's news on something Taylor owns.
- **Push only on change:** a phone alert only when a stock enters "Turning up: entry window", a holding has material news, or a focus sector changes stage. The two scheduled briefs always go out (email + page).

## How the Scout picks sectors and the 5 stocks
1. **Find sectors where something is happening** (Sector watcher + News reader): a sharp group sell-off (8%+ in 10 days) in a sector that was leading, a group turning up together, or a group making new highs on news/money flow. Rank by: group was a leader before (above a rising 200-day) > clear story with sources > breadth of the move (many stocks, not one) > big money signals (volume, 13F, hype building).
2. **Pick the 5 stocks**: companies of $2B and up in that group (US and TSX), leaders before the drop, strongest relative strength over 6 months, clean news (no broken business), not in earnings week unless the earnings are the point. Taylor's own stocks in that group are always shown.
3. **Rising stars (max 2, "good to know"):** $2B+ companies with strong revenue growth, profits and improving margins, in a sector or trend that's growing, even if no price signal yet. One line each with the numbers.
4. **Keep a sector on the list** while it's in play (falling-wait through in-trend). Drop it when it's in trend and handed to Royal B's screens, or broken. Max 3 at a time; a new one has to beat the weakest to get in.

## Data (all free)
- **Prices/volume:** yfinance daily (and 1-minute later, with the live-feed plan).
- **Sectors and themes (US):** XLK, XLC, XLY, XLP, XLE, XLF, XLV, XLI, XLB, XLU, XLRE; themes SMH, SOXX, IGV, HACK, CLOU, XBI, IBB, KRE, ITA, GDX, SIL, URA, TAN, ICLN, COPX, XHB, ITB, JETS, XRT, BOTZ, ARKK, IPAY.
- **Sectors (Canada):** XIU.TO, XEG.TO, XFN.TO, XIT.TO, XMA.TO, XGD.TO, XUT.TO, XRE.TO.
- **Members of each group:** S&P 500 / TSX 60 sector classification + ETF top holdings; Royal B's scan.json sectors.
- **News:** web search, Yahoo Finance + Google News RSS per ticker and per sector, SEC EDGAR 8-K feed, company IR, yfinance upgrades/downgrades.
- **Calendar:** yfinance earnings dates; economic calendar (Fed, CPI, jobs).
- **Royal B:** results branch (scan.json, comeback.json, status.json), db `state/lists` + `state/settings`.

## Delivery
- **Email** (Gmail) at 6:45am and 2:30pm BC time, to Taylor only, sent automatically (decision 1).
- **Phone push** (ntfy, the same topic Royal B uses) only on change (above).
- **Royal B Home:** a "Scout" box at the top (big picture, focus sectors, the 5 stocks each with stage), and a "why it moved" line on each stock's chart. Data in db doc `state/scout`: `{asof, session, big_picture, sectors:[{name, etf, stage, why, sources:[...], stocks:[{ticker, stage, line, plan:{zone_lo, zone_hi, stop, shares}, next_event}]}], book:[...], calendar:[...], changes:[...]}`. With no doc, the page looks exactly like today.
- **Memory:** `scout-state.json` keeps each sector's and stock's stage and history, so the Scout knows what changed and can say "MU moved from Pulled back to Turning up". Saved in the db (`state/scout_memory`) so every run sees it.
- **Archive + scorecard:** every brief saved (`briefs/YYYY-MM-DD-am|pm.md`); every "Turning up: entry window" call logged with price and date. Weekly: 5/10/20-day results vs SPY and vs the stop. After 4 weeks, keep what works.

## Schedule
BC is on permanent daylight time (UTC-7): **market opens 7:30am, closes 2:00pm** Taylor's time.
- **6:45am** (`CRON_TZ=America/Vancouver 45 6 * * 1-5`): overnight news, pre-market movers, today's calendar, what to watch at the open.
- **2:30pm** (`CRON_TZ=America/Vancouver 30 14 * * 1-5`, decision 2): the day's story, stage changes, plan for tomorrow (also saved as `trade-plan-YYYY-MM-DD.md`, Taylor's existing habit).
- Skips US market holidays.
- Taylor can also ask any time: "run the Scout", "scout semis", "scout MU".

## Phases (build in order; Taylor's OK before each)
| # | Phase | What gets built | Done when |
|---|---|---|---|
| 0 | Plan | This file | DONE Nov 12: purpose agreed, all 6 decisions answered (below) |
| 1 | Prove the signals | Backtests, 2023–25 and 2026 separately vs a random baseline: (a) **Shakeout Bounce v2** (leader judged before the drop, so MU/TSM count; v1 already PF 2.93 / 2.12 vs 1.65 / 0.91); (b) **Sector Rebound** (group sells off 8%+, then turns: does buying its top 5 leaders beat buying them at random?); (c) does a stock bouncing *with its sector* beat one bouncing alone? | Each has a number; only winners are used for "Turning up: entry window" |
| 2 | The workers | `scout_data.py`: sector watcher, price-action worker, calendar keeper, Royal B screens reader, your book reader. Writes one `workers.json` per run. News reader stays with the Scout (Claude) because it needs judgment | Runs in under 5 minutes; checked by hand on 3 days, including a replay of Nov 5–12 |
| 3 | The manager | The **Scout skill** (`skills/scout/SKILL.md`): reads `workers.json` + news + yesterday's memory, writes the brief, updates stages | Replay of Nov 5–12 gives briefs Taylor says are right (chips flagged on Nov 6, NVDA "wait") |
| 4 | Paper weeks | Two scheduled tasks; brief by email + archive only; pushes on; page untouched | 2 weeks; Taylor rates noise, timing and usefulness |
| 5 | On Royal B | Scout box on Home, "why it moved" lines, `state/scout` in the db | Phone + laptop; page unchanged when there's no scout doc |
| 6 | Into the engine | Proven signals (Shakeout, Sector Rebound) move into GitHub's daily screen so they also feed Top 5 and the Screener tabs | Daily screen green with them |
| 7 | Live | With the live-feed plan: intraday push when a Scout stock reaches its buy zone | After the live-feed trial |

## Taylor's decisions (Nov 12)
1. **Email: send automatically.** The Scout briefs go to Taylor without a preview (an exception to his preview-every-email rule, for these briefs only, to him only).
2. **Afternoon brief at 2:30pm** BC time (closing prices settled). Note: GitHub's daily screen also starts 2:30pm and lands on the results branch ~3:00–3:20pm, so the 2:30 brief reads the previous day's Royal B screen plus its own fresh data from the workers; it does not wait for the screen.
3. **Canada too**, from day one: TSX sectors and stocks.
4. **$2B and up**, but watch the volume of stocks coming through (low noise stays the rule: still max 3 sectors × 5 stocks). Plus: when the Scout connects the dots on a **smaller company doing really well** (revenue growth, profits, margins) **in a growing sector or trend**, that's good to know: it goes in a short "Rising stars" line (max 2 names), not in the 5.
5. **Earnings: allowed, with the facts.** The 7-day rule was about being aware that a stock jumped or dropped because of an earnings report. So whenever a stock moved on earnings, the Scout says so and shows the numbers (EPS and revenue vs estimates, guidance, the reaction) so Taylor understands the move. An entry right after a report is allowed if the data supports it. Before a report, it still flags "earnings in X days: a gap can jump your stop".
6. **Hype counts only when it's built on facts.** Buzz (Reddit, StockTwits, headlines) is factored in when there's real, checkable information behind it. Even a true story shouldn't decide a stock's future by itself: NVDA's CEO news was real, but the Scout should separate "the headline" from "what it changes for the business" (sales, earnings, products, customers) and say which one is driving the price. Rumours get labelled as rumours, never as reasons.

## Screener clean-up (agreed by Taylor Nov 12; build alongside Phase 1)
Why: the Nov 12 debrief (Claude Doc "Royal B Screener Debrief", https://claude.ai/artifact/XqenghCkjmYDMcSbKaySrq; project note claude/screener-debrief-2026-11-12.md; script claude/allbt.py). Same test for every screener, 572 US + TSX large caps, 2023–25 vs 2026. Only Weekly Trend (2026 PF 1.27), Comeback Turn (1.25) and Early Turn breakout (1.09) beat random (0.94); Trend Cross alone was 0.72 and its live paper portfolio trails the market (USD +0.6% vs SPY +10.2%, CAD −13.5% vs XIU +14.4%). The page shows ~450 rows a day.

Taylor approved all five changes:
1. **Cut from the page and alerts** (hide; keep the code): Almost (heads-up), Strong (waiting), Early Turn squeeze, Early Turn pullback, the Comebacks "moved up" list. Includes removing PULLBACK from the green Buy light (`lightOf` in 03-lists.js: `buySig`), from Today/Watch Alerts, and from Judgement Day's buy rows. Comeback stages stay as background for the Scout.
2. **Trend Cross off the crowns, the Almost alerts and the paper portfolio**; re-test it as a Top 5 source (Top 5 with vs without Trend Cross, 2023–25 and 2026). Keep it in the pool only if the Top 5 is better with it.
3. **Weekly Trend: show new crosses only** (WK NEW), and give Weekly Trend first place in the Top 5 ranking (re-test the ranking change before it goes live).
4. ~~**Paper portfolio (journal.py on GitHub): trade the Top 5** instead of every Trend Cross signal.~~ Dropped Nov 12 after a test: as a paper account the Top 5 lost to Trend Cross in US stocks in 2023–25 and 2026 (`research/top5-paper-results.md`). Taylor: leave it as is.
5. **Top 5: merge US and Toronto listings** of the same company (e.g. COST + COST.TO): keep one row, prefer the listing in the currency Taylor holds cash in, or the US one.

Where each change lives: page = `~/Documents/Stock Screener/royal-b/page/` (publish from a Cowork session to https://claude.ai/artifact/4rYahwzjmiEjqqBCYUgf7R); engine = GitHub main (top5.py, journal.py, intraday.py alerts, github_scan.py), uploaded by Taylor with direct edit links. After the change: the Screener tabs + Watch Alerts should total about 10 tested signals a day plus the Top 5.

## Rules the build must keep
- Plain words for a beginner-to-intermediate investor; "screener / screen", never "scan".
- Low noise: max 3 sectors × 5 stocks; lead with changes; push only on change.
- Info only on Royal B: never change crowns, labels, Today, Watch Alerts, screeners, lists or holdings. The Scout writes only `state/scout` and `state/scout_memory`.
- Backtest before a signal can say "entry window": 2023–25 and 2026 separately, vs a random baseline.
- Taylor's rules: 1% risk, 8% stop, 50-day exit, 25% max position, wait 15–30 min after the open. Earnings: always say when a move came from a report and show the numbers; warn before a report; an entry right after one is fine if the data supports it (decision 5).
- Hype and headlines only count with facts behind them; separate the headline from the business impact (decision 6).
- Market timing in ET in code; Taylor's times in BC time (UTC-7 all year).
- Every news claim has a source link; if it can't be confirmed, say so.
- GitHub repo is public: no secrets in code.
- Not financial advice (one line at the bottom of each brief).
