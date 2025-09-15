#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<USAGE
使い方: $(basename "$0") [out_csv] [db_path]

説明:
  snapshots テーブルをヘッダー付きCSVでエクスポートします。

引数:
  out_csv : 出力CSVパス（省略可、既定: data/snapshots.csv）
  db_path : SQLite DB パス（省略可、既定: money_diary.db）

例:
  $(basename "$0")
  $(basename "$0") data/snapshots.csv money_diary.db
USAGE
}

OUT=${1:-data/snapshots.csv}
DB=${2:-money_diary.db}

mkdir -p "$(dirname "$OUT")"
sqlite3 -header -csv "$DB" "SELECT * FROM snapshots ORDER BY date, ticker" > "$OUT"
echo "Exported snapshots to $OUT"

