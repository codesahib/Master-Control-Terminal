-- Master Terminal data integrity checks. Read-only.
--   psql "$DATABASE_URL" -f scripts/audit/db_checks.sql
-- Each check prints "check | count"; anything non-zero (except row counts / enum usage) needs a look.
\pset footer off
\echo '== row counts'
SELECT 'accounts' AS t, count(*) FROM accounts UNION ALL SELECT 'platforms', count(*) FROM platforms
UNION ALL SELECT 'categories', count(*) FROM categories UNION ALL SELECT 'instruments', count(*) FROM instruments
UNION ALL SELECT 'transactions', count(*) FROM transactions UNION ALL SELECT 'transaction_fundings', count(*) FROM transaction_fundings
UNION ALL SELECT 'holdings_snapshots', count(*) FROM holdings_snapshots UNION ALL SELECT 'market_prices', count(*) FROM market_prices
UNION ALL SELECT 'contribution_limits', count(*) FROM contribution_limits UNION ALL SELECT 'audit_logs', count(*) FROM audit_logs;

\echo '== integrity (all should be 0)'
SELECT 'transactions with null account_id' AS check, count(*) FROM transactions WHERE account_id IS NULL
UNION ALL SELECT 'orphan transactions.account_id', count(*) FROM transactions t WHERE account_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM accounts a WHERE a.id = t.account_id)
UNION ALL SELECT 'orphan transactions.platform_id', count(*) FROM transactions t WHERE platform_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM platforms p WHERE p.id = t.platform_id)
UNION ALL SELECT 'orphan transactions.instrument_id', count(*) FROM transactions t WHERE instrument_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM instruments i WHERE i.id = t.instrument_id)
UNION ALL SELECT 'orphan transactions.category_id', count(*) FROM transactions t WHERE category_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM categories c WHERE c.id = t.category_id)
UNION ALL SELECT 'orphan fundings (transaction or contribution missing)', count(*) FROM transaction_fundings f
  WHERE NOT EXISTS (SELECT 1 FROM transactions t WHERE t.id = f.transaction_id) OR NOT EXISTS (SELECT 1 FROM transactions t WHERE t.id = f.contribution_id)
UNION ALL SELECT 'orphan market_prices', count(*) FROM market_prices m WHERE NOT EXISTS (SELECT 1 FROM instruments i WHERE i.id = m.instrument_id)
UNION ALL SELECT 'duplicate contribution_limits (account, year)', count(*) FROM (SELECT 1 FROM contribution_limits GROUP BY account_id, tax_year HAVING count(*) > 1) d
UNION ALL SELECT 'duplicate categories (case-insensitive)', count(*) FROM (SELECT 1 FROM categories GROUP BY lower(broad), lower(precise) HAVING count(*) > 1) d
UNION ALL SELECT 'duplicate instruments symbol (case-insensitive)', count(*) FROM (SELECT 1 FROM instruments GROUP BY lower(symbol) HAVING count(*) > 1) d
UNION ALL SELECT 'extra market_prices (same instrument, same UTC day)', coalesce(sum(n - 1), 0) FROM (SELECT count(*) n FROM market_prices GROUP BY instrument_id, (priced_at::date) HAVING count(*) > 1) d
UNION ALL SELECT 'funding rows pointing at non-funding types', count(*) FROM transaction_fundings f JOIN transactions s ON s.id = f.contribution_id
  WHERE s.transaction_type NOT IN ('contribution', 'dividend_interest', 'transfer')
UNION ALL SELECT 'legacy contribution_id without funding row', count(*) FROM transactions t
  WHERE t.contribution_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM transaction_fundings f WHERE f.transaction_id = t.id)
UNION ALL SELECT 'negative amount or fees', count(*) FROM transactions WHERE amount < 0 OR fees < 0 OR source_amount < 0
UNION ALL SELECT 'bad currency codes', count(*) FROM transactions WHERE currency !~ '^[A-Z]{3}$' OR source_currency !~ '^[A-Z]{3}$' OR fee_currency !~ '^[A-Z]{3}$'
UNION ALL SELECT 'buy/sell/reinvest without quantity', count(*) FROM transactions
  WHERE transaction_type IN ('investment_buy', 'investment_sell', 'dividend_reinvestment') AND instrument_id IS NOT NULL AND quantity IS NULL
UNION ALL SELECT 'transfers without source platform', count(*) FROM transactions WHERE transaction_type = 'transfer' AND source_platform_id IS NULL;

\echo '== funding sources over-allocated (should be empty)'
SELECT s.id AS source_id, s.transaction_type, s.amount AS source_amount, sum(f.amount) AS allocated
FROM transaction_fundings f JOIN transactions s ON s.id = f.contribution_id
GROUP BY s.id, s.transaction_type, s.amount HAVING sum(f.amount) > s.amount + 0.005;

\echo '== instruments marked inactive or manual that still have priced history'
SELECT i.symbol, i.provider_symbol, i.is_active, i.asset_type, count(m.id) AS prices
FROM instruments i JOIN market_prices m ON m.instrument_id = i.id
WHERE NOT i.is_active OR i.asset_type = 'manual' GROUP BY i.id ORDER BY i.symbol;

\echo '== enum values in use'
SELECT transaction_type, count(*) FROM transactions GROUP BY 1 ORDER BY 1;

\echo '== transactions per account and currency'
SELECT a.name AS account, t.currency, count(*) FROM transactions t LEFT JOIN accounts a ON a.id = t.account_id GROUP BY 1, 2 ORDER BY 1, 2;

\echo '== latest price age per instrument with a position (hours, oldest first)'
SELECT i.symbol, round(extract(epoch FROM (now() - max(m.priced_at))) / 3600) AS hours_old
FROM instruments i JOIN market_prices m ON m.instrument_id = i.id
WHERE EXISTS (SELECT 1 FROM transactions t WHERE t.instrument_id = i.id AND t.quantity IS NOT NULL)
GROUP BY i.symbol ORDER BY hours_old DESC LIMIT 10;
