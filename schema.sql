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

-- View: attribution of daily change into price, fx, cross, and flow
DROP VIEW IF EXISTS v_attribution;
CREATE VIEW v_attribution AS
WITH s AS (
  SELECT
    s.date,
    s.ticker,
    s.qty AS q1,
    s.price_ccy AS p1,
    LAG(s.qty) OVER (PARTITION BY s.ticker ORDER BY s.date) AS q0,
    LAG(s.price_ccy) OVER (PARTITION BY s.ticker ORDER BY s.date) AS p0,
    LAG(s.date) OVER (PARTITION BY s.ticker ORDER BY s.date) AS d0
  FROM snapshots s
),
base AS (
  SELECT
    s.date,
    s.ticker,
    a.ccy,
    s.q0,
    s.q1,
    s.p0,
    s.p1,
    CASE WHEN a.ccy = 'JPY' THEN 1.0 ELSE f0.rate END AS r0,
    CASE WHEN a.ccy = 'JPY' THEN 1.0 ELSE f1.rate END AS r1
  FROM s
  JOIN assets a
    ON a.ticker = s.ticker
  LEFT JOIN fx_rates f1
    ON a.ccy <> 'JPY'
   AND f1.date = s.date
   AND f1.pair = (a.ccy || 'JPY')
  LEFT JOIN fx_rates f0
    ON a.ccy <> 'JPY'
   AND f0.date = s.d0
   AND f0.pair = (a.ccy || 'JPY')
  WHERE s.q0 IS NOT NULL
    AND (a.ccy = 'JPY' OR (f1.rate IS NOT NULL AND f0.rate IS NOT NULL))
)
SELECT
  date,
  ticker,
  (q1 * p1 * r1 - q0 * p0 * r0) AS delta_total,
  (q0 * (p1 - p0) * r0)         AS delta_price,
  (q0 * p0 * (r1 - r0))         AS delta_fx,
  (q0 * (p1 - p0) * (r1 - r0))  AS delta_cross,
  ((q1 - q0) * p1 * r1)         AS flow
FROM base
UNION ALL
SELECT
  date,
  'PORTFOLIO' AS ticker,
  SUM(q1 * p1 * r1 - q0 * p0 * r0) AS delta_total,
  SUM(q0 * (p1 - p0) * r0)         AS delta_price,
  SUM(q0 * p0 * (r1 - r0))         AS delta_fx,
  SUM(q0 * (p1 - p0) * (r1 - r0))  AS delta_cross,
  SUM((q1 - q0) * p1 * r1)         AS flow
FROM base
GROUP BY date
;
