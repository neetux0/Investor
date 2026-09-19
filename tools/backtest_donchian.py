"""ドンチャン型トレンドフォロー(HHLL + SMAフィルター + ATRサイジング)の過去検証。
本人のチャート設定 ATR(20) / SMA(20,55) / HHLL(H:20,L:10) をそのままルール化する。
  エントリー: 終値が直近20日高値(当日除く)を上抜け [かつ SMA20>SMA55] → 翌日寄り買い
  手仕舞い : 終値が直近10日安値(当日除く)を下抜け → 翌日寄り
  枚数    : 1トレードのリスク = 資金の r% を 2*ATR20 で割る(ATRストップ相当)
使い方: python3 tools/backtest_donchian.py [--oos_start 2025-09-19] [--min_turnover 1e8]
"""
import argparse, glob, os
import numpy as np, pandas as pd

ap=argparse.ArgumentParser()
ap.add_argument('--oos_start',default='2025-09-19'); ap.add_argument('--min_turnover',type=float,default=1e8)
ap.add_argument('--cost',type=float,default=0.003); ap.add_argument('--capital',type=float,default=700000)
ap.add_argument('--risk',type=float,default=0.02); ap.add_argument('--max_pos',type=int,default=3)
ap.add_argument('--prices_dir',default='data/prices'); ap.add_argument('--bench',default='data/bench_n225.csv'); ap.add_argument('--out',default='research/backtest_donchian.md')
a=ap.parse_args()

uni=pd.read_csv('data/universe.csv',dtype=str).set_index('code')
bench=pd.read_csv(a.bench,index_col=0,parse_dates=True)

def load(f):
    d=pd.read_csv(f,index_col=0,parse_dates=True); d=d[~d.index.duplicated()].sort_index()
    if len(d)<150 or d['Close'].isna().mean()>0.1: return None
    adj=(d['Adj Close']/d['Close']).fillna(1.0)
    for k in ('Open','High','Low','Close'): d[k]=d[k]*adj
    med=d['Close'].rolling(11,center=True,min_periods=3).median()
    bad=(d['Close']/med>4)|(d['Close']/med<0.25)
    if bad.any(): d=d[~bad]
    d['turn20']=(d['Close']*d['Volume']).rolling(20).mean()
    tr=pd.concat([d['High']-d['Low'],(d['High']-d['Close'].shift()).abs(),(d['Low']-d['Close'].shift()).abs()],axis=1).max(axis=1)
    d['atr20']=tr.rolling(20).mean()
    d['sma20']=d['Close'].rolling(20).mean(); d['sma55']=d['Close'].rolling(55).mean()
    d['hh20']=d['High'].rolling(20).max().shift(1); d['ll10']=d['Low'].rolling(10).min().shift(1)
    d['hh55']=d['High'].rolling(55).max().shift(1); d['ll20']=d['Low'].rolling(20).min().shift(1)
    return d

VARIANTS={
 'D1_hh20_ll10':            dict(hh='hh20',ll='ll10',sma=False),
 'D2_hh20_ll10_sma20>55':   dict(hh='hh20',ll='ll10',sma=True),
 'D3_hh55_ll20_sma20>55':   dict(hh='hh55',ll='ll20',sma=True),
 'D4_hh20_ll10_sma_prime':  dict(hh='hh20',ll='ll10',sma=True,prime=True),
}
trades=[]
prices={}
for f in glob.glob(f'{a.prices_dir}/*.csv'):
    if os.path.basename(f).startswith('N225'): continue
    c=os.path.basename(f)[:-4]; d=load(f)
    if d is None: continue
    prices[c]=d
    mkt=uni['market'].get(c,'')
    for vname,v in VARIANTS.items():
        if v.get('prime') and 'プライム' not in mkt: continue
        sig=(d['Close']>d[v['hh']])&(d['turn20'].shift(1)>=a.min_turnover)
        if v['sma']: sig&=(d['sma20']>d['sma55'])
        i=60; n=len(d)
        while i<n-2:
            if not sig.iloc[i]: i+=1; continue
            e=i+1; entry=d['Open'].iloc[e]; atr=d['atr20'].iloc[i]
            if not (entry>0 and atr>0): i+=1; continue
            x=None
            for k in range(e+1,n):
                if d['Close'].iloc[k]<d[v['ll']].iloc[k]:
                    x=min(k+1,n-1); break
            if x is None: x=n-1; reason='open'
            else: reason='ll'
            exitp=d['Open'].iloc[x]; r=exitp/entry-1-a.cost
            d0,d1=d.index[e],d.index[x]
            if d0 in bench.index and d1 in bench.index and bench.index.get_loc(d0)>0:
                b=bench.loc[d1,'Close']/bench['Close'].iloc[bench.index.get_loc(d0)-1]-1
            else: b=np.nan
            trades.append(dict(variant=vname,code=c,name=uni['name'].get(c,''),market=mkt,entry_date=d0,exit_date=d1,
                entry=entry,exit=exitp,ret=r,days=x-e,reason=reason,atr_pct=atr/entry,
                r_multiple=(exitp-entry)/(2*atr),bench=b,excess=r-b))
            i=x+1
T=pd.DataFrame(trades); T['sample']=np.where(T.entry_date>=pd.Timestamp(a.oos_start),'OOS','IS')
T.to_csv(a.out.replace('.md','_trades.csv'),index=False)

def stats(g):
    w=g[g.ret>0]; l=g[g.ret<=0]
    return pd.Series({'件数':len(g),'勝率':(g.ret>0).mean(),'平均':g.ret.mean(),'中央値':g.ret.median(),'平均利益':w.ret.mean() if len(w) else 0,
        '平均損失':l.ret.mean() if len(l) else 0,'PF':w.ret.sum()/abs(l.ret.sum()) if len(l) else np.nan,'超過(対N225)':g.excess.mean(),'平均保有日':g.days.mean(),
        'R倍数平均':g.r_multiple.mean(),'t値':g.ret.mean()/(g.ret.std()/np.sqrt(len(g))) if len(g)>2 else np.nan})

out=[f"# ドンチャン型トレンドフォロー 過去検証 ({pd.Timestamp.today().date()}) data={a.prices_dir} cost={a.cost:.1%}\n",
 f"- ルール: 終値が直近N日高値を上抜け→翌日寄り買い、終値が直近M日安値を割れ→翌日寄り手仕舞い。売買代金{a.min_turnover/1e8:.0f}億円以上。往復コスト{a.cost:.1%}",
 f"- IS = {a.oos_start} より前 / OOS = それ以降。R倍数 = 損益 ÷ (2×ATR20)。\n","## トレード単位の統計\n"]
tbl=T.groupby(['variant','sample']).apply(stats).unstack('sample').reorder_levels([1,0],axis=1).sort_index(axis=1,level=0,sort_remaining=False)
fmt=tbl.copy()
for col in fmt.columns:
    k=col[1]
    if k in ('勝率','平均','中央値','平均利益','平均損失','超過(対N225)'): fmt[col]=fmt[col].map(lambda v:f"{v:.1%}" if pd.notna(v) else '')
    elif k in ('PF','t値','R倍数平均','平均保有日'): fmt[col]=fmt[col].map(lambda v:f"{v:.2f}" if pd.notna(v) else '')
    else: fmt[col]=fmt[col].map(lambda v:f"{int(v)}" if pd.notna(v) else '')
out.append(fmt.to_markdown()); out.append('')

# ---- ポートフォリオ・シミュレーション(ATRサイジング、同時保有 max_pos、シグナルは日付順・先着) ----
out.append(f"## ポートフォリオ・シミュレーション（資金{a.capital/1e4:.0f}万、1トレードのリスク{a.risk:.0%}、同時保有{a.max_pos}まで、先着順）\n")
rows=[]
for vname in VARIANTS:
    g=T[T.variant==vname].sort_values('entry_date')
    cash=a.capital; equity=[]; open_pos=[]; dates=sorted(set(g.entry_date)|set(g.exit_date))
    by_entry=g.groupby('entry_date')
    for dt in dates:
        # 決済
        still=[]
        for p in open_pos:
            if p['exit_date']==dt: cash+=p['shares']*p['exit']*(1-a.cost/2)
            else: still.append(p)
        open_pos=still
        # 新規
        if dt in by_entry.groups:
            for _,t in by_entry.get_group(dt).iterrows():
                if len(open_pos)>=a.max_pos: break
                eq=cash+sum(p['shares']*p['entry'] for p in open_pos)
                risk_yen=eq*a.risk; shares=int(risk_yen/(2*t.atr_pct*t.entry)//100*100)
                if shares<=0 or shares*t.entry>cash*0.95: shares=int(cash*0.95/t.entry//100*100)
                if shares<=0: continue
                cash-=shares*t.entry*(1+a.cost/2)
                open_pos.append(dict(shares=shares,entry=t.entry,exit=t.exit,exit_date=t.exit_date))
        eq=cash+sum(p['shares']*p['entry'] for p in open_pos)  # 建値評価(簡略)
        equity.append((dt,eq))
    E=pd.Series(dict(equity)).sort_index()
    if len(E)<2: continue
    yrs=(E.index[-1]-E.index[0]).days/365.25
    cagr=(E.iloc[-1]/a.capital)**(1/yrs)-1 if yrs>0 else np.nan
    dd=(E/E.cummax()-1).min()
    oos=E[E.index>=pd.Timestamp(a.oos_start)]
    rows.append({'variant':vname,'最終資金(万)':round(E.iloc[-1]/1e4,1),'年率':f"{cagr:.1%}",'最大DD':f"{dd:.1%}",
                 'OOS期間の損益':f"{(oos.iloc[-1]/oos.iloc[0]-1):.1%}" if len(oos)>1 else '','取引数':len(g)})
b0=bench['Close'].iloc[0]; b1=bench['Close'].iloc[-1]; byrs=(bench.index[-1]-bench.index[0]).days/365.25
boos=bench[bench.index>=pd.Timestamp(a.oos_start)]['Close']
rows.append({'variant':'(参考) 日経平均 買い持ち','最終資金(万)':round(a.capital*b1/b0/1e4,1),'年率':f"{(b1/b0)**(1/byrs)-1:.1%}",'最大DD':f"{(bench['Close']/bench['Close'].cummax()-1).min():.1%}",'OOS期間の損益':f"{boos.iloc[-1]/boos.iloc[0]-1:.1%}",'取引数':0})
out.append(pd.DataFrame(rows).to_markdown(index=False)); out.append('')
out.append("注: 建玉は建値で評価しているため日中のDDは実際より浅く出る。同時保有3で全銘柄のシグナルを先着で取るため、実際の銘柄選択とは異なる。\n")
# 年別
out.append("## 年別 平均リターン / 件数\n")
T['year']=T.entry_date.dt.year
out.append(T.pivot_table(index='year',columns='variant',values='ret',aggfunc=['count','mean']).to_markdown(floatfmt='.3f')); out.append('')
out.append("## 市場別 (D2)\n"); out.append(T[T.variant=='D2_hh20_ll10_sma20>55'].groupby('market').apply(stats).to_markdown(floatfmt='.3f'))
open(a.out,'w').write('\n'.join(out)); print('\n'.join(out))
