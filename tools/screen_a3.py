"""戦略A3 の当日シグナル抽出。
条件: 直近営業日の終値が前日比 +5%以上、出来高が20日平均の2倍以上、かつ その日または前営業日に決算発表があった銘柄。
→ 翌営業日の寄り付きで買い、10営業日後の引けで手仕舞い(A3_react5_any_hold10)。
使い方: python3 tools/screen_a3.py [--min_react 0.05] [--min_turnover 1e8] [--risk_yen 14000] [--stop_pct 0.07]
"""
import argparse, time
import numpy as np, pandas as pd, yfinance as yf

ap=argparse.ArgumentParser()
ap.add_argument('--min_react',type=float,default=0.05); ap.add_argument('--min_turnover',type=float,default=1e8)
ap.add_argument('--risk_yen',type=float,default=14000); ap.add_argument('--stop_pct',type=float,default=0.07)
a=ap.parse_args()

uni=pd.read_csv('data/universe.csv',dtype=str).set_index('code')
liq=pd.read_csv('data/liquidity.csv',dtype={'code':str})
codes=liq[liq.turnover20>=a.min_turnover].code.tolist()
tickers=[c+'.T' for c in codes]
print(f'{len(tickers)} 銘柄の直近40日を取得中...',flush=True)
px=yf.download(tickers,period='60d',group_by='ticker',auto_adjust=True,threads=True,progress=False)
cands=[]
for c,t in zip(codes,tickers):
    try: d=px[t].dropna(how='all')
    except KeyError: continue
    if len(d)<25: continue
    last=d.iloc[-1]; prev=d.iloc[-2]
    react=last['Close']/prev['Close']-1
    volx=last['Volume']/d['Volume'].iloc[-21:-1].mean()
    if react>=a.min_react and volx>=2:
        cands.append(dict(code=c,name=uni['name'].get(c,''),market=uni['market'].get(c,''),date=d.index[-1].date(),
            close=last['Close'],react=react,volx=volx,prev_date=d.index[-2].date()))
print(f'値動き条件を満たす候補 {len(cands)} 件。決算日を照合中...',flush=True)
rows=[]
for x in cands:
    try:
        ed=yf.Ticker(x['code']+'.T').get_earnings_dates(limit=8)
    except Exception: ed=None
    time.sleep(0.2)
    if ed is None or ed.empty: continue
    dates={pd.Timestamp(i).tz_convert('Asia/Tokyo').date() if pd.Timestamp(i).tzinfo else pd.Timestamp(i).date() for i in ed.index}
    hit=[dd for dd in dates if dd in (x['date'],x['prev_date'])]
    if not hit: continue
    sur=ed.loc[[pd.Timestamp(i) for i in ed.index if (pd.Timestamp(i).tz_convert('Asia/Tokyo').date() if pd.Timestamp(i).tzinfo else pd.Timestamp(i).date()) in hit],'Surprise(%)']
    x['earnings_date']=hit[0]; x['surprise']=sur.iloc[0] if len(sur) else np.nan
    # ロット: 建値≒終値とみなし、stop_pct の逆行で risk_yen の損失になる株数(100株単位)
    unit=100; shares=int(a.risk_yen/(x['close']*a.stop_pct)//unit*unit)
    x['shares']=shares; x['position_yen']=shares*x['close']
    rows.append(x)
R=pd.DataFrame(rows)
if R.empty:
    print('本日のA3シグナルなし'); raise SystemExit
R=R.sort_values('react',ascending=False)
pd.set_option('display.width',200)
print(R[['code','name','market','date','close','react','volx','earnings_date','surprise','shares','position_yen']].to_string(index=False,formatters={'react':'{:.1%}'.format,'volx':'{:.1f}x'.format,'close':'{:,.0f}'.format,'position_yen':'{:,.0f}'.format}))
print('\n次の営業日の寄りで買い、10営業日後の引けで手仕舞い。同時保有は3銘柄まで。株数0の銘柄は単価が高すぎるので見送り。')
R.to_csv('research/signals_a3_latest.csv',index=False)
