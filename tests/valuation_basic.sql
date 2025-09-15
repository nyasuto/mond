-- prepare data
INSERT INTO assets (ticker, ccy) VALUES ('VTI','USD');
INSERT INTO fx_rates (date, pair, rate) VALUES ('2025-09-15','USDJPY',145.2);
INSERT INTO snapshots (date, ticker, qty, price_ccy) VALUES ('2025-09-15','VTI',2037.88,270.5);

-- assert valuation (rounded for determinism)
SELECT
  date,
  ticker,
  ccy,
  qty,
  price_ccy,
  fx_rate,
  round(value_jpy, 3) AS value_jpy_3dp
FROM v_valuation
ORDER BY date, ticker;

