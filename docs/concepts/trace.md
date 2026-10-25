# The trace

Every number a report draws from a model has a trace: a record of how it was
made. A trace shows that a number reproduces and that the file was not
altered. It does not show the number is correct.

Each build writes two files:

```
output/my_report.html                   the report
output/my_report.html.manifest.json     the trace
```

For each figure the manifest records the model, the exact query and a SHA-256
fingerprint of the data the query returned. The HTML embeds the same
fingerprinted rows it draws from, so what the reader sees is what the trace
covers.

## Check a report

```bash
tracebi verify output/my_report.html.manifest.json
```

This re-runs every recorded query against the model and compares
fingerprints. Each figure gets one verdict:

| Verdict | Meaning |
| --- | --- |
| `REPRODUCES` | The query ran again and returned byte-identical data. |
| `ALTERED` | The data changed: the number moved since the build. |
| `UNVERIFIABLE` | No re-runnable query backs it (a `report.py` output). |
| `UNVERIFIED (marked)` | The author marked it as not a claim. |

```bash
tracebi verify --file output/my_report.html
```

This checks the file and its trace offline, with no database and no account:
do the embedded rows still hash to what the manifest says? It reads
`<file>.manifest.json` beside the report, or `--manifest <path>`, so send both
files together. It catches a number edited in the HTML after the build.

## Read the trace in the file

Every built page has a trace drawer. Open it from **Trace** under the title,
the verdict chip, **How these numbers were made** in the footer, or by
clicking a number. It lists one row per figure: the value, its label, the
measure's definition, the query in one line
(`fair_value by dim_issuer.sector · order fair_value desc`) and the start of
its fingerprint. **About this build** adds the sink contracts, the stated
methodology, who built it and the commit. The full layout is in
[[template-html]].

The drawer re-runs nothing. A file says **Not checked** about itself. Only a
checker (`tracebi verify`, the web app) says **Reproduces**, **Needs a look**
(the source or model changed) or **Does not reproduce**.

## Read the trace in the app

The app re-checks each build and tells the framed report its verdict in one
message, `{type: "tracebi:verdict", state, detail}`. That is the only way a
file's chip turns green. Opened on its own (as a file, a `/r/` share link or
an email attachment) the file hears nothing and says **Not checked**. Any page
that frames a file could send the message, so a green chip in a frame is that
app's claim; `tracebi verify` is the check.

On a report's page, the **Trace** panel follows the figure you last clicked
through five steps: **Source** (the transform that wrote the table, and
whether the sink satisfied its contract), **Model**, **Query**,
**Fingerprint** and **Re-run now** (what re-running the query returned).

## What a trace does not prove

- **It is not a correctness check.** A wrong number that reproduces still
  reads `REPRODUCES`. If the transform wrote bad data, every chip is green.
- **Between two companies it is documentation, not evidence.** The data, the
  query and the fingerprint come from the same author. It becomes evidence
  when the checker holds the warehouse too.
- **It says nothing about the transform.** Lineage is traced from the sink,
  not through the transform. See [[the-three-phase-workflow]].

The question it does answer is useful: "these 40 overnight reports still
reproduce, and this one doesn't."

## Numbers no query can reproduce

Some numbers need several queries combined, a window function or an
algorithm. Those go in a package's `report.py`. Its inputs are stamped and
re-runnable; its outputs are stamped `verifiable: false`, cannot be
overridden, and never read green. The trace labels them python-derived.

## Words to use

The runtime writes these phrases exactly, and tests check them:

- **"reproduces"**, never "verified". Green means a re-runnable query backs
  the number, not that anyone checked it is correct.
- **"the sink satisfied its contract"**, never "the transform was verified".
  See [[sink-contracts]].
- **"stated methodology"**: the author's own description, not a TraceBi
  claim.

## Names in the code

Until 2026-10-18 the trace was called the *receipt*. The word is gone from
everything a reader sees. The code keeps it in names that are part of the
file format: the `tracebi-receipt` block in a built page, the `.tb-receipt*`
classes, the `data-tb-receipt-*` attributes and `tracebi.renderReceipt`.

## Next

- Check reports in CI: `tracebi verify --strict` in [[cli]]
- See what is recorded along the way: [[lineage]]
