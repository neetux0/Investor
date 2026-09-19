# Investor

資産形成の記録リポジトリ。

- `plans/` 行動計画（90日単位）
- `journal/取引記録.csv` 売買記録
- `journal/週次検証.md` 仮説→売買→記録→検証の週次ログ
- `research/` 戦略の過去検証結果
- `tools/` 検証スクリプト
  - `fetch_prices.py` 東証全銘柄の日足取得（yfinance）
  - `liquidity.py` 売買代金の集計
  - `fetch_earnings.py` 決算発表日・EPSサプライズの取得
  - `backtest.py` 戦略A/Bの検証
  - `import_rakuten.py` 楽天証券の取引履歴CSVを取引記録に変換し、勝ち筋を集計

## 再現手順
```
pip install yfinance pandas tabulate openpyxl
python3 tools/fetch_prices.py
python3 tools/liquidity.py
python3 tools/fetch_earnings.py
python3 tools/backtest.py
```
`data/prices/` と `data/earnings/` はサイズが大きいためコミットしない。
  - `backtest_donchian.py` ドンチャン型トレンドフォローの検証（`--prices_dir data/prices10` で10年）
  - `screen_donchian.py` HH20/LL10・SMA20/55・ATR20 の当日シグナルと保有銘柄の手仕舞い判定
  - `fetch_prices_long.py` プライム銘柄の10年分日足取得
