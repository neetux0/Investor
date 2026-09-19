"""流動性上位の銘柄について決算発表日・EPSサプライズを取得し data/earnings/<code>.csv に保存する。
使い方: python3 tools/fetch_earnings.py --top 1200
"""
import argparse, os, time
import pandas as pd, yfinance as yf

ap=argparse.ArgumentParser(); ap.add_argument('--top',type=int,default=1200); ap.add_argument('--min_turnover',type=float,default=1e8); a=ap.parse_args()
os.makedirs('data/earnings',exist_ok=True)
liq=pd.read_csv('data/liquidity.csv',dtype={'code':str}); liq=liq[liq.turnover20>=a.min_turnover].sort_values('turnover20',ascending=False).head(a.top)
todo=[c for c in liq['code'] if not os.path.exists(f'data/earnings/{c}.csv')]
print(f'{len(todo)} to fetch',flush=True)
for i,c in enumerate(todo):
    for attempt in range(3):
        try:
            ed=yf.Ticker(f'{c}.T').get_earnings_dates(limit=40)
            break
        except Exception as e:
            time.sleep(3*(attempt+1)); ed=None
    if ed is None or len(ed)==0:
        pd.DataFrame().to_csv(f'data/earnings/{c}.csv'); continue
    ed=ed.copy(); ed.index=pd.to_datetime(ed.index, utc=True).tz_convert('Asia/Tokyo')
    ed.index.name='EarningsDateJST'; ed.to_csv(f'data/earnings/{c}.csv')
    if i%50==0: print(i,flush=True)
    time.sleep(0.3)
print('done')
