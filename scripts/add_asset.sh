#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<USAGE
使い方: $(basename "$0") [db_path]

説明:
  assets に銘柄を手動追加/更新します（対話式）。

引数:
  db_path : SQLite DB パス（省略可、既定: money_diary.db）

備考:
  既存ティッカーは UPSERT（ccy/name を更新）します。
USAGE
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage; exit 0
fi

DB=${1:-money_diary.db}

read -rp "Ticker (例: VTI): " TICKER
if [[ -z "${TICKER}" ]]; then echo "ERROR: Ticker は必須" >&2; exit 1; fi

read -rp "通貨3桁 (例: USD/JPY) [必須]: " CCY
if [[ ! ${CCY:-} =~ ^[A-Za-z]{3}$ ]]; then echo "ERROR: 通貨は3文字 (USD等)" >&2; exit 1; fi
CCY=$(echo "$CCY" | tr '[:lower:]' '[:upper:]')

read -rp "名称 (任意): " NAME

sqlite3 "$DB" <<SQL
INSERT INTO assets (ticker, ccy, name)
VALUES ('$TICKER', '$CCY', ${NAME:+quote('$NAME')} )
ON CONFLICT(ticker) DO UPDATE SET
  ccy = excluded.ccy,
  name = excluded.name;
SQL

echo "Added/Updated asset: $TICKER ($CCY) in $DB"

