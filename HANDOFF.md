# Handoff (Nov 12, 2026, evening)

Written for the next session picking this up. Read `CLAUDE.md` and `PLAN.md` first; this file is what changed today.

## Royal B Scout: where the phases stand
| Phase | Status | Files |
|---|---|---|
| 1 Prove the signals | Done | `research/phase1-results.md`, `research/shakeout-v2-results.md`, scripts in `research/` |
| 2 The workers | Done, run by hand | `scout_data.py` -> `workers.json` (about 30 s) |
| 3 The manager | Built; **waiting for Taylor to read the replay briefs and say they are right** | `skills/scout/SKILL.md`, `scout_pick.py`, `briefs/replay/` |
| 4 Paper weeks (email + schedule) | **Running from Nov 13** (Taylor OK'd Nov 12). Scheduled tasks `royal-b-scout-am` (6:54am) and `royal-b-scout-pm` (2:31pm), weekdays, Auto mode, email to Taylor only. First live brief Nov 12 pm, test email sent | `skills/scout/SCHEDULED.md`, `briefs/`, `briefs/scorecard.csv`, `scout-state.json` |
| 5–7 | Not started | |

Python: `~/Documents/Stock Screener/.venv-scout/bin/python` (this folder's name has a colon, so no venv can live here).
Run order: `scout_data.py --summary`, then `scout_pick.py`, write the brief per the skill, then `scout_pick.py --save`.

## Phase 1 findings to keep in mind
- Shakeout Bounce setting Taylor chose: 52-week high within 120 days, close in the top half of the day's range.
- A bounce **with its group** (a third or more of the group up 2%+ that day) beat random in both periods; a bounce alone did not. Only the with-group case may be called "entry window".
- Sector Rebound (leading group falls 8%+, closes 3%+ off its low within 5 days) beat random days. Picking the group's 5 leaders by six-month strength did not beat picking any member.
- 2026 results are carried by a few big winners in every test; the 120-day setting was chosen by looking at Nov 2026, so 2026 is not a fair test of it.

## Known gaps in the Scout
- The five replay briefs were written before `scout_pick.py` learned to count groups in one sector as one focus; the Nov 11 and 12 briefs do not mention energy, which the fixed script shows turning up.
- No live (non-replay) brief has been run. `scout-state.json` does not exist yet; the first `scout_pick.py --save` creates it.
- No macro calendar, no share counts or cash, universe is 571 large caps (not everything over $2B).
- News in the replay came from search summaries, not full articles.
- Nothing has been emailed, pushed or published.

## Not started from PLAN.md
- **Screener clean-up** (five agreed changes). Changes 2 and 3 need re-tests with `claude/allbt.py`, which is in Taylor's Claude project and not on this Mac. Changes 1, 4, 5 need no re-test.
- **GitHub sign-in.** No GitHub command-line tool on this Mac. Uploads today were done through the signed-in browser pane (new-file page on github.com).

## Other work from today, in `~/Documents/Stock Screener/royal-b/github-repo`
- Branch `fixes`, **uncommitted**: fund-cache save in `scan.yml`, missed-screen alert and no hard-coded ntfy address in `royal-b-drive-copy_1.gs`, sheet id moved to secret `LISTS_SHEET_ID` (`sync_lists.py`, both workflows), new page link in `intraday.py`, `tests/test_rules.py` + `tests.yml`.
  Before uploading: GitHub secret `LISTS_SHEET_ID` and Apps Script property `NTFY_TOPIC` must be set, or list sync and pushes stop.
- `live_screen.py` and `.github/workflows/live.yml` are **already on GitHub main** (uploaded Nov 12). The live screen stopped at its first check: Massive answered 403 because the account is on the free plan. It needs Stocks Starter ($29/month); secret `MASSIVE_API_KEY` is set. Start it after about 10:40am ET to capture the close.
- The old Mac app's scheduled job was removed and its app moved to the Trash.

## Open decisions with Taylor
1. Do the replay briefs read right? (gate for Phase 4)
2. TradingView Plus (about C$42/month) for live alerts and charts, with or without Massive Starter for the whole-market live screen.
3. Public repo exposes entries, stops and costs in the results files; the old ntfy topic and sheet id remain in git history.
