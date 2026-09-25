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

## ① Transform — `transforms/`

Ordinary, unconstrained pandas. Pull the queries, do the real analysis — window
functions, prose parsing, cleaning, dedupe — then **sink** clean star-schema
tables into a DuckDB warehouse file.

The framework does not constrain this phase. The contract is not *how* you
clean; it is **what lands**: the named tables at the end of the script.

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
| ① Transform | `transforms/` | pandas (a `.py` or `.ipynb`) that writes DuckDB tables | it doesn't; you run it with `tracebi run-transform` |
| ② Model | `models/` | a `DataModel` in a variable named `model` | listed on the Models page |
| ③ Report | `reports/` | a package (`report.json` + `template.html`), or a JSON spec that compiles into one | listed on the Reports page |

The warehouse is one file, `data/warehouse.duckdb`: phase ① writes it and phase
② reads it, so the two can run in separate processes. `output/` holds what
`tracebi report build` renders. Both folders are gitignored except the
`*.manifest.json` receipts inside them, which stay tracked as the audit trail
behind every rendered number.

## Try it on the reference project

```bash
cd examples/portfolio_project
python run_workflow.py          # ① build the warehouse, ③ render the report once
tracebi serve                   # browse it: Reports → portfolio_dashboard
```

The first run generates a deliberately messy Schedule of Investments into
`inputs/`, so phase ① has real work to do: prose position descriptions to parse
into issuers, trailing position counters to strip, sectors spelled six ways,
money stored as strings.

## Exploring before a report exists

`tracebi dev` with no report name opens the **discovery workbench**. Any script
run while it's open can call `tracebi.workbench.show(df, note=...)` to post an
excerpt; the warehouse panel lists tables and their contract status as they
land, and the models panel shows the star schema taking shape.
`tracebi session export` saves the session to `explorations/` as a committed
record (`--format md` for a version that reads well in a git review). It is
marked as exploration and carries no receipt, and `verify` refuses it by name.

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

See [[receipts]] for exactly what this does and does not prove.

## Related

- [[freeze-points]] — the handoff between phases
- [[quickstart]] — run all three in about five minutes
- [[sink-contracts]] — the checks a transform's tables must pass
