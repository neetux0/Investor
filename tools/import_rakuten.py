"""楽天証券「取引履歴(国内株式)」CSV を読み、FIFOで買い/売りを往復トレードに組み、journal/取引記録.csv 形式と集計を出力する。
使い方: python3 tools/import_rakuten.py <楽天CSV> [<楽天CSV>...]
楽天CSVは Shift_JIS。列名は「約定日」「銘柄コード」「銘柄名」「売買区分」「数量［株］」「単価［円］」「受渡金額［円］」等を想定し、表記ゆれは部分一致で拾う。
"""
import sys, re, pandas as pd, numpy as np
from collections import deque

def read(path):
    for enc in ('cp932','utf-8-sig','utf-8'):
        try: return pd.read_csv(path,encoding=enc)
        except Exception: pass
    raise SystemExit(f'読めない: {path}')

def col(df,*keys):
    for c in df.columns:
        n=re.sub(r'[\s　［\[］\]（）()円株]','',str(c))
        if all(k in n for k in keys): return c
    return None

rows=[]
for p in sys.argv[1:]:
    df=read(p)
    c_date=col(df,'約定日'); c_code=col(df,'銘柄コード'); c_name=col(df,'銘柄名'); c_side=col(df,'売買区分')
    c_qty=col(df,'数量'); c_px=col(df,'単価'); c_amt=col(df,'受渡金額'); c_kind=col(df,'取引区分'); c_acct=col(df,'口座区分')
    missing=[k for k,v in dict(約定日=c_date,銘柄コード=c_code,売買区分=c_side,数量=c_qty,単価=c_px).items() if v is None]
    if missing: raise SystemExit(f'{p}: 列が見つからない {missing}. 列一覧: {list(df.columns)}')
    for _,r in df.iterrows():
        side=str(r[c_side])
        qty=pd.to_numeric(str(r[c_qty]).replace(',',''),errors='coerce'); px=pd.to_numeric(str(r[c_px]).replace(',',''),errors='coerce')
        if pd.isna(qty) or pd.isna(px): continue
        rows.append(dict(date=pd.to_datetime(str(r[c_date]).replace('/','-'),errors='coerce'),code=str(r[c_code]).strip(),
            name=str(r[c_name]) if c_name else '',side=('buy' if '買' in side else 'sell' if '売' in side else side),
            qty=qty,px=px,kind=str(r[c_kind]) if c_kind else '',acct=str(r[c_acct]) if c_acct else '',
            amt=pd.to_numeric(str(r[c_amt]).replace(',',''),errors='coerce') if c_amt else np.nan))
X=pd.DataFrame(rows).dropna(subset=['date']).sort_values('date')
print(f'約定 {len(X)} 件, 期間 {X.date.min().date()} 〜 {X.date.max().date()}')

# FIFO で往復に組む(信用の売建→買埋めも「sell→buy」として扱う)
trades=[]; book={}
for _,r in X.iterrows():
    q=book.setdefault(r.code,deque()); qty=r.qty
    while qty>0 and q and q[0]['side']!=r.side:
        o=q[0]; take=min(qty,o['qty'])
        long=o['side']=='buy'
        pnl=(r.px-o['px'])*take*(1 if long else -1)
        trades.append(dict(日付=o['date'].date(),銘柄コード=r.code,銘柄名=r['name'],戦略='',方向='買' if long else '売',建値=o['px'],枚数=take,
            損切り値='',利確目安='',決済日=r.date.date(),決済値=r.px,損益円=round(pnl),損益率=round(pnl/(o['px']*take),4),
            保有日数=(r.date-o['date']).days,ルール遵守='',仮説='',結果メモ=''))
        o['qty']-=take; qty-=take
        if o['qty']<=0: q.popleft()
    if qty>0: q.append(dict(side=r.side,qty=qty,px=r.px,date=r.date))
T=pd.DataFrame(trades)
open_pos={c:sum(o['qty'] for o in q) for c,q in book.items() if q}
T.to_csv('journal/取引記録.csv',index=False,encoding='utf-8-sig')
print(f'往復トレード {len(T)} 件を journal/取引記録.csv に書いた。未決済: {open_pos}')
if len(T):
    w=T[T.損益円>0]; l=T[T.損益円<=0]
    print(f'勝率 {len(w)/len(T):.1%}  合計損益 {T.損益円.sum():,.0f}円  平均利益 {w.損益円.mean():,.0f}  平均損失 {l.損益円.mean():,.0f}  PF {w.損益円.sum()/max(1,abs(l.損益円.sum())):.2f}')
    T['保有区分']=pd.cut(T.保有日数,[-1,0,3,10,30,90,10000],labels=['日計り','1-3日','4-10日','11-30日','31-90日','90日超'])
    print(T.groupby('保有区分',observed=True).agg(件数=('損益円','size'),勝率=('損益円',lambda s:(s>0).mean()),合計=('損益円','sum'),平均率=('損益率','mean')).to_string())
    print(T.groupby('方向').agg(件数=('損益円','size'),勝率=('損益円',lambda s:(s>0).mean()),合計=('損益円','sum')).to_string())
    print('\n損益上位5:'); print(T.nlargest(5,'損益円')[['日付','銘柄名','方向','保有日数','損益円','損益率']].to_string(index=False))
    print('\n損益下位5:'); print(T.nsmallest(5,'損益円')[['日付','銘柄名','方向','保有日数','損益円','損益率']].to_string(index=False))
