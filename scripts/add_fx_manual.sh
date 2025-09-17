#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<USAGE
使い方: $(basename "$0") [db_path]

説明:
  fx_rates に対し、指定日・通貨の対JPYレートを手動追加/更新します（対話式）。

引数:
  db_path : SQLite DB パス（省略可、既定: money_diary.db）

備考:
  ペアは <通貨>JPY を自動生成します（例: USD -> USDJPY）。
USAGE
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage; exit 0
fi

DB=${1:-money_diary.db}

read -rp "日付 YYYY-MM-DD [必須]: " DATE
if [[ ! ${DATE:-} =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then echo "ERROR: 日付形式が不正" >&2; exit 1; fi

read -rp "通貨3桁 (対JPY) 例: USD [必須]: " CCY
if [[ ! ${CCY:-} =~ ^[A-Za-z]{3}$ ]]; then echo "ERROR: 通貨は3文字 (USD等)" >&2; exit 1; fi
CCY=$(echo "$CCY" | tr '[:lower:]' '[:upper:]')
PAIR="${CCY}JPY"

read -rp "レート (例 145.23) [必須]: " RATE
if [[ ! ${RATE:-} =~ ^[0-9]+(\.[0-9]+)?$ ]]; then echo "ERROR: 数値レートを入力" >&2; exit 1; fi

sqlite3 "$DB" <<SQL
INSERT INTO fx_rates (date, pair, rate)
VALUES ('$DATE', '$PAIR', $RATE)
ON CONFLICT(date, pair) DO UPDATE SET
  rate = excluded.rate;
SQL

echo "Added/Updated FX: $DATE $PAIR=$RATE in $DB"

