"""全上場銘柄(universe.csv)の日足を yfinance で取得し data/prices/<code>.csv に保存する。
使い方: python3 tools/fetch_prices.py [--years 3] [--batch 200]
"""
import argparse, os, time, sys
import pandas as pd, yfinance as yf

ap=argparse.ArgumentParser(); ap.add_argument('--years',type=int,default=3); ap.add_argument('--batch',type=int,default=200)
a=ap.parse_args()
os.makedirs('data/prices',exist_ok=True)
uni=pd.read_csv('data/universe.csv',dtype=str)
todo=[t for t in uni['ticker'] if not os.path.exists(f'data/prices/{t[:-2]}.csv')]
print(f'{len(todo)} tickers to fetch', flush=True)
for i in range(0,len(todo),a.batch):
    chunk=todo[i:i+a.batch]
    for attempt in range(3):
        try:
            df=yf.download(chunk, period=f'{a.years}y', group_by='ticker', auto_adjust=False, threads=True, progress=False)
            break
        except Exception as e:
            print('retry',attempt,e,flush=True); time.sleep(5*(attempt+1))
    else:
        continue
    n=0
    for t in chunk:
        try:
            d=df[t].dropna(how='all') if len(chunk)>1 else df.dropna(how='all')
        except KeyError:
            continue
        if len(d)<30: continue
        d=d[['Open','High','Low','Close','Adj Close','Volume']].copy(); d.index.name='Date'
        d.to_csv(f'data/prices/{t[:-2]}.csv'); n+=1
    print(f'{i+len(chunk)}/{len(todo)} saved {n}',flush=True)
    time.sleep(1)
print('done')
