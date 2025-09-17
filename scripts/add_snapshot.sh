#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<USAGE
使い方: $(basename "$0") [db_path]

説明:
  snapshots に対し、指定日のスナップショットを手動追加/更新します（対話式）。

引数:
  db_path : SQLite DB パス（省略可、既定: money_diary.db）

備考:
  既存 (date,ticker) は UPSERT します。
USAGE
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage; exit 0
fi

DB=${1:-money_diary.db}

read -rp "日付 YYYY-MM-DD [必須]: " DATE
if [[ ! ${DATE:-} =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then echo "ERROR: 日付形式が不正" >&2; exit 1; fi

read -rp "Ticker [必須]: " TICKER
if [[ -z "${TICKER}" ]]; then echo "ERROR: Ticker は必須" >&2; exit 1; fi

read -rp "数量 qty (例 100) [必須]: " QTY
if [[ ! ${QTY:-} =~ ^[0-9]+(\.[0-9]+)?$ ]]; then echo "ERROR: 数量は数値" >&2; exit 1; fi

read -rp "現地通貨建て価格 price_ccy (例 210.5) [必須]: " PRICE
if [[ ! ${PRICE:-} =~ ^[0-9]+(\.[0-9]+)?$ ]]; then echo "ERROR: 価格は数値" >&2; exit 1; fi

sqlite3 "$DB" <<SQL
INSERT INTO snapshots (date, ticker, qty, price_ccy)
VALUES ('$DATE', '$TICKER', $QTY, $PRICE)
ON CONFLICT(date, ticker) DO UPDATE SET
  qty = excluded.qty,
  price_ccy = excluded.price_ccy;
SQL

echo "Added/Updated snapshot: $DATE $TICKER qty=$QTY price_ccy=$PRICE in $DB"

