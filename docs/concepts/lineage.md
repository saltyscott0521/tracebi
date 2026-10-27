# Lineage

Every data operation in TraceBi adds a node to a chain that records what
happened. Read it from any `DataSet`:

```python
ds2 = ds.filter(region="West")     # ds is unchanged; ds2 has one more node
for node in ds2.lineage:
    print(node.operation, node.source)
```

A node records the operation, its parameters, the source, a timestamp and
operation-specific metadata: enough to say what produced a frame without
reading the code that produced it.

## Rules

- **`DataSet` is immutable.** Every method returns a new `DataSet`. Nothing
  changes `.df` or `.lineage` in place.
- **Every operation adds a `LineageNode`.** The operation and its node happen
  together or not at all, so the chain cannot break silently.
- **A node cannot be edited.** `LineageNode` is frozen: every field, including
  `metadata`, is set when it is created.
- **Lineage starts at the sink.** It covers the model and the report. It is
  not traced through the transform. A SQL transform's certificate does
  record which source columns each sink column is computed from, as DuckDB's
  parser proves it ([[transform-sql]]); pandas records nothing.

## Where it shows up

- **In the trace.** A figure's manifest entry carries the resolved query and
  the model it ran against, taken from lineage.
- **In the app.** A report's **Lineage** tab draws where each number came
  from, left to right: the transform that wrote the tables, the stored tables,
  the model, each query and the figures on the page. It is read from the last
  build's [[trace]], so it shows what the reader was shown. Select a figure
  to light only the tables its own query read. A python-derived query is shown
  as such and never reads as verified. `GET /api/reports/{name}/lineage`
  returns the same graph; `/mermaid` returns a diagram.
- **In `tracebi verify`.** The source fingerprints in lineage let verify
  explain drift. `SOURCE DRIFT` means an input moved. `UNEXPLAINED` means the
  inputs did not move but the answer did, which is the one to worry about.

## Why it works this way

The transform is arbitrary SQL or Python, and auditing arbitrary code is not
something a fingerprint can do. The line is drawn at the sink, where the
numbers become tables a model can query. See [[the-three-phase-workflow]].

## Next

- What the chain is used for: [[trace]]
- Checks at the sink: [[sink-contracts]]
