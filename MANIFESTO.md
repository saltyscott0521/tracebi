# The TraceBi Manifesto

Governance tooling assumes a human wrote the transformation and is still
around to ask. TraceBi assumes a machine wrote it and is gone.

AI made producing reports nearly free; believing them is the expensive part.
When an agent composes forty reports overnight, "ask the author" is not a
control, code review of the pandas is not a control, and a dashboard tool's
polish is not a control. The only control that scales is a mechanical one: a
contract the number was computed against, a fingerprint of what came out, and
a command that re-checks both without trusting anyone's memory.

Producing analysis is now cheap. TraceBi exists so believing it can be too.

## The work

A report in TraceBi is made in three phases, in three folders, and the trust
story lives in the seams between them.

**① TRANSFORM** — `transforms/`. Ordinary, unconstrained pandas. Pull the raw
inputs, do the real analysis — window functions, prose parsing, dedupe,
whatever the data demands. The framework does not constrain this phase and
will not pretend to understand it. The contract is not *how* you clean; it is
*what lands*: named star-schema tables sunk into a file-backed DuckDB
warehouse.

*— freeze point: the warehouse, the materialized tables —*

**② MODEL** — `models/`. A declarative `DataModel` over the sink: grain,
keys, relationships, named measures — a few dozen lines a reviewer reads
without opening the pandas above it. It reads the sink; it never sees the
transform.

*— freeze point: the model, the semantic contract —*

**③ REPORT** — `reports/`. A `ReportSpec` pointed at the model, where every
figure is a live query: KPI cards, charts, tables. Because the model is
materialized, the page re-renders in milliseconds with no pandas in the loop.
A dashboard is a style of report, not a different thing.

A freeze point is a materialized artifact handed from one phase to the next.
The phases never block each other: editing a report never re-runs the
transform; rewriting the transform never breaks a report the model still
satisfies.

## The receipt

At the freeze points, the machinery attaches.

Every query from the model boundary onward is **stamped**: the resolved
query, the lineage chain, and a SHA-256 fingerprint of the result. Every
render emits a **manifest** — the receipt for the whole report. Specs are
validated before execution, and a validation error carries a repair path
(`sections[0].data.query.fact`), because the author fixing it may not be a
person.

`tracebi verify <manifest>` re-runs the recorded queries against the model
and classifies every section: **REPRODUCES**, **SOURCE DRIFT**, **MODEL
CHANGED**, **MISMATCH (cause unknown)**, **UNEXPLAINED**, **UNVERIFIABLE**,
**ERROR**. Anything alarming — a mismatch nobody has diagnosed, a model that
changed under a receipt, an error mid-check — exits nonzero. The bias is
toward loud failure, never toward the reassuring guess.

**Every number has a receipt — or is marked as not having one. There is no
third state.** That is the promise, and it is checkable: run `verify`
yourself.

## Why it is shaped this way

The trust boundary needs somewhere to draw the line, and the line is drawn at
the **sink** — the freeze point where free-form analysis becomes named
tables, and the numbers become a contract you can report against. The
three-phase workflow is not a style preference; it is the mechanism that
makes the trust layer possible. The trust layer is the identity; the workflow
is how it works.

It is also why the spec is JSON. Python stays strictly more powerful: a spec
cannot express arbitrary computation, which is exactly why it is safe for a
machine to generate and checkable without executing. Python and JSON are two
serializations of one object graph — an analyst prototypes in a notebook,
exports with `from_report()`, and the governed artifact needs no rewrite.

TraceBi is the AI framework for BI and analytics: humans and machines author
against the same contracts. Nothing on the agent surface is a second-class
copy of the human surface — a report has only ever been a name and a zero-arg
callable, and neither author gets a shortcut around the receipt. The analyst
gets a model they can read in one screen and a `verify` they can run before a
sign-off. The agent gets the same thing through the MCP gateway — validate a
spec, query a model, render, verify — a surface that is deliberately
read-and-compute-only, because an agent that can check everything and
overwrite nothing is one you can leave alone.

## The honest boundary

Lineage is **not** traced through phase-① pandas, and this is a feature, not
a gap. A framework that claimed to trace arbitrary dataframe surgery would be
lying at exactly the moment lying is most expensive. The transform is trusted
the way reviewed code is trusted — in git — not the way a fingerprint is
trusted. The trust machinery applies from the model boundary onward — phases
② and ③. `tracebi verify` re-runs recorded queries and compares fingerprints;
it does not read a transform, and it never asserts a number is *correct*. It
asserts something narrower and more durable: this number is still what this
query against this model produces.

The escape hatch honors the same line. When the spec vocabulary can't express
a layout, a template package's `report.py` can run arbitrary pandas — and its
output stamps `verifiable: false` and never reads green under `verify`.
Honesty over reach: an unverifiable section that says so is trustworthy; a
green badge on unchecked work is not.

The maturity frame is the **assurance ladder**:

- **L0 — nothing**: raw SQL in, raw HTML out; the company can prove nothing.
- **L1 — query receipts**: every figure carries its resolved query, lineage,
  and fingerprint.
- **L2 — spec reproducibility**: the whole report re-runs from its manifest
  and reproduces, section by section.
- **L3 — signed attestation**: a receipt whose issuer is cryptographically
  verifiable. **This does not exist yet.** Manifests today are unsigned, and
  until receipts are signed and attribution is authenticated, we describe the
  audit trail as operator-asserted — because that is what it is. We say so,
  because a trust product that overclaims its own trust story has already
  failed.

## What we refuse to build

- **We will not trace through the transform.** Fake lineage over free-form
  pandas would trade honesty for a demo. The line stays at the sink.
- **We will not let `verify` guess.** An undiagnosed mismatch exits nonzero.
  No heuristic ever rounds a discrepancy down to "probably fine."
- **We will not let presentation change a number.** Derived labels and
  formats fill in what the author left unset; a presentation default must
  never change the number it presents. When a value's unit is ambiguous, the
  unit-changing rung is declined and only unit-preserving formatting applies.
- **We will not let the escape hatch read green.** `verifiable: false` is
  permanent for that path. There is no flag to override it.
- **We will not give the agent surface write access to the warehouse** until
  per-agent identity and scopes exist. Capability follows accountability,
  never precedes it.
- **We will not ship a spec language that grows toward Turing-completeness.**
  The moment a spec can compute, it can no longer be checked without being
  executed, and the safety of machine authorship evaporates.
- **We will not phone home.** No telemetry, no CDN fetches, no usage beacons
  — in the framework or in anything it renders.
- **We will not claim a number is correct.** We claim it reproduces. The
  difference is the product.

In code review, "that violates the manifesto" means one of these eight.

## Vocabulary

One canon, used everywhere — code, docs, UI, agent context:

| Term | Meaning |
|---|---|
| **Transform** (①) | Unconstrained pandas in `transforms/`; the contract is what lands, not how. (The medallion `ManipulationLayer` is orchestration vocabulary for tracked pipeline jobs — a different thing, not this phase.) |
| **Sink** | Where transform output becomes named warehouse tables — where trust attaches |
| **Freeze point** | A materialized artifact handed from one phase to the next |
| **Model** (②) | The declarative star-schema contract: grain, keys, measures |
| **Report** (③) | Any rendered output of live queries; "dashboard" is a style of report |
| **Stamp** | Resolved query + lineage + SHA-256 fingerprint on a section's data |
| **Manifest** | The receipt a render emits: every stamp for the report |
| **Verify** | Re-run the recorded queries; classify: REPRODUCES / SOURCE DRIFT / MODEL CHANGED / MISMATCH (cause unknown) / UNEXPLAINED / UNVERIFIABLE / ERROR |
| **`verifiable: false`** | The escape hatch's permanent mark; never green |
| **Assurance ladder** | L0 nothing → L1 receipts → L2 reproducibility → L3 signed attestation (L3: not yet) |
| **`requests/`** | The human scratchpad — unverified authoring space; the path forward is promotion into `reports/` |

## Commitments

1. **The receipt is the product.** Any feature that weakens the
   stamp–manifest–verify loop is rejected, whatever it adds elsewhere.
2. **Never overclaim.** The boundary at the sink, the unsigned manifest, the
   unverifiable section — all stated plainly, in the tool's own output, not
   buried in docs.
3. **Local by default.** Your warehouse is a file you own; rendered reports
   are self-contained HTML with a strict CSP and vendored charts; connector
   `describe()` is contractually forbidden from exposing credentials. Data
   residency is the default, not a tier. Hosted topologies are demos of
   TraceBi, not the shape of it.
4. **Both authors, one contract.** Anything the analyst can validate, render,
   or verify, the agent can too — and neither gets a shortcut around the
   receipt.
5. **Errors are for repair.** Validation failures carry the path to the
   fault. A machine-facing error that a machine cannot act on is a bug.
6. **Loud failure over quiet convenience.** Missing dependencies raise named
   errors; unknown mismatches alarm; validation fails with a path to the fix.

The boundary is load-bearing. Changes that blur the sink line — lineage
claims about transforms, green verdicts for unverifiable sections, defaults
that alter values — violate this manifesto and get reverted, not debated. If
a change makes a number harder to check, it violates the manifesto. Cite this
document and reject it.

The machine wrote it and is gone. The receipt remains. That is enough — if
the receipt is honest.
