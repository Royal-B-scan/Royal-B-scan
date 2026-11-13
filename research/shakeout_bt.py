"""Shakeout Bounce quick backtest (planning check, Nov 12 2026).
Signal on day i (large caps: S&P 500 + TSX 60 + a few big ADRs):
  leader: close > 200d SMA, 200d rising vs 20d ago, 252d closing high set within the last 60 days
  shakeout: lowest close of last 10 days is >= 12% below the highest close of the 20 days before it
  turn day: close up >= 3%, close > prior day's high, close in top 30% of day range, volume >= 1.2x 50d avg,
            the shakeout low was within the last 5 days, and no other turn signal in the last 10 days
Trade: buy next day's open. Exit: 8% stop (intraday low, fill at stop or open if gapped), else close below the
shakeout low, else once the close has been above the 50d, a close back below it; else after 60 trading days.
Baseline: same exits from random entries on leader days (no shakeout/turn condition)."""
import pandas as pd, numpy as np
px=pd.read_pickle('px.pkl'); tick=sorted(set(px.columns.get_level_values(0)))
rows=[]; base=[]; rng=np.random.default_rng(1)
def trade(O,H,L,C,s50,i,low):
    if i+1>=len(C): return None
    e=O[i+1]; stop=e*0.92; above=False
    for j in range(i+1,min(i+61,len(C))):
        if O[j]<=stop and j>i+1: return (O[j]/e-1, j-i,'stop')
        if L[j]<=stop: return (stop/e-1, j-i,'stop')
        if C[j]<low: return (C[j]/e-1,j-i,'low')
        if C[j]>s50[j]: above=True
        elif above: return (C[j]/e-1,j-i,'50d')
    j=min(i+60,len(C)-1); return (C[j]/e-1,j-i,'time' if j==i+60 else 'open')
for t in tick:
    df=px[t].dropna()
    if len(df)<300: continue
    O,H,L,C,V=[df[k].values for k in ('Open','High','Low','Close','Volume')]
    c=pd.Series(C); s200=c.rolling(200).mean().values; s50=c.rolling(50).mean().values
    hi252=c.rolling(252).max().values; v50=pd.Series(V).rolling(50).mean().shift(1).values
    last=-99; dates=df.index
    for i in range(260,len(C)):
        lead = C[i]>s200[i] and s200[i]>s200[i-20] and C[i-60:i+1].max()>=hi252[i]*0.999
        if not lead: continue
        if rng.random()<0.02:
            r=trade(O,H,L,C,s50,i,C[i]*0.85)
            if r: base.append((dates[i],t)+r)
        lo=C[i-10:i].min(); pk=C[i-30:i-10].max() if i>=30 else np.nan
        if not (lo<=pk*0.88): continue
        if i-np.argmin(C[i-10:i])-(i-10)>5: continue
        rng_=H[i]-L[i]
        if not (C[i]>=C[i-1]*1.03 and C[i]>H[i-1] and rng_>0 and (C[i]-L[i])/rng_>=0.7 and V[i]>=1.2*v50[i]): continue
        if i-last<10: continue
        last=i; r=trade(O,H,L,C,s50,i,lo)
        if r: rows.append((dates[i],t)+r+(round((1-lo/pk)*100,1),))
S=pd.DataFrame(rows,columns=['date','t','ret','held','why','drop']); B=pd.DataFrame(base,columns=['date','t','ret','held','why'])
def rep(D,name):
    for lab,m in [('2023-25',(D.date>='2023-01-01')&(D.date<'2026-01-01')),('2026',D.date>='2026-01-01')]:
        x=D[m & (D.why!='open')].ret
        if not len(x): continue
        pf=x[x>0].sum()/-x[x<0].sum()
        print(f"{name:9} {lab}: n={len(x):4} win {100*(x>0).mean():.0f}% avg {100*x.mean():+.2f}% PF {pf:.2f} stopped {100*(D[m].why=='stop').mean():.0f}% held {D[m].held.mean():.0f}d")
rep(S,'Shakeout'); rep(B,'Baseline')
S.to_csv('shakeout_trades.csv',index=False)
print(S[S.date>='2026-10-01'].sort_values('date').tail(25).to_string())
