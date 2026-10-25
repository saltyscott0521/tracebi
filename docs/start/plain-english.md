# What is TraceBi

TraceBi makes reports where every number carries a record of how it was made,
so anyone can check later that the number still matches its source.

## The problem

AI tools can write a full report in minutes. A wrong number in that report
looks exactly like a right one: same font, same chart. Checking usually means
asking someone where a figure came from and trusting their memory.

## How TraceBi works

Every number in a TraceBi report comes with a **trace**, like the tracking on
a parcel. The trace records which data and which definition produced the
number, and a fingerprint of that data. Change one digit and the fingerprint
no longer matches.

A report is made in three steps, each owned by the person best at it:

1. **Clean.** Messy exports become tidy tables.
2. **Define.** Each business term ("fair value", "revenue") is written down
   once, and reviewed.
3. **Present.** The page is laid out. Every number on it is looked up from
   the definitions, never typed in.

## What you can check

Anyone with the report file can ask two questions and get an answer in
seconds:

- **Does it reproduce?** Run it again today: is the number the same?
- **Was the file altered?** Did someone edit a number after it was built?

## What it does not promise

A trace shows a number is consistent and unedited. It does not show the number
is right. If bad data went into the cleaning step, the report will show the
bad number every time. People still review the cleaning and the definitions.
When the cleaned tables pass their declared checks, TraceBi says "the sink
satisfied its contract", and nothing more.

## In one sentence

"Our reports are built from written-down definitions, every number carries a
trace, and anyone can check in seconds that a number still matches its source
and hasn't been edited, including numbers an AI produced."

## Next

- Show it to someone: [[demo-script]]
- Try it yourself: [[quickstart]]
