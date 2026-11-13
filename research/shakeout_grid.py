"""Phase 1a follow-up (Nov 12, 2026): which change, if any, lets Shakeout Bounce catch MU / TSM / AVGO without
turning into noise. why_missed.py showed two separate blockers:
  leader test   MU's and AVGO's 52-week highs were 98 and 114 trading days old (v2 allows 90)
  turn day      TSM never had one day that was up 3%+, above the prior high AND closing in the top 30% of its range
Each row changes those settings and reports signal vs its own random baseline, 2023-25 and 2026 separately.
CAUTION: these settings were picked by looking at Nov 2026, so 2026 is not an independent test for them.
Judge them on 2023-25, and on 2026 only as "did not break".      python shakeout_grid.py"""
import pandas as pd
from shakeout_v2 import run

def pf(D, m, cut=0):
    x = D[m & (D.why != "open")].ret.sort_values(ascending=False)
    if cut and len(x) > 2 * cut:
        x = x.iloc[cut:]
    return (x[x > 0].sum() / -x[x < 0].sum()) if len(x) and (x < 0).any() else float("nan"), len(x)

CHIPS = ("MU", "TSM", "AVGO", "AMD")
print(f"{'52wk high within':>16} {'close in top':>12} {'>prev high':>10} | {'2023-25: n':>10} {'PF':>5} {'-10best':>7} {'base':>5} {'base-10':>7} |"
      f" {'2026: n':>7} {'PF':>5} {'-10best':>7} {'base':>5} {'base-10':>7} | chip signals in Nov 2026")
for hi_days in (90, 120, 150):
    for top, prev in ((0.7, True), (0.5, True), (0.0, True), (0.5, False), (0.0, False)):
        S, B = run("v2", hi_days=hi_days, top=top, prev_high=prev)
        a, b = (S.date >= "2023-01-01") & (S.date < "2026-01-01"), S.date >= "2026-01-01"
        ba, bb = (B.date >= "2023-01-01") & (B.date < "2026-01-01"), B.date >= "2026-01-01"
        chips = " ".join(f"{t}:{'/'.join(d.strftime('%d') for d in S[(S.t == t) & (S.date >= '2026-11-01')].date) or '-'}" for t in CHIPS)
        print(f"{str(hi_days) + ' days':>16} {('top ' + str(round((1 - top) * 100)) + '%') if top else 'any':>12} {'yes' if prev else 'no':>10} | "
              f"{pf(S, a)[1]:>10} {pf(S, a)[0]:5.2f} {pf(S, a, 10)[0]:7.2f} {pf(B, ba)[0]:5.2f} {pf(B, ba, 10)[0]:7.2f} | "
              f"{pf(S, b)[1]:>7} {pf(S, b)[0]:5.2f} {pf(S, b, 10)[0]:7.2f} {pf(B, bb)[0]:5.2f} {pf(B, bb, 10)[0]:7.2f} | {chips}", flush=True)
