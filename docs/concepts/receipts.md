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

Checks the **file alone**, offline, with no database and no account: do the
embedded bytes still hash to what the embedded manifest says? This catches a
number edited in the HTML after the fact.

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
