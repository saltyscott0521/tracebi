-- %% [markdown]
-- # Phase ① — TRANSFORM, in SQL: Wealth Management
--
-- Read the core-banking system's six tables, clean what its export gets
-- wrong, and SINK a star schema: positions and a year of account activity,
-- each keyed to the client, branch, product and account it belongs to.
--
-- DuckDB SQL, run top to bottom in one fresh connection by
-- `tracebi run-transform wealth_transform`. The contract is the six tables
-- created below; phase ② (models/wealth_model.yaml) reads them and never sees
-- this file. The checks they must pass sit beside it in
-- wealth_transform.contract.yaml.
--
-- The input is the bank (connections/bank.yaml): the SQLite file that ships,
-- inputs/bank.sqlite, unless TRACEBI_BANK_URL names another database. The
-- lines below load each table through that connection before the first
-- statement runs; the SQL reads them as bank.<table>.
--
-- source: bank.branches
-- source: bank.clients
-- source: bank.products
-- source: bank.accounts
-- source: bank.holdings
-- source: bank.activities
--
-- Each CREATE OR REPLACE TABLE lands in the warehouse tracebi.yaml names
-- (data/warehouse.duckdb), beside the other models' tables, so each name
-- carries a wealth_ prefix (the portfolio has its own fact_holdings).
-- Idempotent: rerun any time; it replaces the warehouse tables.

-- %% [markdown]
-- ## Methodology
--
-- The client segment is spelled several ways ("Affluent", " AFFLUENT") and
-- is folded to lower case; a spelling outside retail, affluent and private
-- stops the run. Market values are text with thousands separators and are
-- read as numbers. An activity posted twice, identical in every column, is
-- kept once. Holdings and activities name only the account; each gains the
-- account's client and that client's branch, so a report can slice either
-- fact by client, branch, product or account.

-- %%
CREATE OR REPLACE TEMP MACRO strip(s) AS regexp_replace(s, '^\s+|\s+$', '', 'g');

-- %% [markdown]
-- ## Dimensions

-- %%
CREATE OR REPLACE TABLE wealth_dim_branch AS
SELECT branch_id, branch, region, manager
FROM bank.branches
ORDER BY branch_id;

CREATE OR REPLACE TABLE wealth_dim_client AS
SELECT client_id, name,
       CASE WHEN lower(strip(segment)) IN ('retail', 'affluent', 'private')
            THEN lower(strip(segment))
            ELSE error('unknown segment spelling: ' || segment) END AS segment,
       risk_profile, advisor, branch_id
FROM bank.clients
ORDER BY client_id;

CREATE OR REPLACE TABLE wealth_dim_product AS
SELECT product_id, ticker, product_name, asset_class, risk_rating, expense_ratio_bps
FROM bank.products
ORDER BY product_id;

CREATE OR REPLACE TABLE wealth_dim_account AS
SELECT account_id, client_id, account_type, opened
FROM bank.accounts
ORDER BY account_id;

-- %% [markdown]
-- ## Facts
-- A left join, so a position on an account the bank does not list lands
-- with no client rather than vanishing; the contract's not_null check
-- then stops it.

-- %%
CREATE OR REPLACE TABLE wealth_fact_holdings AS
SELECT h.holding_id, h.account_id, a.client_id, c.branch_id, h.product_id, h.units,
       -- '12,345.67' → 12345.67
       CAST(replace(h.market_value, ',', '') AS DOUBLE) AS market_value,
       h.cost_basis
FROM bank.holdings h
LEFT JOIN wealth_dim_account a ON a.account_id = h.account_id
LEFT JOIN wealth_dim_client c ON c.client_id = a.client_id
ORDER BY h.holding_id;

-- DISTINCT drops the exact repeat only; two different rows under one
-- activity_id would both land, and the contract's unique check stops them.
CREATE OR REPLACE TABLE wealth_fact_activities AS
SELECT v.activity_id, v.account_id, a.client_id, c.branch_id, v.product_id,
       v.trade_date, v.activity_type, v.units, v.amount
FROM (SELECT DISTINCT * FROM bank.activities) v
LEFT JOIN wealth_dim_account a ON a.account_id = v.account_id
LEFT JOIN wealth_dim_client c ON c.client_id = a.client_id
ORDER BY v.activity_id;
