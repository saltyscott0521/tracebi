# Receipts

**A receipt proves a number *reproduces* and the file was not *altered*. It
does not prove the number is correct.**

That distinction is the most important sentence in these docs, and the wording
is deliberately locked — see [[#The locked language]].

---

## What ships

Every built report writes two files:

```
output/my_report.html                   the self-contained artifact
output/my_report.html.manifest.json     the receipt
```

The manifest records, per figure: the model it came from, the exact query, and
a SHA-256 fingerprint of the data the query returned. The artifact embeds the
same fingerprinted bytes it draws from — so what the reader sees and what the
receipt covers are the same thing, by construction.

## What the file shows

Every built page carries the receipt in a drawer: open it from the
masthead's **Receipt** button or verdict chip, from the footer, or by
clicking a number on the page (it opens at that figure's row). It reads top
to bottom as a certificate:

- the report, when it was built, from which model, and the verdict chip. A
  file says **Not checked** of itself: nothing has re-run its queries since
  it was built. Only a checker (`tracebi verify`, the web app) states
  **Reproduces**, **Needs a look** (the source or model changed since the
  build) or **Does not reproduce**.
- *"The receipt does not claim the numbers are right."*
- how to check the file: `tracebi verify --file <name>.html`, with the
  `.manifest.json` beside it.
- one row per figure, in page order: the value as the page shows it, its
  label, the measure's definition from the model, the query in one line
  (`fair_value by dim_issuer.sector · order fair_value desc`) and the first 8
  characters of the fingerprint. **Raw** holds the query exactly as run and
  the full fingerprint.
- **About this build**: the sink contracts, the stated methodology, who
  built it, the render stamp and the git commit.

The drawer displays what the embedded receipt block records; it re-runs
nothing. The manifest beside the file is still the receipt of record.

## In the web app

The app shows a report as delivered, in a sandboxed frame, and knows more
than the file: its desk re-checks the build. So it tells the frame its
verdict, one message over the frame bridge, `{type: "tracebi:verdict",
state, detail}`, and the masthead's chip and the drawer's say the app's
state in the app's words (**Reproduces**, **Needs a look**, **Does not
reproduce**, **Not checked**). This is the one place a file's chip may read
green, and only because the host told it:

- the app sends only a state it computed from its own re-check
  (`verdictOf`), and nothing while it has none;
- opened on its own (the file, the `/r/` share link, an email) nothing tells
  it, and the chip says what the file can say of itself: **Not checked**;
- a working preview stays **Draft** whatever it is told;
- any page that frames a file could send the message, so a green chip in a
  frame is the framing app's claim. `tracebi verify` is the check.

The report page's **About this build** panel opens on **Receipt**: the same
certificate, drawn by the build's own `tracebi.js` (`renderReceipt`) in a
sandboxed frame, its chip in the app's verdict.

## What you can check

```bash
tracebi verify output/my_report.html.manifest.json
```

Re-runs every recorded query against the model and compares fingerprints.
Each figure lands on one verdict:

| Verdict | Means |
| --- | --- |
| `REPRODUCES` | re-running the query produced byte-identical data |
| `ALTERED` | the data changed — the number moved since the render |
| `UNVERIFIABLE` | no re-runnable query backs it (see [[#Unverifiable figures]]) |
| `UNVERIFIED (marked)` | the author explicitly marked it as not a claim |

```bash
tracebi verify --file output/my_report.html
```

Checks the **file and its receipt**, offline, with no database and no account:
do the embedded bytes still hash to what the manifest says? The manifest is
read from `<file>.manifest.json` beside the report (or `--manifest <path>`), so
send both files together. This catches a number edited in the HTML after the
fact.

## What it does not prove

**It is a reproduction-and-integrity check, not a correctness check.**

- A wrong number that reproduces reliably still says `REPRODUCES`. If phase ①
  sank bad data, every badge is green.
- Between two parties it travels as *documentation*, not evidence: the data,
  the query and the fingerprint are generated together by the same author. It
  becomes evidence only when the verifier independently holds the warehouse.
- It says nothing about the pandas above the sink. See
  [[the-three-phase-workflow#Where trust starts]].

This is a real, useful guarantee — *"these 40 overnight reports still reproduce,
and this one doesn't"* is exactly the question it answers — but it is a narrower
one than "the numbers are right", and the docs never widen it.

## Unverifiable figures

Some numbers cannot be expressed as a model query — several queries combined, a
window function, an algorithm. Those go in a package's `report.py` escape
hatch. Its **inputs** are stamped and re-runnable; its **outputs** are not.

An output figure is stamped `verifiable: false`, permanently and
un-overridably. It never reads green. The receipt says the number is
python-derived and not query-reproducible, because it is.

## The locked language

These phrases are fixed. The runtime writes them literally, and tests pin them:

- **"reproduces"** — never "verified". The green badge means a re-runnable
  query backs the number, not that anyone checked it is correct.
- **"the sink satisfied its contract"** — never "the transform was verified".
  See [[sink-contracts]].
- **"stated methodology"** — the author's own description, not a framework
  claim.

Paraphrasing these is how an honest guarantee quietly becomes an overclaim, so
they are treated as vocabulary rather than prose.

## Related

- [[lineage]] — what gets recorded on the way
- [[sink-contracts]] — narrowing the phase-① gap
- [[cli]] — `tracebi verify` flags
