-- %% [markdown]
-- # Phase ① — TRANSFORM, in SQL
--
-- Read the messy Schedule-of-Investments export, do the work a fund-ops
-- analyst (or their agent) actually does — parse prose instrument blobs into
-- issuers, strip trailing position counters, normalise sectors spelled six
-- ways, coerce money stored as strings, dedupe — and SINK the clean,
-- star-shaped result into the warehouse.
--
-- DuckDB SQL, run top to bottom in one fresh connection by
-- `tracebi run-transform holdings_transform`. The contract is not *how* you
-- clean, it is *what lands*: the seven tables and the one view created below.
-- Phase ② (models/) reads those and never sees this file. The checks they must pass sit
-- beside it in holdings_transform.contract.yaml.
--
-- One input sits outside inputs/: the credit team's CRM, a Postgres database
-- (connections/crm.yaml). The line below loads its issuer_ratings table
-- through that connection before the first statement runs, and the SQL reads
-- it as crm.issuer_ratings. With TRACEBI_CRM_URL unset, the committed
-- snapshot stands in, and the certificate records that it did.
--
-- source: crm.issuer_ratings fallback: inputs/issuer_ratings.csv
--
-- This is the file tier: each CREATE OR REPLACE TABLE lands in the warehouse
-- tracebi.yaml names (data/warehouse.duckdb by default). On the object tier
-- a table lands as Parquet instead, with
--   COPY (SELECT …) TO '{{ sink }}/fact_holdings.parquet' (FORMAT PARQUET);
-- Relative paths in reads (inputs/…) resolve against the project root.
--
-- transforms/holdings_transform_pandas.py does the same work in pandas, the
-- escape hatch; both sink identical tables, fingerprint for fingerprint.
-- Idempotent: rerun any time; it replaces the warehouse tables.

-- %% [markdown]
-- ## Cleaning helpers
-- Temporary macros (gone with the connection), one per pandas helper.

-- %%
-- Python's str.strip(): leading and trailing whitespace.
CREATE OR REPLACE TEMP MACRO strip(s) AS regexp_replace(s, '^\s+|\s+$', '', 'g');

-- '$ 8,135,782.69 (a)' → 8135782.69: drop a trailing footnote, then every
-- character that is not a digit, a point or a minus. Unparseable → NULL.
CREATE OR REPLACE TEMP MACRO parse_money(s) AS
    TRY_CAST(strip(regexp_replace(regexp_replace(s, '\s*\([a-z]\)\s*$', ''),
                                  '[^\d.\-]', '', 'g')) AS DOUBLE);

-- A trailing '(2)' position counter, stripped so it never rides along.
CREATE OR REPLACE TEMP MACRO drop_counter(s) AS strip(regexp_replace(s, '\s*\(\d+\)\s*$', ''));

-- Cents, rounded as the pandas transform's numpy floats round: scale by 100,
-- round half to even, scale back. Spelled out because round(x, 2) rounds a
-- tie away from zero (505711.125 → .13, not .12) and round_even(x, 2) does
-- not scale the same way (296054.975 → .98, not .97).
CREATE OR REPLACE TEMP MACRO cents(x) AS round_even(x * 100, 0) / 100;

-- canonical sector ← the six spellings each administrator uses
CREATE OR REPLACE TEMP TABLE sector_canon AS
SELECT * FROM (VALUES
    ('industrials', 'Industrials'), ('industrial', 'Industrials'),
    ('software', 'Software'), ('tech - software', 'Software'),
    ('technology/software', 'Software'),
    ('healthcare', 'Healthcare'), ('health care', 'Healthcare'),
    ('health-care', 'Healthcare'),
    ('consumer', 'Consumer'), ('consumer discretionary', 'Consumer'), ('cons.', 'Consumer'),
    ('energy', 'Energy'), ('oil & gas', 'Energy'),
    ('financials', 'Financials'), ('financial services', 'Financials'), ('fin.', 'Financials')
) AS t(spelling, sector);

-- %% [markdown]
-- ## Parse the raw pull
-- Every column read as text, numbered in file order (`line`): the dedupe
-- keeps the first of a double booking, and the holdings keep the file's
-- order, as the pandas transform does.

-- %%
CREATE OR REPLACE TEMP TABLE raw_holdings AS
SELECT row_number() OVER () AS line, *
FROM read_csv('inputs/holdings.csv', header = true, all_varchar = true);

CREATE OR REPLACE TEMP TABLE parsed AS
SELECT
    line,
    fund,
    -- 'Acme Industrial Holdings, LLC — Senior Secured … (2)' → the name
    -- before the em dash, and the instrument type after it ('' with no dash).
    drop_counter(split_part(coalesce(position, ''), ' — ', 1)) AS issuer,
    CASE WHEN contains(coalesce(position, ''), ' — ')
         THEN drop_counter(substr(position, strpos(position, ' — ') + 3))
         ELSE '' END AS instrument_type,
    coalesce((SELECT c.sector FROM sector_canon c
              WHERE c.spelling = lower(strip(industry))), 'Other') AS sector,
    parse_money(par) AS par,
    parse_money(cost) AS cost,
    parse_money(fair_value) AS fair_value,
    -- 'SOFR + 597' → 597; 'L+7.44%' → 744: a percent spread is points
    -- (×100 to bps), a bare number is already bps. round_even rounds half to
    -- even, as pandas does.
    (SELECT CAST(round_even(CASE WHEN contains(spread, '%')
                                 THEN TRY_CAST(replace(spread, '%', '') AS DOUBLE) * 100
                                 ELSE TRY_CAST(spread AS DOUBLE) END, 0) AS BIGINT)
     FROM (SELECT regexp_replace(replace(rate, ' ', ''), '^[A-Za-z]+\+?', '') AS spread)) AS spread_bps,
    -- three date spellings: 10/20/2031, 2031-03-08, Mar 18, 2028
    CAST(coalesce(try_strptime(maturity, '%m/%d/%Y'),
                  try_strptime(maturity, '%Y-%m-%d'),
                  try_strptime(maturity, '%b %d, %Y')) AS DATE) AS maturity
FROM raw_holdings;

-- %% [markdown]
-- ## Key, dedupe
-- Drop rows we could not key to a real issuer (at least one letter: this
-- rejects an em-dash-only blob and a blanked cell alike), then collapse
-- exact double-booked positions, keeping the first.

-- %%
CREATE OR REPLACE TEMP TABLE keyed AS
SELECT *
FROM parsed
WHERE regexp_matches(issuer, '[A-Za-z]')
QUALIFY row_number() OVER (PARTITION BY fund, issuer, instrument_type, par, fair_value
                           ORDER BY line) = 1;

-- %% [markdown]
-- ## Sink the star: dimensions, then the holdings fact keyed to them

-- %%
CREATE OR REPLACE TABLE dim_fund AS
SELECT row_number() OVER (ORDER BY fund) AS fund_id, fund
FROM (SELECT DISTINCT fund FROM keyed)
ORDER BY fund_id;

CREATE OR REPLACE TABLE dim_issuer AS
SELECT row_number() OVER (ORDER BY issuer, sector) AS issuer_id, issuer, sector
FROM (SELECT DISTINCT issuer, sector FROM keyed)
ORDER BY issuer_id;

-- Each held issuer's CRM rating, and whether the credit team has it on
-- watch. An issuer the CRM does not cover is Unrated, its watch unknown: a
-- row with no rating is a fact about the CRM, so it stays in the book.
CREATE OR REPLACE TEMP TABLE issuer_rating AS
SELECT i.issuer,
       coalesce(r.rating, 'Unrated') AS rating,
       CASE WHEN r.issuer IS NULL THEN 'unknown' WHEN r.watch THEN 'yes' ELSE 'no' END AS watch
FROM (SELECT DISTINCT issuer FROM keyed) i
LEFT JOIN crm.issuer_ratings r USING (issuer);

CREATE OR REPLACE TABLE dim_rating AS
SELECT row_number() OVER (ORDER BY rating, watch) AS rating_id, rating, watch
FROM (SELECT DISTINCT rating, watch FROM issuer_rating)
ORDER BY rating_id;

CREATE OR REPLACE TABLE fact_holdings AS
SELECT row_number() OVER (ORDER BY k.line) AS holding_id,
       f.fund_id, i.issuer_id, d.rating_id, k.instrument_type,
       k.par, k.cost, k.fair_value, k.spread_bps, k.maturity
FROM keyed k
JOIN dim_fund f USING (fund)
JOIN dim_issuer i USING (issuer)
JOIN issuer_rating r USING (issuer)
JOIN dim_rating d ON d.rating = r.rating AND d.watch = r.watch
ORDER BY holding_id;

-- %% [markdown]
-- ## A second fact: the book's cash flows
-- Derived from the holdings themselves (no second raw pull), so the demo
-- stays one input file: a quarterly coupon on alternate quarters (par ×
-- (spread + a 4.3% base rate) / 4), a drawdown on every fourth position and
-- a partial repayment on every fifth, all in 2025. Signed from the fund's
-- side: money lent out is negative, money received positive. It shares
-- dim_fund and dim_issuer with the holdings and adds two dimensions only it
-- reaches (the flow's date and its type), which is what a page needs to show
-- a filter that reaches one fact and not the other.

-- %%
CREATE OR REPLACE TABLE dim_flow_type AS
SELECT CAST(flow_type_id AS BIGINT) AS flow_type_id, flow_type
FROM (VALUES (1, 'Drawdown'), (2, 'Interest'), (3, 'Repayment')) AS t(flow_type_id, flow_type)
ORDER BY flow_type_id;

-- Each flow carries its holding and its place among that holding's flows
-- (seq), so flows that tie on date, fund and issuer keep the order they are
-- generated in: holding by holding, coupons, then drawdown, then repayment.
CREATE OR REPLACE TEMP TABLE flows AS
SELECT h.holding_id, q AS seq, h.fund_id, h.issuer_id,
       last_day(make_date(2025, 3 * q + 3, 1)) AS flow_date, 2 AS flow_type_id,
       cents(h.par * (h.spread_bps / 10000 + 0.043) / 4) AS amount
FROM fact_holdings h, range(4) AS r(q)
WHERE h.par IS NOT NULL AND h.spread_bps IS NOT NULL AND (h.holding_id + q) % 2 = 0
UNION ALL
SELECT holding_id, 4, fund_id, issuer_id,
       make_date(2025, CAST(holding_id % 12 + 1 AS INTEGER), 1), 1, -cents(par * 0.10)
FROM fact_holdings
WHERE par IS NOT NULL AND spread_bps IS NOT NULL AND holding_id % 4 = 1
UNION ALL
SELECT holding_id, 5, fund_id, issuer_id,
       make_date(2025, CAST(holding_id % 12 + 1 AS INTEGER), 15), 3, cents(par * 0.05)
FROM fact_holdings
WHERE par IS NOT NULL AND spread_bps IS NOT NULL AND holding_id % 5 = 0;

CREATE OR REPLACE TABLE fact_cashflows AS
SELECT row_number() OVER (ORDER BY flow_date, fund_id, issuer_id, holding_id, seq) AS cashflow_id,
       fund_id, issuer_id, flow_date, CAST(flow_type_id AS BIGINT) AS flow_type_id, amount
FROM flows
ORDER BY cashflow_id;

CREATE OR REPLACE TABLE dim_date AS
SELECT DISTINCT flow_date FROM fact_cashflows ORDER BY flow_date;

-- %% [markdown]
-- ## A sink view: the book by sector
-- Materialize the facts you aggregate, view the derivations. This one is a
-- definition kept in the warehouse, not a copy of rows: the model reads it as
-- it reads a table, and it always agrees with the two tables it names. A view
-- may read only the warehouse's own tables and views, never crm.… or a file.
-- The sum is rounded to the cent: the last bits of a float sum depend on the
-- order the rows are added in, and the pandas form adds them in another.
-- (No cents() here: a view cannot call a TEMP MACRO, which is gone when it
-- is read.)

-- %%
CREATE OR REPLACE VIEW fact_holdings_by_sector AS
SELECT i.sector,
       count(DISTINCT h.issuer_id) AS issuers,
       count(*) AS positions,
       round(sum(h.fair_value), 2) AS fair_value
FROM fact_holdings h
JOIN dim_issuer i USING (issuer_id)
GROUP BY i.sector
ORDER BY i.sector;
