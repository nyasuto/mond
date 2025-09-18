# Money Diary

Money Diary は、個人利用に特化した資産・収支トラッキングツールです。
日々のスナップショットを手入力し、ドル建て資産を為替データと突き合わせながら「原因分解」で資産変動の理由を明らかにします。
AI Agent と組み合わせることで、入力支援や分析・可視化を半自動化できます。

⸻

✨ 特徴
	•	日次スナップショット入力
	•	銘柄ごとに「数量」「現地通貨建て価格」を入力するだけ
	•	為替データを同日付で参照し、自動で円換算
	•	原因分解 (Attribution Analysis)
	•	資産変動を以下に分解：
	•	価格要因
	•	為替要因
	•	クロス要因（価格×為替の相乗）
	•	フロー（入金・売却・配当）
	•	「昨日→今日」の差分を積み上げる方式で直感的に理解可能
	•	シンプルな DB スキーマ
	•	fx_rates：為替
	•	assets：銘柄マスタ
	•	snapshots：日次スナップショット
	•	cashflows：入出金や配当
	•	AI Agent との相性
	•	CSV/SQL 入出力を介して自動化が容易
	•	Agent に「昨日分のスナップショットをコピー→価格更新」と依頼可能
	•	集計やグラフ生成をプロンプトから直接呼び出せる

⸻

🚀 使い方
	1.	DB の初期化

sqlite3 money_diary.db < schema.sql


	2.	銘柄登録

INSERT INTO assets (ticker, ccy) VALUES ('VTI','USD');
INSERT INTO assets (ticker, ccy) VALUES ('eMAXIS_SP500','JPY');


	3.	為替レート入力

INSERT INTO fx_rates (date, pair, rate) VALUES ('2025-09-15','USDJPY',145.2);

または自動取得:

```
# 単日
./scripts/fetch_fx.py 2025-09-15 2025-09-15 USD JPY --db money_diary.db

# 直近1年分（開始日と終了日を指定）
./scripts/fetch_fx.py 2023-09-18 2024-09-18 USD JPY --db money_diary.db
```


	4.	日次スナップショット入力

INSERT INTO snapshots (date, ticker, qty, price_ccy)
  VALUES ('2025-09-15','VTI',2037.88,270.5);


	5.	キャッシュフロー入力（例：配当受領）

INSERT INTO cashflows (date, ticker, type, amount_ccy, ccy)
  VALUES ('2025-09-15','VTI','DIVIDEND',200,'USD');


	6.	評価額ビュー（円換算）

SELECT * FROM v_valuation WHERE date='2025-09-15';


	7.	原因分解ビュー（価格/為替/クロス/フロー）

SELECT date, ticker,
       round(delta_total,3) AS total,
       round(delta_price,3) AS price,
       round(delta_fx,3)    AS fx,
       round(delta_cross,3) AS cross,
       round(flow,3)        AS flow
  FROM v_attribution
 WHERE date='2025-09-15'
 ORDER BY ticker;  -- 'PORTFOLIO' 行も併記


	8.	テスト（開発者向け）

./scripts/test.sh
  # 例: valuation と attribution のゴールデンテストが PASS します



	9.	手動入力（対話式スクリプト）

# 銘柄の追加/更新（assets）
scripts/add_asset.sh

# 当日レートを手入力（対JPY）
scripts/add_fx_manual.sh

# スナップショットを手入力（date, ticker, qty, price_ccy）
scripts/add_snapshot.sh

注: v_attribution は「直近の前回スナップショット」と比較するため、
月次入力（例: 月末のみの記録）でも差分が計算されます。
非JPY資産は該当2日付の為替レート行が必要です。

⸻

📊 将来の拡張
	•	可視化
	•	Streamlit/Next.js を用いたダッシュボード
	•	Price/FX/Flow/Dividend の分解チャート
	•	シミュレーション
	•	モンテカルロで未来の資産推移を確率的に予測
	•	「今やめる」「週3勤務にする」「続ける」など複数シナリオ比較
	•	エージェント連携
	•	「今日の USD/JPY を追加」→ 自動入力
	•	「原因分解グラフを生成」→ PNG/HTML 出力
	•	「1ヶ月の配当合計を計算」→ テキスト要約

⸻

⚠️ 注意点
	•	完全に個人利用前提。クラウド共有や公開環境への配置は想定していません。
	•	為替・株価データは外部 API や CSV インポートにより各自で取得してください。
	•	個人情報や資産データはローカル保存を推奨します。
	•	DB ファイル（money_diary.db）や `data/` は .gitignore 済み。Git に含めないでください。

⸻

🛠️ 開発補助（Makefile）
- `make help`
- `make venv && make install`
- `make db-init`
- `make test`
- `make quality`
- `make gui`

CI: push / PR ごとに GitHub Actions で `make quality` が実行されます。

**GUI 入力（ローカル）**
- 事前準備
  - `python3 -m venv .venv && source .venv/bin/activate`
  - `pip install -r requirements.txt`
- 起動
  - `streamlit run app/streamlit_app.py`
- 機能
  - Assets/Fx/Snapshots のフォーム入力（UPSERT）
  - 指定日付の `v_valuation` と `v_attribution` を一覧・CSVダウンロード
  - DB が無ければ初回起動時に `schema.sql` を適用
