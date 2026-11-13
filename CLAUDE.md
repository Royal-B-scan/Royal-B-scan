# Trading Bot: Live Royal B (start here)

This folder is the build home for **Royal B Scout**, Taylor's "trading bot". The Scout is **Royal B's manager**: a team of small workers (sector watcher, price-action worker, news reader, calendar keeper, Royal B's screens, Taylor's book) gathers the data; the Scout puts the big picture together and reports to Taylor twice a day (6:45am, 2:30pm): **1–3 focus sectors, 5 stocks each, why, and what changed**, following each stock's stage (falling: wait → pulled back: watch → turning up: entry window → in trend). Low noise. It does not place trades.

**Read `PLAN.md` first (v2: Royal B's purpose and Taylor's own words are at the top).** Status: planning (Nov 12, 2026). Build one phase at a time and ask Taylor before starting each phase.

## What's here
- `PLAN.md` – the whole plan: why, pieces, detectors, delivery, schedule, phases, open decisions, rules.
- `research/2026-11-12-why-we-missed.md` – what happened with MU/TSM/GOOGL and why Royal B didn't catch it.
- `research/shakeout-backtest.md` + `research/shakeout_bt.py` – the quick Nov 12 test of the Shakeout Bounce detector (v1) and what v2 must fix.
- `skills/scout/SKILL.md` – DRAFT of the Scout skill (the method). Not saved as a skill yet.

## Where everything else lives
- **Royal B page (live):** https://claude.ai/artifact/4rYahwzjmiEjqqBCYUgf7R. Its source and notes are copied in `~/Documents/Stock Screener/royal-b/` (page/, github-repo/, project-notes/; see its CLAUDE.md). Page changes are made in `royal-b/page/` and published with the Artifact tool (Claude Code can do it too: copy the changed files to the scratchpad first, read the live version, then publish to the same URL). Nov 12: clean-up published as version 1794540910-2dd3.
- **Page database:** `state/lists` (watch lists, holdings = mirror of BMO InvestorLine, longterm, plans, channels, trades) and `state/settings` (cash, risk 1%, maxpos 25%, fx).
- **Engine:** GitHub repo Royal-B-scan/Royal-B-scan (public). Daily screen 2:30pm PT → branch `results` (scan.json, comeback.json, data.json, status.json). Edit links: https://github.com/Royal-B-scan/Royal-B-scan/edit/main/<path>.
- **Phone alerts:** ntfy (topic is a secret: GitHub Secret NTFY_TOPIC; never write it into the public repo).
- **claude.ai project "Stock Screener / Everything about stocks":** all notes, backtests and history (current-system.md is the system overview).

## Conventions
- Say "screener / screen", never "scan", to Taylor and on the page. Plain words.
- Hype counts only with facts behind it; separate the headline from the business impact.
- Size: $2B and up, US + TSX; low noise (max 3 sectors × 5 stocks).
- Info only: the Scout never changes Royal B's crowns, labels, Today, Watch Alerts or screeners.
- Backtest before a rule goes live: 2023–25 and 2026 separately, vs a random baseline.
- Market timing in ET in code. Taylor is in Vancouver, BC: permanent daylight time (UTC-7), so the market opens 7:30am and closes 2:00pm his time.
- Trading rules: 1% risk, 8% stop, 50-day exit, 25% max position, wait 15–30 min after the open. Earnings: always explain a move that came from a report (with the numbers); entries right after a report are fine if the data supports them.
- Not financial advice.
