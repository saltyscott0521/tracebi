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
- [[WORKFLOW]] — the same model, stated normatively
