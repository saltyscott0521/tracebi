# The three-phase workflow

**TraceBi takes data from messy to reportable in three folders, each with its
own cadence, separated by [[freeze-points|freeze points]].**

```
inputs/  →  transforms/  →  [ warehouse ]  →  models/  →  reports/
   ⓪            ①            freeze          ②            ③
```

Each phase has one job, and the phases are deliberately decoupled so the slow
one never blocks the fast one.

---

> **In the app** there are four places. **Reports** is where it opens: the library, every
> report in its folder with whether its numbers still reproduce, narrowed to a model by a
> chip. **Ask** puts a question to one model. **Data** opens on the board: these three
> stages as lanes, sources first and reports last, with the warehouse between Transform and
> Model, the freeze point it is. A model's page draws it as a line: **Transform** (the
> pipeline that rebuilds its warehouse, and what the sink contract says about it),
> **Model** (its tables, joins and measures) and **Reports** (what reads it); **Refresh
> data**, on the Transform tab, runs the pipeline. **Review** holds what needs attention (a failed
> refresh, a build that needs a look, a request to publish), then drafts, then **Verify a
> file** (check a report file from anywhere); **History** (what ran) is one link away. Reports and Ask only ever ask the
> model; see [[models-and-connectors]].

## ① Transform — `transforms/`

SQL by default: `transforms/<name>.sql`, DuckDB statements run top to bottom
in one fresh connection. Pull the queries, do the real analysis — window
functions, prose parsing, cleaning, dedupe — then **sink** clean star-schema
tables into the warehouse. When the work outgrows SQL, the escape hatch is
pandas or polars (a `.py` or `.ipynb`); both forms run with
`tracebi run-transform`, which says which one ran.

The framework does not constrain this phase. The contract is not *how* you
clean; it is **what lands**: the named tables at the end of the script. The
[[sink-contracts|sink contract]] that checks them sits beside the transform, in
`<name>.contract.yaml`.

"Pull the queries" has a concrete form when the input is a database rather
than a file. A [[connections-yaml|connection]] declares it
(`connections/crm.yaml`, with the URL kept in an environment variable), and a
header line `-- source: crm.issuer_ratings` in the SQL loads that table
through the connection before the first statement, so the transform reads it
as `crm.issuer_ratings` beside its CSVs. The certificate records each load's
fingerprint under `sources`, so the sink satisfied its contract against named
inputs, and `tracebi verify --contracts` says when one has moved since. The
reference project's ratings come from a Postgres CRM this way, with a committed
CSV snapshot standing in (and the certificate saying so) when no database is
configured. → [[transform-sql]]

→ [[transform]]

*Freeze: `data/warehouse.duckdb` — materialized tables.*

## ② Model — `models/`

A declarative `DataModel` over the warehouse: the grain, the keys, the
[[measures]]. A few dozen lines a reviewer reads without opening the pandas
above it.

It reads the sink. It never sees the transform.

→ [[model]]

*Freeze: the model — the semantic contract.*

## ③ Report — `reports/`

A report package where **every figure is a live query**. Because the model is
materialized, the page re-renders in milliseconds with no pandas in the loop.

→ [[report]]

---

## Where each phase lives

| Stage | Folder | What you write | How the server finds it |
|---|---|---|---|
| ⓪ Input | `inputs/` | a raw pull: a CSV, an API export, a SQL dump | it doesn't; you put it there |
| ① Transform | `transforms/` | DuckDB SQL (a `.sql`, with its `.contract.yaml` beside it), or pandas as the escape hatch (a `.py` or `.ipynb`), that lands warehouse tables | it doesn't; you run it with `tracebi run-transform` |
| ② Model | `models/` | a `DataModel` in a variable named `model` | its page on **Data** (`/data/<model>`), Model tab |
| ③ Report | `reports/` | a package (`report.json` + an `app.jsx` dashboard or a `template.html` page), or a JSON spec that compiles into one | listed in **Reports** (the library), under its model |

The warehouse is one per project, declared in `tracebi.yaml` (by default one
file, `data/warehouse.duckdb`): every transform sinks into it and every model
reads it (`type: warehouse`), so phase ① and phase ② can run in separate
processes. `output/` holds what
`tracebi report build` renders. Both folders are gitignored except the
`*.manifest.json` traces inside them, which stay tracked as the audit trail
behind every rendered number.

## Try it on the reference project

```bash
cd examples/portfolio_project
python run_workflow.py          # ① build the warehouse, ③ build every report
tracebi serve                   # browse it: portfolio_model → Reports → portfolio_dashboard
```

The first run generates a deliberately messy Schedule of Investments into
`inputs/`, so phase ① has real work to do: prose position descriptions to parse
into issuers, trailing position counters to strip, sectors spelled six ways,
money stored as strings.

Its four models follow the same conventions and share the one warehouse its
`tracebi.yaml` names. `holdings_transform.sql`, `saas_transform.sql` and
`wealth_transform.sql` are SQL with a `.contract.yaml` beside each (the last two
read SQLite databases that ship in `inputs/`, through `-- source:` lines);
`affordability_transform.py`, which follows
each home buyer year by year, is the pandas escape hatch and declares its
contract in a `with contract(...)` block. Every table on the Warehouse tab reads
"Checks passed", or an honest failure.

## Exploring before a report exists

`tracebi dev` with no report name opens the app's Data page with the
**project feed**. Any script run while it's open can call
`tracebi.workbench.show(df, note=...)` to post an excerpt, and you can leave
your agent notes there (folded under one line, below the models). The
warehouse tables are on the model's Transform tab, and the Model tab shows the star
schema taking shape. Sink-contract status and
column profiles of the warehouse tables are in the agent's `workbench_state`,
and on the classic page (`tracebi dev --classic`), which lays the warehouse,
models and packages out beside the feed.
`tracebi session export` saves the session to `explorations/` as a committed
record (`--format md` for a version that reads well in a git review). It is
marked as exploration and carries no trace, and `verify` refuses it by name.

## Why the split

The slow, unconstrained analysis (①) and the fast, iterated reporting (③)
never block each other, because the model (②) is a frozen contract between
them.

**Editing a report never re-runs the pandas.** That single property is what
makes the reporting loop fast enough to iterate on, and it is the reason the
phases are separate folders rather than one script.

## Where trust starts

Tracing lineage *through* the raw analysis in phase ① is intentionally **not**
done. The line is drawn at the **sink**, where numbers become a contract you
can report against.

The trust machinery — stamped queries, [[lineage]], fingerprints, and
`tracebi verify` — applies **from the model boundary onward**, phases ② and ③.
Phase ① is trusted the way you trust reviewed code in git, not the way you
trust a hash.

A transform can narrow that gap by declaring a [[sink-contracts|sink contract]]:
closed, declarative checks its tables must satisfy before the data counts.

See [[trace]] for exactly what this does and does not prove.

## Related

- [[freeze-points]] — the handoff between phases
- [[quickstart]] — run all three in about five minutes
- [[sink-contracts]] — the checks a transform's tables must pass
