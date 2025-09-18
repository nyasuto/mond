#!/usr/bin/env python3
"""Fetch daily close prices for assets and upsert into asset_prices."""
import argparse
import datetime as dt
import json
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from typing import Dict, List, Tuple

BASE_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&period1={start}&period2={end}"
RETRY_STATUS = {429, 502, 503}


def to_epoch(day: dt.date) -> int:
    return int(time.mktime(dt.datetime(day.year, day.month, day.day, 0, 0).timetuple()))


def fetch_history(symbol: str, start: dt.date, end: dt.date) -> Dict[str, float]:
    url = BASE_URL.format(symbol=symbol, start=to_epoch(start), end=to_epoch(end + dt.timedelta(days=1)))
    req = urllib.request.Request(url, headers={"User-Agent": "MoneyDiaryPriceFetcher/1.0"})

    backoff = 2.0
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.load(resp)
            break
        except urllib.error.HTTPError as exc:
            if exc.code in RETRY_STATUS and attempt < 3:
                time.sleep(backoff)
                backoff *= 2
                continue
            raise RuntimeError(f"Yahoo Finance request failed ({symbol}): HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:  # type: ignore[arg-type]
            if attempt < 3:
                time.sleep(backoff)
                backoff *= 2
                continue
            raise RuntimeError(f"Yahoo Finance request failed ({symbol}): {exc}") from exc

    result = (data.get("chart") or {}).get("result") or []
    if not result:
        error = (data.get("chart") or {}).get("error")
        raise RuntimeError(f"No data returned for {symbol}: {error}")

    node = result[0]
    timestamps = node.get("timestamp") or []
    quotes = (node.get("indicators") or {}).get("quote") or []
    if not timestamps or not quotes:
        raise RuntimeError(f"Missing time series for {symbol}")

    closes = quotes[0].get("close") or []
    history: Dict[str, float] = {}
    for ts, close in zip(timestamps, closes):
        if close is None:
            continue
        date = dt.datetime.utcfromtimestamp(ts).date().isoformat()
        history[date] = float(close)
    return history


def ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS asset_prices (
          date   TEXT NOT NULL CHECK (date LIKE '____-__-__'),
          ticker TEXT NOT NULL,
          close  REAL NOT NULL CHECK (close >= 0),
          PRIMARY KEY (date, ticker)
        )
        """
    )


def upsert(conn: sqlite3.Connection, date: str, ticker: str, close: float) -> None:
    conn.execute(
        """
        INSERT INTO asset_prices (date, ticker, close)
        VALUES (?, ?, ?)
        ON CONFLICT(date, ticker) DO UPDATE SET close = excluded.close
        """,
        (date, ticker, close),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("start", help="Start date YYYY-MM-DD")
    parser.add_argument("end", nargs="?", default=None, help="End date YYYY-MM-DD (default: start)" )
    parser.add_argument(
        "tickers",
        nargs="+",
        help="Ticker symbols. Use TICKER or TICKER=YAHOO_SYMBOL (default: same as ticker)",
    )
    parser.add_argument("--db", dest="db_path", default="money_diary.db", help="SQLite DB path")
    parser.add_argument("--dry-run", action="store_true", help="Print rates only")
    return parser.parse_args()


def main():
    args = parse_args()

    start = dt.date.fromisoformat(args.start)
    if args.end:
        end = dt.date.fromisoformat(args.end)
    else:
        end = start

    if end < start:
        raise SystemExit("End date must be on or after start date")

    pairs: List[Tuple[str, str]] = []  # (store_ticker, yahoo_symbol)
    for spec in args.tickers:
        if "=" in spec:
            store, symbol = spec.split("=", 1)
        else:
            store = symbol = spec
        store = store.strip()
        symbol = symbol.strip()
        if not store or not symbol:
            raise SystemExit(f"Invalid ticker specification: {spec}")
        pairs.append((store, symbol))

    all_prices = defaultdict(dict)  # date -> ticker -> close

    for store_ticker, yahoo_symbol in pairs:
        try:
            history = fetch_history(yahoo_symbol, start, end)
        except RuntimeError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            raise SystemExit(1)
        print(f"Fetched {len(history)} prices for {store_ticker} (symbol {yahoo_symbol})")
        for date, close in history.items():
            all_prices[date][store_ticker] = close

    dates = sorted(all_prices.keys())
    for date in dates:
        for ticker, close in all_prices[date].items():
            print(f"{date} {ticker} = {close}")

    if args.dry_run:
        return

    conn = sqlite3.connect(args.db_path)
    try:
        with conn:
            ensure_table(conn)
            for date in dates:
                for ticker, close in all_prices[date].items():
                    upsert(conn, date, ticker, close)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
