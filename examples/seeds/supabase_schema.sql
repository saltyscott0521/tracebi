-- TraceBi starter schema for Supabase.
--
-- Paste this whole file into the Supabase SQL Editor and run it once.
-- It creates two tables with a clean foreign key and seeds enough rows to
-- see real numbers in Explore and in a report.
--
-- The shape matches models/supabase.py.example, so the model, its
-- dimension, and its measures work as soon as both are in place.
--
-- Safe to re-run: it drops and recreates.

drop table if exists public.orders;
drop table if exists public.customers;

-- ── Dimension ───────────────────────────────────────────────────────────────
-- customer_id is the primary key, which matters more than it looks: TraceBi
-- refuses to join a dimension whose key is not unique, because a repeated key
-- silently multiplies fact rows and inflates every additive measure.
create table public.customers (
    customer_id integer primary key,
    name        text    not null,
    region      text    not null,
    tier        text    not null
);

-- ── Fact ────────────────────────────────────────────────────────────────────
create table public.orders (
    order_id    integer primary key,
    customer_id integer not null references public.customers (customer_id),
    product     text    not null,
    status      text    not null,
    qty         integer not null,
    revenue     numeric(12, 2) not null,
    cost        numeric(12, 2) not null,
    ordered_at  date    not null
);

create index orders_customer_id_idx on public.orders (customer_id);
create index orders_status_idx      on public.orders (status);

-- ── Seed data ───────────────────────────────────────────────────────────────

insert into public.customers (customer_id, name, region, tier) values
    (1, 'Acme Corp',  'North East', 'enterprise'),
    (2, 'Globex',     'South East', 'smb'),
    (3, 'Initech',    'Midwest',    'smb'),
    (4, 'Umbrella',   'West',       'enterprise'),
    (5, 'Vandelay',   'North East', 'mid-market');

insert into public.orders
    (order_id, customer_id, product, status, qty, revenue, cost, ordered_at)
values
    ( 1, 1, 'Widget A', 'shipped', 120,  3598.80, 2100.00, '2026-01-14'),
    ( 2, 2, 'Widget B', 'shipped',  85,  4249.15, 2800.00, '2026-01-22'),
    ( 3, 3, 'Gadget X', 'open',    200, 19998.00, 14000.00, '2026-02-03'),
    ( 4, 4, 'Widget A', 'shipped',  60,  1799.40, 1050.00, '2026-02-11'),
    ( 5, 1, 'Gadget X', 'open',     95,  9499.05, 6600.00, '2026-02-27'),
    ( 6, 3, 'Widget B', 'shipped', 150, 14998.50, 10500.00, '2026-03-08'),
    ( 7, 2, 'Widget A', 'shipped',  40,  1199.60,  700.00, '2026-03-19'),
    ( 8, 4, 'Gadget X', 'open',    110, 10998.90, 7700.00, '2026-04-02'),
    ( 9, 1, 'Widget B', 'shipped',  75,  3748.25, 2200.00, '2026-04-15'),
    (10, 3, 'Widget A', 'shipped', 180, 17997.00, 12600.00, '2026-05-06'),
    (11, 5, 'Widget B', 'shipped',  95,  4749.05, 2900.00, '2026-05-21'),
    (12, 5, 'Gadget X', 'open',     70,  6999.30, 4900.00, '2026-06-09');

-- ── Row Level Security ──────────────────────────────────────────────────────
-- Supabase enables RLS on new tables by default in some projects. TraceBi
-- connects with the Postgres role in your connection string, which bypasses
-- RLS — but if you later expose these tables through Supabase's own API,
-- add policies deliberately rather than leaving them open.
--
-- Left off here so the starter works immediately:
alter table public.customers disable row level security;
alter table public.orders    disable row level security;

-- ── Sanity check ────────────────────────────────────────────────────────────
-- Expect 12 orders, 5 customers, and a unique dimension key.
select
    (select count(*) from public.orders)    as orders,
    (select count(*) from public.customers) as customers,
    (select count(*) = count(distinct customer_id)
       from public.customers)               as customer_key_is_unique;
