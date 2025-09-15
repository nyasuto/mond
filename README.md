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


	4.	日次スナップショット入力

INSERT INTO snapshots (date, ticker, qty, price_ccy)
  VALUES ('2025-09-15','VTI',2037.88,270.5);


	5.	キャッシュフロー入力（例：配当受領）

INSERT INTO cashflows (date, ticker, type, amount_ccy, ccy)
  VALUES ('2025-09-15','VTI','DIVIDEND',200,'USD');


	6.	ビューで確認

SELECT * FROM v_valuation WHERE date='2025-09-15';



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

⸻

