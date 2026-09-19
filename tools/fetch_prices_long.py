"""プライム銘柄の10年分日足を data/prices10/ に取得する(トレンドフォローの長期検証用)。"""
import os, time, pandas as pd, yfinance as yf
os.makedirs('data/prices10',exist_ok=True)
uni=pd.read_csv('data/universe.csv',dtype=str)
todo=[t for t,m in zip(uni.ticker,uni.market) if 'プライム' in m and not os.path.exists(f'data/prices10/{t[:-2]}.csv')]
todo+=['^N225'] if not os.path.exists('data/prices10/N225.csv') else []
print(len(todo),'to fetch',flush=True)
B=200
for i in range(0,len(todo),B):
    chunk=todo[i:i+B]
    for attempt in range(3):
        try: df=yf.download(chunk,period='10y',group_by='ticker',auto_adjust=False,threads=True,progress=False); break
        except Exception as e: print('retry',e,flush=True); time.sleep(5*(attempt+1))
    else: continue
    for t in chunk:
        try: d=df[t].dropna(how='all') if len(chunk)>1 else df.dropna(how='all')
        except KeyError: continue
        if len(d)<200: continue
        d=d[['Open','High','Low','Close','Adj Close','Volume']].copy(); d.index.name='Date'
        d.to_csv(f"data/prices10/{'N225' if t=='^N225' else t[:-2]}.csv")
    print(i+len(chunk),flush=True); time.sleep(1)
print('done')
