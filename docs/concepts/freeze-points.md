# Freeze points

A freeze point is a stored artifact one stage hands to the next. There are
two:

| Freeze point | What it is | Written by | Read by |
| --- | --- | --- | --- |
| The sink | The warehouse `tracebi.yaml` names (by default `data/warehouse.duckdb`): real tables | The [[transform]] | The [[model]] |
| The model | The definitions: grain, keys, [[measures]] | You, in `models/` | The [[report]] |

## What they give you

- **Editing a report rebuilds in milliseconds.** It queries stored tables; no
  transform runs.
- **Re-running a transform does not touch your reports.** They keep showing
  the last good data until you rebuild them.
- **Changing a model is a diff someone can review.** What sits below it is
  fixed, and what sits above it only uses the model's names.

## What they cost

- **The model cannot see the transform.** If a number is wrong because the
  cleaning was wrong, the model has no way to know.
- **The report cannot read the warehouse directly.** It asks for measures and
  dimensions the model declares. That is what makes a figure re-runnable, and
  why a gap in the model pushes work into code the trace cannot check.

## Refresh one

```bash
tracebi run-transform <name>
```

The rerun replaces the warehouse tables. It never appends.

A DuckDB file has one writer at a time. A model query opens the warehouse
read-only for that query alone, so a running `tracebi dev` or `tracebi serve`
does not block a refresh. The write waits a few seconds for a read in progress
to finish. A read that arrives during the write is refused, naming the
transform to wait for.

## Next

- The three stages they connect: [[the-three-phase-workflow]]
- Checks that run before the sink counts: [[sink-contracts]]
