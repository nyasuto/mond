#!/usr/bin/env python3
"""Fetch FX rates via Yahoo Finance API and upsert into fx_rates."""
import argparse
import datetime as dt
import json
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from typing import Dict

BASE_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&period1={start}&period2={end}"


def to_epoch(d: dt.date) -> int:
    return int(time.mktime(dt.datetime(d.year, d.month, d.day, 0, 0).timetuple()))


def fetch_history(symbol: str, start: dt.date, end: dt.date) -> Dict[str, float]:
    url = BASE_URL.format(symbol=symbol, start=to_epoch(start), end=to_epoch(end + dt.timedelta(days=1)))
    req = urllib.request.Request(url, headers={"User-Agent": "MoneyDiaryFXFetcher/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.load(resp)
    except (urllib.error.URLError, TimeoutError) as exc:  # type: ignore[arg-type]
        raise RuntimeError(f"Yahoo Finance request failed: {exc}") from exc

    result = (data.get("chart") or {}).get("result") or []
    if not result:
        error = (data.get("chart") or {}).get("error")
        raise RuntimeError(f"No data returned for {symbol}: {error}")

    result = result[0]
    timestamps = result.get("timestamp") or []
    quotes = (result.get("indicators") or {}).get("quote") or []
    if not timestamps or not quotes:
        raise RuntimeError(f"Missing time series for {symbol}")

    closes = quotes[0].get("close") or []
    rates: Dict[str, float] = {}
    for ts, close in zip(timestamps, closes):
        if close is None:
            continue
        date = dt.datetime.utcfromtimestamp(ts).date().isoformat()
        rates[date] = float(close)
    return rates


def upsert(conn: sqlite3.Connection, date: str, pair: str, rate: float) -> None:
    conn.execute(
        """
        INSERT INTO fx_rates (date, pair, rate)
        VALUES (?, ?, ?)
        ON CONFLICT(date, pair) DO UPDATE SET rate = excluded.rate
        """,
        (date, pair, rate),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("start", nargs="?", default=None, help="Start date YYYY-MM-DD (default: today)")
    parser.add_argument("end", nargs="?", default=None, help="End date YYYY-MM-DD (default: same as start)")
    parser.add_argument("base", nargs="?", default="USD", help="Base currency (default: USD)")
    parser.add_argument("symbols", nargs="*", default=["JPY"], help="Target currencies (default: JPY)")
    parser.add_argument("--db", dest="db_path", default="money_diary.db", help="SQLite DB path")
    parser.add_argument("--dry-run", action="store_true", help="Do not write to DB, just print rates")
    return parser.parse_args()


def main():
    args = parse_args()

    today = dt.date.today()
    if args.start is None:
        start = today
    else:
        start = dt.date.fromisoformat(args.start)

    if args.end is None:
        end = start
    else:
        end = dt.date.fromisoformat(args.end)

    if end < start:
        raise SystemExit("End date must be on or after start date")

    base = args.base.upper()
    targets = [s.upper() for s in args.symbols]

    all_rates: Dict[str, Dict[str, float]] = defaultdict(dict)
    for target in targets:
        symbol = f"{base}{target}=X"
        try:
            history = fetch_history(symbol, start, end)
        except RuntimeError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            raise SystemExit(1)
        for date, rate in history.items():
            all_rates[date][target] = rate
        print(f"Fetched {len(history)} rates for {symbol}")

    dates_sorted = sorted(all_rates.keys())
    for date in dates_sorted:
        pairs = all_rates[date]
        for target, rate in pairs.items():
            print(f"{date} {base}{target} = {rate}")

    if args.dry_run:
        return

    conn = sqlite3.connect(args.db_path)
    try:
        with conn:
            for date in dates_sorted:
                for target, rate in all_rates[date].items():
                    pair = f"{base}{target}"
                    upsert(conn, date, pair, rate)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
