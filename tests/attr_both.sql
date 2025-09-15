-- Price and FX change (USD asset), q constant
INSERT INTO assets (ticker, ccy) VALUES ('VTI','USD');
INSERT INTO fx_rates (date, pair, rate) VALUES ('2025-09-14','USDJPY',140.0);
INSERT INTO fx_rates (date, pair, rate) VALUES ('2025-09-15','USDJPY',145.0);
INSERT INTO snapshots (date, ticker, qty, price_ccy) VALUES ('2025-09-14','VTI',100,200);
INSERT INTO snapshots (date, ticker, qty, price_ccy) VALUES ('2025-09-15','VTI',100,210);

SELECT date,
       ticker,
       round(delta_total, 3) AS total,
       round(delta_price, 3) AS price,
       round(delta_fx, 3)    AS fx,
       round(delta_cross, 3) AS cross,
       round(flow, 3)        AS flow
FROM v_attribution
ORDER BY ticker;

