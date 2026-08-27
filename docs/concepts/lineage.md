# Lineage

**Every data operation appends a node describing what happened. The chain is
not optional, and it cannot be edited after the fact.**

---

## The two invariants

**1. `DataSet` is immutable.** Every transform method returns a *new* `DataSet`.
Nothing mutates `.df` or `.lineage` in place.

```python
ds2 = ds.filter(region="West")     # ds is unchanged
```

**2. Every operation produces a `LineageNode`.** If an operation skipped the
lineage step, the audit chain would break silently — so the two happen together
or not at all.

`LineageNode` is **frozen**: every field, including `metadata`, is passed at
construction. You cannot edit a node afterwards, by design.

## What a node records

The operation, its parameters, the source, a timestamp, and operation-specific
metadata — enough to say *what produced this frame* without re-reading the code
that produced it.

```python
for node in ds.lineage:
    print(node.operation, node.source)
```

## Where it shows up

- **In the receipt.** A figure's manifest entry carries the resolved query and
  the model it ran against — recovered from lineage, not re-derived.
- **In the web UI.** `GET /api/reports/{name}/lineage` returns a graph;
  `/mermaid` returns a diagram.
- **In `tracebi verify`.** Source fingerprints recorded in lineage are what let
  drift be *diagnosed* — `SOURCE DRIFT` (an input moved) is distinguishable
  from `UNEXPLAINED` (the inputs did not move but the answer did), and that
  distinction is the difference between a shrug and an alarm.

## Where it deliberately stops

Lineage covers the [[model]] and [[report]] phases. It does **not** trace
through phase-① [[transform]] pandas.

That is the honest boundary described in
[[the-three-phase-workflow#Where trust starts]] — drawn at the sink, where
numbers become a contract you can query. Claiming otherwise would mean claiming
to audit arbitrary Python.

## Related

- [[receipts]] — what the chain is ultimately used for
- [[sink-contracts]] — narrowing the phase-① gap
