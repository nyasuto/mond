PRAGMA foreign_keys = ON;

-- Core master: assets
CREATE TABLE IF NOT EXISTS assets (
  ticker     TEXT PRIMARY KEY,
  ccy        TEXT NOT NULL CHECK (length(ccy) = 3),
  name       TEXT
);

-- FX rates: pair like 'USDJPY'
CREATE TABLE IF NOT EXISTS fx_rates (
  date TEXT NOT NULL CHECK (date LIKE '____-__-__'),
  pair TEXT NOT NULL,
  rate REAL NOT NULL,
  PRIMARY KEY (date, pair)
);

-- Daily snapshots per asset (qty * price_ccy)
CREATE TABLE IF NOT EXISTS snapshots (
  date       TEXT NOT NULL CHECK (date LIKE '____-__-__'),
  ticker     TEXT NOT NULL,
  qty        REAL NOT NULL CHECK (qty >= 0),
  price_ccy  REAL NOT NULL CHECK (price_ccy >= 0),
  PRIMARY KEY (date, ticker),
  FOREIGN KEY (ticker) REFERENCES assets(ticker) ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_snapshots_ticker_date ON snapshots(ticker, date);

-- Cashflows (dividends, deposits, buys/sells etc.)
CREATE TABLE IF NOT EXISTS cashflows (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  date        TEXT NOT NULL CHECK (date LIKE '____-__-__'),
  ticker      TEXT NOT NULL,
  type        TEXT NOT NULL, -- e.g., DIVIDEND/BUY/SELL/DEPOSIT/WITHDRAWAL
  amount_ccy  REAL NOT NULL,
  ccy         TEXT NOT NULL CHECK (length(ccy) = 3),
  FOREIGN KEY (ticker) REFERENCES assets(ticker) ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_cashflows_date ON cashflows(date);
CREATE INDEX IF NOT EXISTS idx_cashflows_ticker_date ON cashflows(ticker, date);

-- View: valuation in JPY per date and ticker
DROP VIEW IF EXISTS v_valuation;
CREATE VIEW v_valuation AS
SELECT
  s.date,
  s.ticker,
  a.ccy,
  s.qty,
  s.price_ccy,
  CASE WHEN a.ccy = 'JPY' THEN 1.0 ELSE r.rate END AS fx_rate,
  (s.qty * s.price_ccy) * (CASE WHEN a.ccy = 'JPY' THEN 1.0 ELSE r.rate END) AS value_jpy
FROM snapshots s
JOIN assets a ON a.ticker = s.ticker
LEFT JOIN fx_rates r ON r.date = s.date AND r.pair = (a.ccy || 'JPY');
