#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<USAGE
使い方: $(basename "$0") <csv_path> [db_path]

説明:
  fx_rates テーブルへ CSV をインポートします（ヘッダー1行を自動スキップ）。

引数:
  csv_path : 入力CSV（列: date,pair,rate）
  db_path  : SQLite DB パス（省略可、既定: money_diary.db）

例:
  $(basename "$0") data/fx_rates.csv
USAGE
}

CSV=${1:-}
DB=${2:-money_diary.db}

if [[ -z "${CSV}" || ! -f "${CSV}" ]]; then
  usage; echo "ERROR: CSV ファイルを指定してください: $CSV" 1>&2; exit 1
fi

TMP=$(mktemp)
# ヘッダーを除去
tail -n +2 "$CSV" > "$TMP"

sqlite3 "$DB" <<SQL
.mode csv
.import "$TMP" fx_rates
SQL

rm -f "$TMP"
echo "Imported fx_rates from $CSV into $DB"

