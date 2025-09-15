#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
TEST_DIR="$ROOT_DIR/tests"
OUT_DIR="$TEST_DIR/out"
EXP_DIR="$TEST_DIR/expected"
SCHEMA="$ROOT_DIR/schema.sql"

mkdir -p "$OUT_DIR"

green() { printf "\033[32m%s\033[0m\n" "$*"; }
red()   { printf "\033[31m%s\033[0m\n" "$*"; }

fail=0
total=0

for sql in "$TEST_DIR"/*.sql; do
  [ -f "$sql" ] || continue
  total=$((total+1))
  name=$(basename "$sql" .sql)
  db="$OUT_DIR/$name.db"
  out="$OUT_DIR/$name.csv"
  exp="$EXP_DIR/$name.csv"

  rm -f "$db" "$out"
  sqlite3 "$db" < "$SCHEMA"
  # Run test SQL and capture CSV with headers
  if ! sqlite3 -cmd ".headers on" -cmd ".mode csv" "$db" < "$sql" > "$out"; then
    red "ERROR running $name.sql"
    fail=$((fail+1))
    continue
  fi
  # Normalize line endings (strip CR)
  tmp="$out.tmp"
  tr -d '\r' < "$out" > "$tmp" && mv "$tmp" "$out"
  if ! diff -u "$exp" "$out"; then
    red "FAIL: $name"
    fail=$((fail+1))
  else
    green "PASS: $name"
  fi
done

echo "-----"
echo "Total: $total, Failed: $fail"
exit $fail
