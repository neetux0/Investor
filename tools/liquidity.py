"""各銘柄の直近20日平均売買代金(円)を集計し data/liquidity.csv に出力する。"""
import os, glob, pandas as pd
rows=[]
for f in glob.glob('data/prices/*.csv'):
    d=pd.read_csv(f,index_col=0,parse_dates=True)
    if len(d)<60: continue
    t=(d['Close']*d['Volume']).tail(20).mean()
    rows.append({'code':os.path.basename(f)[:-4],'turnover20':t,'last_close':d['Close'].iloc[-1],'days':len(d)})
pd.DataFrame(rows).to_csv('data/liquidity.csv',index=False)
print(len(rows),'tickers')
