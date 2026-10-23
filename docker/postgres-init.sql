-- The compose stack's Postgres (docker-compose.yml), set up once. Postgres
-- runs /docker-entrypoint-initdb.d only when its data directory is empty, the
-- first `docker compose up` on a fresh `pgdata` volume; after that every
-- database below persists on the volume and nothing runs this file again.
-- To start over: docker compose down -v (which also drops the run history).
--
-- crm            the reference project's CRM, a standing mock database:
--                examples/portfolio_project/inputs/seed_crm.sql
--                (issuer_ratings), loaded here once. The app and the seed
--                service read it through connections/crm.yaml
--                (TRACEBI_CRM_URL) and never write it.
-- tracebi_state  the state store (TRACEBI_STATE_URL): run history, sessions,
--                tokens. Never a data database, so never a connection.

CREATE DATABASE crm;
CREATE DATABASE tracebi_state;

\connect crm
\i /seed/seed_crm.sql
