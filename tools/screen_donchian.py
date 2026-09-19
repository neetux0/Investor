"""ドンチャン型(HH20/LL10 + SMA20>SMA55 + ATR20サイジング)の当日シグナルと保有銘柄の手仕舞い判定。
使い方:
  python3 tools/screen_donchian.py                       # 新規シグナル一覧
  python3 tools/screen_donchian.py --hold 7203,6758      # 保有銘柄のLL10(手仕舞いライン)も表示
オプション: --capital 700000 --risk 0.02 --min_turnover 1e8 --prime_only 1
"""
import argparse, pandas as pd, numpy as np, yfinance as yf
ap=argparse.ArgumentParser()
ap.add_argument('--capital',type=float,default=700000); ap.add_argument('--risk',type=float,default=0.02)
ap.add_argument('--min_turnover',type=float,default=1e8); ap.add_argument('--prime_only',type=int,default=1)
ap.add_argument('--hold',default='')
a=ap.parse_args()
uni=pd.read_csv('data/universe.csv',dtype=str).set_index('code')
liq=pd.read_csv('data/liquidity.csv',dtype={'code':str})
codes=liq[liq.turnover20>=a.min_turnover].code.tolist()
if a.prime_only: codes=[c for c in codes if 'プライム' in uni['market'].get(c,'')]
hold=[h.strip() for h in a.hold.split(',') if h.strip()]
codes=sorted(set(codes)|set(hold))
print(f'{len(codes)} 銘柄の直近6ヶ月を取得中...',flush=True)
px=yf.download([c+'.T' for c in codes],period='6mo',group_by='ticker',auto_adjust=True,threads=True,progress=False)
sig=[]; holds=[]
for c in codes:
    try: d=px[c+'.T'].dropna(how='all')
    except KeyError: continue
    if len(d)<60: continue
    tr=pd.concat([d['High']-d['Low'],(d['High']-d['Close'].shift()).abs(),(d['Low']-d['Close'].shift()).abs()],axis=1).max(axis=1)
    atr=tr.rolling(20).mean().iloc[-1]; sma20=d['Close'].rolling(20).mean().iloc[-1]; sma55=d['Close'].rolling(55).mean().iloc[-1]
    hh20=d['High'].iloc[-21:-1].max(); ll10=d['Low'].iloc[-11:-1].min(); close=d['Close'].iloc[-1]
    turn=(d['Close']*d['Volume']).iloc[-20:].mean()
    row=dict(code=c,name=uni['name'].get(c,''),date=d.index[-1].date(),close=round(close),hh20=round(hh20),ll10=round(ll10),
             sma20=round(sma20),sma55=round(sma55),atr20=round(atr,1),atr_pct=atr/close,turnover_億=turn/1e8)
    if c in hold:
        row['判定']='手仕舞い(翌日寄り)' if close<ll10 else f'継続 (LL10まで {close/ll10-1:.1%})'; holds.append(row)
    if close>hh20 and sma20>sma55 and turn>=a.min_turnover:
        shares=int(a.capital*a.risk/(2*atr)//100*100)
        row['shares']=shares; row['position_yen']=shares*close; row['stop_2atr']=round(close-2*atr)
        sig.append(row)
pd.set_option('display.width',250)
if holds:
    print('\n== 保有銘柄 =='); print(pd.DataFrame(holds)[['code','name','date','close','ll10','判定']].to_string(index=False))
S=pd.DataFrame(sig)
if S.empty: print('\n本日の新規シグナルなし')
else:
    S=S.sort_values('atr_pct')  # ボラが低い=枚数が入る順
    print(f'\n== 新規シグナル {len(S)} 件 (終値>HH20, SMA20>SMA55) ==')
    print(S[['code','name','date','close','hh20','ll10','sma20','sma55','atr20','atr_pct','turnover_億','shares','position_yen','stop_2atr']].to_string(index=False,
        formatters={'atr_pct':'{:.1%}'.format,'turnover_億':'{:.1f}'.format,'position_yen':'{:,.0f}'.format}))
    print('\n翌営業日の寄りで買い。手仕舞いは終値がLL10を割った翌日の寄り。同時保有3まで。shares=0は単価が高すぎるので見送り。')
    S.to_csv('research/signals_donchian_latest.csv',index=False)
