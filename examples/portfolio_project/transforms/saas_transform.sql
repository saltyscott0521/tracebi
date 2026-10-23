-- %% [markdown]
-- # Phase ① — TRANSFORM, in SQL: SaaS subscriptions
--
-- Read the billing system's subscriptions, normalise plan and status
-- spellings against its price list, and SINK a star schema: one row per
-- account per month.
--
-- DuckDB SQL, run top to bottom in one fresh connection by
-- `tracebi run-transform saas_transform`. The contract is the four tables
-- created below; phase ② (models/saas_model.yaml) reads them and never sees
-- this file. The checks they must pass sit beside it in
-- saas_transform.contract.yaml.
--
-- The input is the billing system (connections/billing.yaml): the SQLite
-- file that ships, inputs/billing.sqlite, unless TRACEBI_BILLING_URL names
-- another database. The lines below load its two tables through that
-- connection before the first statement runs; the SQL reads them as
-- billing.subscriptions and billing.plans.
--
-- source: billing.subscriptions
-- source: billing.plans
--
-- Each CREATE OR REPLACE TABLE lands in the warehouse tracebi.yaml names
-- (data/warehouse.duckdb), beside the portfolio's and the housing model's
-- tables. Idempotent: rerun any time; it replaces the warehouse tables.

-- %% [markdown]
-- ## Methodology
--
-- The subscriptions table is one row per account per month, as exported:
-- plans and statuses spelled several ways, money stored as text, a
-- duplicated account-month, and one row with no account id. Unkeyed rows are dropped. Ending MRR
-- is zero in a churned or inactive month. `starting` is 1 when the prior
-- month was active, or when the month is the account's cohort.

-- %%
CREATE OR REPLACE TEMP MACRO strip(s) AS regexp_replace(s, '^\s+|\s+$', '', 'g');

-- Every column is text as exported; subscription_id numbers the rows in
-- export order (`line`), so the dedupe keeps the first of a duplicated
-- account-month.
CREATE OR REPLACE TEMP TABLE raw_subscriptions AS
SELECT subscription_id AS line, * EXCLUDE (subscription_id)
FROM billing.subscriptions;

-- %% [markdown]
-- ## Clean
-- Drop unkeyed rows, dedupe account-months, then normalise. A plan is
-- matched to the price list by its code (billing.plans); a plan or status
-- spelled some way not listed stops the run rather than landing as a new
-- plan.

-- %%
CREATE OR REPLACE TEMP TABLE keyed AS
SELECT line, CAST(account_id AS BIGINT) AS account_id,
       strip(month) AS month, strip(cohort) AS cohort, plan, status, mrr
FROM raw_subscriptions
WHERE account_id IS NOT NULL
QUALIFY row_number() OVER (PARTITION BY CAST(account_id AS BIGINT), strip(month)
                           ORDER BY line) = 1;

CREATE OR REPLACE TEMP TABLE cleaned AS
SELECT account_id, month, cohort,
       CASE WHEN p.plan IS NOT NULL THEN p.plan
            ELSE error('unknown plan spelling ' || k.plan || '; expected a plan_code '
                       || 'in billing.plans') END AS plan,
       CASE WHEN lower(strip(status)) IN ('active', 'churned', 'inactive')
            THEN lower(strip(status))
            ELSE error('unknown status spelling: ' || status) END AS status,
       -- '$1,149' → 1149.0; ending MRR is zero in a month that is not active.
       CASE WHEN lower(strip(status)) = 'active'
            THEN CAST(regexp_replace(mrr, '[$,]', '', 'g') AS DOUBLE)
            ELSE 0.0 END AS mrr
FROM keyed k
LEFT JOIN billing.plans p ON p.plan_code = lower(strip(k.plan));

-- %% [markdown]
-- ## Shape: dimensions, then the account-month fact
-- `starting` reads the account's previous month in month order.

-- %%
CREATE OR REPLACE TEMP TABLE shaped AS
SELECT account_id, month, cohort, plan, mrr,
       CAST(status = 'active' AS BIGINT) AS active,
       CAST(status = 'churned' AS BIGINT) AS churned,
       CAST(coalesce(lag(status = 'active') OVER (PARTITION BY account_id ORDER BY month), false)
            OR month = cohort AS BIGINT) AS starting
FROM cleaned;

CREATE OR REPLACE TABLE dim_month AS
SELECT row_number() OVER (ORDER BY month) - 1 AS month_id, month
FROM (SELECT DISTINCT month FROM shaped)
ORDER BY month_id;

CREATE OR REPLACE TABLE dim_plan AS
SELECT row_number() OVER (ORDER BY plan) - 1 AS plan_id, plan
FROM (SELECT DISTINCT plan FROM shaped)
ORDER BY plan_id;

CREATE OR REPLACE TABLE dim_cohort AS
SELECT row_number() OVER (ORDER BY cohort) - 1 AS cohort_id, cohort
FROM (SELECT DISTINCT cohort FROM shaped)
ORDER BY cohort_id;

CREATE OR REPLACE TABLE fact_account_month AS
SELECT s.account_id, m.month_id, p.plan_id, c.cohort_id,
       s.mrr, s.active, s.churned, s.starting
FROM shaped s
JOIN dim_month m USING (month)
JOIN dim_plan p USING (plan)
JOIN dim_cohort c USING (cohort)
ORDER BY s.account_id, s.month;
