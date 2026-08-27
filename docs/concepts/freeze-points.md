# Freeze points

**A freeze point is a materialized artifact handed from one phase to the next.
It is what lets the three phases run at different speeds.**

There are two, one between each pair of phases in [[the-three-phase-workflow]]:

| Freeze | What it is | Written by | Read by |
| --- | --- | --- | --- |
| **The sink** | `data/warehouse.duckdb` — real tables on disk | [[transform]] (①) | [[model]] (②) |
| **The model** | the semantic contract: grain, keys, [[measures]] | you, in `models/` | [[report]] (③) |

---

## Why they matter

Without a freeze point, every report render would re-run the analysis above it.
With one, the expensive work happens once and the cheap work happens as often
as you like.

That is the whole reason the reporting loop is fast:

- **Editing a report re-renders in milliseconds.** It queries materialized
  tables; no pandas runs.
- **Re-running a transform does not touch your reports.** They keep serving
  the last good sink until you refresh it.
- **Changing a model is a reviewable diff**, not a cascade — because what sits
  below it is frozen, and what sits above it only speaks the model's
  vocabulary.

## What crossing a freeze point costs

A freeze point is a *contract*, so crossing it deliberately loses information.

- **The model cannot see the transform.** It reads tables, not the code that
  produced them. If a number is wrong because the pandas was wrong, the model
  has no way to know — this is the honest boundary described in [[receipts]].
- **The report cannot see the warehouse directly.** It speaks in
  [[measures]] and dimensions the model declares. That is what makes a figure
  re-runnable, and it is why an expressiveness gap in the model pushes work
  into ungoverned code where the receipt weakens.

## Refreshing a freeze point

Re-run the transform (`tracebi run-transform <name>`) and the sink is replaced.
Transforms are written to be **idempotent** — a rerun replaces the warehouse
tables rather than appending to them.

> **One operational catch:** DuckDB allows many readers but a single writer. A
> warehouse refresh is blocked while a `tracebi dev` or `tracebi serve` process
> holds the file open. Stop the server to refresh.

## Related

- [[transform]] — what writes the sink
- [[sink-contracts]] — checks that run at sink time
- [[model]] — what reads it
