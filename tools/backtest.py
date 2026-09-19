"""戦略A(決算後ドリフト)・戦略B(出来高急増ブレイク)の過去検証。
使い方: python3 tools/backtest.py [--oos_start 2025-09-19] [--min_turnover 1e8]
出力: research/backtest_latest.md と research/trades_*.csv
"""
import argparse, glob, os
import numpy as np, pandas as pd

ap=argparse.ArgumentParser()
ap.add_argument('--oos_start',default='2025-09-19')
ap.add_argument('--min_turnover',type=float,default=1e8)   # 直近20日平均売買代金の下限(円)
ap.add_argument('--cost',type=float,default=0.003)          # 往復コスト+スリッページ
a=ap.parse_args()

uni=pd.read_csv('data/universe.csv',dtype=str).set_index('code')
prices={}
for f in glob.glob('data/prices/*.csv'):
    c=os.path.basename(f)[:-4]
    d=pd.read_csv(f,index_col=0,parse_dates=True)
    d=d[~d.index.duplicated()].sort_index()
    if len(d)<120 or d['Close'].isna().mean()>0.1: continue
    # 株式分割の調整: Adj Close/Close の比率を OHLC に掛ける(配当分のわずかな歪みは許容)
    adj=(d['Adj Close']/d['Close']).fillna(1.0)
    for k in ('Open','High','Low','Close'): d[k]=d[k]*adj
    # データ不良(1306.Tで見られた1/10価格の日)の除去: 前後5日の中央値から4倍以上乖離した行を落とす
    med=d['Close'].rolling(11,center=True,min_periods=3).median()
    bad=(d['Close']/med>4)|(d['Close']/med<0.25)
    if bad.any(): d=d[~bad]
    d['turn20']=(d['Close']*d['Volume']).rolling(20).mean()
    prices[c]=d
print('loaded',len(prices),'tickers')

bench=pd.read_csv('data/bench_n225.csv',index_col=0,parse_dates=True) if os.path.exists('data/bench_n225.csv') else None  # 日経平均(1306.TはYahooデータに異常値があり不使用)
def bench_ret(d0,d1):
    if bench is None or d0 not in bench.index or d1 not in bench.index: return np.nan
    i0=bench.index.get_loc(d0)
    if i0==0: return np.nan
    return bench.loc[d1,'Close']/bench['Close'].iloc[i0-1]-1

def next_idx(idx,ts):
    """ts より後の最初の営業日の位置"""
    return idx.searchsorted(ts,side='right')

trades=[]
def add(strategy,variant,code,d,e_i,hold,stop=None):
    """e_i: エントリー日の位置(寄り付き買い)。hold 日後の引けで手仕舞い。stop: 直近N日安値割れで翌日寄り手仕舞い"""
    if e_i>=len(d) or e_i+1>=len(d): return
    entry=d['Open'].iloc[e_i]
    if not entry>0: return
    x_i=min(e_i+hold,len(d)-1); reason='time'
    if stop:
        for k in range(e_i+1,x_i+1):
            lowN=d['Low'].iloc[max(0,k-stop):k].min()
            if d['Close'].iloc[k]<lowN:
                x_i=min(k+1,len(d)-1); reason='stop'; break
    exitp=d['Open'].iloc[x_i] if reason=='stop' else d['Close'].iloc[x_i]
    r=exitp/entry-1-a.cost
    trades.append(dict(strategy=strategy,variant=variant,code=code,name=uni['name'].get(code,''),market=uni['market'].get(code,''),
        entry_date=d.index[e_i].date(),exit_date=d.index[x_i].date(),entry=entry,exit=exitp,ret=r,reason=reason,
        bench=bench_ret(d.index[e_i],d.index[x_i]),turn20=d['turn20'].iloc[e_i-1] if e_i>0 else np.nan))

# ---------- 戦略A: 決算後ドリフト(PEAD) ----------
# 反応日R = 発表日D当日とその翌営業日のうち出来高が大きい方(Yahooの発表時刻は不正確なため)。
# エントリー = R の翌営業日寄り。reaction = R終値/前日終値-1。volx = R出来高/20日平均。
nA=0
for f in glob.glob('data/earnings/*.csv'):
    c=os.path.basename(f)[:-4]
    if c not in prices: continue
    try: ed=pd.read_csv(f,index_col=0,parse_dates=True)
    except Exception: continue
    if ed.empty or 'Surprise(%)' not in ed: continue
    d=prices[c]; vol20=d['Volume'].rolling(20).mean().shift(1)
    for ts,row in ed.iterrows():
        s_=row.get('Surprise(%)')
        if pd.isna(s_): continue
        ts=pd.Timestamp(ts)
        if ts.tzinfo is not None: ts=ts.tz_convert('Asia/Tokyo').tz_localize(None)
        i0=d.index.searchsorted(ts.normalize(),side='left')   # D以降の最初の営業日
        if i0<25 or i0+2>=len(d): continue
        cand=[i0,i0+1]
        R=max(cand,key=lambda i:d['Volume'].iloc[i])
        e_i=R+1
        if e_i+1>=len(d): continue
        if d['turn20'].iloc[R]<a.min_turnover: continue
        reaction=d['Close'].iloc[R]/d['Close'].iloc[R-1]-1
        volx=d['Volume'].iloc[R]/vol20.iloc[R] if vol20.iloc[R]>0 else 0
        if volx<2: continue   # 出来高が伴わない=決算反応日を取り違えている可能性が高いので除外
        nA+=1
        if s_>=10:
            add('A','A1_surp10_hold10',c,d,e_i,10)
            if reaction>=0.03:
                add('A','A2_surp10_react3_hold5',c,d,e_i,5); add('A','A2_surp10_react3_hold10',c,d,e_i,10)
                add('A','A2_surp10_react3_stop5_hold10',c,d,e_i,10,stop=5); add('A','A2_surp10_react3_stop5_hold20',c,d,e_i,20,stop=5)
        if reaction>=0.05:
            add('A','A3_react5_any_hold10',c,d,e_i,10); add('A','A3_react5_any_stop5_hold20',c,d,e_i,20,stop=5)
        if reaction>=0.08:
            add('A','A5_react8_any_hold10',c,d,e_i,10)
        if s_<=-10 and reaction<=-0.03:
            add('A','A4_negsurp_react-3_hold10(買い側の値。空売りなら符号反転)',c,d,e_i,10)
print('A events',nA)

# ---------- 戦略B: 出来高急増ブレイク ----------
for c,d in prices.items():
    if len(d)<80: continue
    hi60=d['High'].rolling(60).max().shift(1)
    vol20=d['Volume'].rolling(20).mean().shift(1)
    sig=(d['Close']>hi60)&(d['Volume']>=5*vol20)&(d['Close']>d['Open'])&(d['turn20'].shift(1)>=a.min_turnover)
    last=None
    for i in np.where(sig.values)[0]:
        if i+1>=len(d): continue
        if last is not None and i-last<10: continue   # 10日以内の連続シグナルは無視
        last=i
        add('B','B1_vol5x_hi60_hold5',c,d,i+1,5); add('B','B1_vol5x_hi60_hold10',c,d,i+1,10)
        add('B','B2_vol5x_hi60_stop5_hold10',c,d,i+1,10,stop=5)
        add('B','B3_vol5x_hi60_stop3_hold20',c,d,i+1,20,stop=3)

T=pd.DataFrame(trades)
if T.empty: print('no trades'); raise SystemExit
T['entry_date']=pd.to_datetime(T['entry_date'])
T['sample']=np.where(T['entry_date']>=pd.Timestamp(a.oos_start),'OOS','IS')
T['excess']=T['ret']-T['bench']
T.to_csv('research/trades_all.csv',index=False)

def stats(g):
    w=g[g.ret>0]; l=g[g.ret<=0]
    pf=w.ret.sum()/abs(l.ret.sum()) if len(l) and l.ret.sum()!=0 else np.nan
    return pd.Series({'件数':len(g),'勝率':(g.ret>0).mean(),'平均':g.ret.mean(),'中央値':g.ret.median(),
        '平均利益':w.ret.mean() if len(w) else 0,'平均損失':l.ret.mean() if len(l) else 0,'PF':pf,
        '超過(対N225)':g.excess.mean(),'t値':g.ret.mean()/(g.ret.std()/np.sqrt(len(g))) if len(g)>2 else np.nan})

out=[]
out.append(f"# 戦略A/B 過去検証 ({pd.Timestamp.today().date()})\n")
out.append(f"- 対象: 東証内国株 {len(prices)} 銘柄、直近3年、直近20日平均売買代金 {a.min_turnover/1e8:.0f}億円以上のみ")
out.append(f"- コスト: 往復 {a.cost:.1%}。IS = {a.oos_start} より前、OOS = それ以降")
out.append(f"- 戦略A: 決算発表の翌営業日寄り買い。Surprise = EPS実績/予想の乖離(Yahoo)。反応日R=発表日と翌営業日のうち出来高が大きい日、その翌営業日寄りで買い。reactN = 反応日の終値騰落率がN%以上")
out.append(f"- 戦略B: 終値が60日高値更新 かつ 出来高が20日平均の5倍以上 かつ 陽線 → 翌日寄り買い。stopN = 直近N日安値を終値で割ったら翌日寄りで手仕舞い\n")
for name,grp in T.groupby('strategy'):
    out.append(f"## 戦略{name}\n")
    tbl=grp.groupby(['variant','sample']).apply(stats).unstack('sample')
    tbl=tbl.reorder_levels([1,0],axis=1).sort_index(axis=1,level=0,sort_remaining=False)
    fmt=tbl.copy()
    for col in fmt.columns:
        if col[1] in ('勝率','平均','中央値','平均利益','平均損失','超過(対N225)'): fmt[col]=fmt[col].map(lambda v:f"{v:.1%}" if pd.notna(v) else '')
        elif col[1] in ('PF','t値'): fmt[col]=fmt[col].map(lambda v:f"{v:.2f}" if pd.notna(v) else '')
        else: fmt[col]=fmt[col].map(lambda v:f"{int(v)}" if pd.notna(v) else '')
    out.append(fmt.to_markdown()); out.append('')
# 市場別
out.append("## 戦略B 市場別 (B2_vol5x_hi60_stop5_hold10, 全期間)\n")
b2=T[T.variant=='B2_vol5x_hi60_stop5_hold10']
if len(b2): out.append(b2.groupby('market').apply(stats).to_markdown(floatfmt='.3f')); out.append('')
out.append("## 戦略A 市場別 (A2_surp10_react3_hold10, 全期間)\n")
a2=T[T.variant=='A2_surp10_react3_hold10']
if len(a2): out.append(a2.groupby('market').apply(stats).to_markdown(floatfmt='.3f')); out.append('')
# 年別
out.append("## 年別 平均リターン (hold10系)\n")
h10=T[T.variant.isin(['A2_surp10_react3_hold10','B2_vol5x_hi60_stop5_hold10'])].copy(); h10['year']=h10.entry_date.dt.year
if len(h10): out.append(h10.pivot_table(index='year',columns='variant',values='ret',aggfunc=['count','mean']).to_markdown(floatfmt='.3f')); out.append('')
open('research/backtest_latest.md','w').write('\n'.join(out))
print('\n'.join(out))
