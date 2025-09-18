INSERT INTO assets (ticker, ccy) VALUES ('VTI','USD');
INSERT INTO assets (ticker, ccy) VALUES ('TOPIX','JPY');

INSERT INTO fx_rates (date, pair, rate) VALUES ('2023-12-29','USDJPY',140.0);
INSERT INTO fx_rates (date, pair, rate) VALUES ('2023-12-30','USDJPY',142.0);

INSERT INTO snapshots (date, ticker, qty, price_ccy) VALUES ('2023-12-29','VTI',10,200);
INSERT INTO snapshots (date, ticker, qty, price_ccy) VALUES ('2023-12-29','TOPIX',5,100);
INSERT INTO snapshots (date, ticker, qty, price_ccy) VALUES ('2023-12-30','VTI',11,205);
INSERT INTO snapshots (date, ticker, qty, price_ccy) VALUES ('2023-12-30','TOPIX',5,101);

SELECT
  date,
  round(total_value_jpy, 3) AS total_value_jpy
FROM v_portfolio_total
ORDER BY date;
