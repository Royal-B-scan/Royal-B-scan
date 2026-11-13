# Replay briefs, Nov 5–12 2026 (Phase 3 check)

Written on Nov 12–13 to test the Scout skill. Each brief uses only the prices and news available by that afternoon.

- Numbers: `scout_data.py --asof <day>` then `scout_pick.py`, in date order (files in `data/`).
- News: found by web search on Nov 12–13 and taken from the search summaries, not from reading each article in
  full. Every claim is linked; check a link before relying on it.
- "Your stocks" is left out: a replay cannot rebuild what Taylor held or watched on a past day.
- Nothing was emailed, pushed or published.

Briefs: Nov 5, Nov 6, Nov 9, Nov 11, Nov 12 (2:30pm each). Nov 10 had no change worth a brief of its own.
`scorecard-replay.csv` lists the entry windows these briefs named.

## What the replay changed
The first run gave all three focus slots to Semiconductors, Technology Hardware and Information Technology on Nov 9,
which dropped Canadian gold and metals while it was still turning up. `scout_pick.py` now counts groups in the same
sector as one focus. The briefs here were written before that change; the files in `data/` were re-run after it.
