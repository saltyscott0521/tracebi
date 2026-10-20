-- The reference project's CRM: one table, the credit team's rating of each
-- issuer it covers. Postgres SQL, deterministic and idempotent (it replaces
-- the table). `python inputs/seed_crm.py` applies it to the database
-- TRACEBI_CRM_URL names; inputs/issuer_ratings.csv is the same twelve rows,
-- the snapshot the transform reads when that variable is unset.
--
-- The issuer name is the key the transform joins on (the name its cleaning
-- parses out of the Schedule of Investments). Lambda Pipeline Co is held
-- but not covered: it lands as Unrated.

DROP TABLE IF EXISTS issuer_ratings;

CREATE TABLE issuer_ratings (
    issuer      text PRIMARY KEY,
    rating      text NOT NULL,
    rating_date date NOT NULL,
    watch       boolean NOT NULL
);

INSERT INTO issuer_ratings (issuer, rating, rating_date, watch) VALUES
    ('Acme Industrial Holdings, LLC', 'B+',   '2025-03-31', false),
    ('Beta Widgets Inc',              'B',    '2025-02-14', false),
    ('Delta Systems Ltd',             'BB-',  '2025-05-09', false),
    ('Epsilon Health Partners, LLC',  'B-',   '2025-04-22', true),
    ('Gamma Software Group, LLC',     'B',    '2025-01-30', false),
    ('Iota Foods Company',            'B+',   '2025-06-12', false),
    ('Kappa Energy Holdings, LLC',    'CCC+', '2025-06-03', true),
    ('Mu Financial Services, LLC',    'BB',   '2025-03-18', false),
    ('Omega Media Group, LLC',        'B-',   '2025-05-27', false),
    ('Sigma Logistics Holdings, LLC', 'B',    '2025-04-08', true),
    ('Theta Retail Brands, LLC',      'B-',   '2025-02-26', true),
    ('Zeta Diagnostics Corporation',  'BB-',  '2025-06-20', false);
