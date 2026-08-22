---
slug: verify-your-own-work
title: Check the number before you claim it — the loop is your best chance
when: before telling anyone an analysis is done, and whenever a number looks surprising
---
**The principle.** The thing that most separates a good analyst from a bad one
is not knowing more rules — it is a short loop between producing a number and
finding out whether it's right. Close that loop yourself, before a human sees
the output. Do not hand over a number you have not checked.

**What TraceBi gives you to check with.**

- **`tracebi verify <manifest>`** re-runs every recorded query and confirms each
  figure still reproduces. Only `REPRODUCES` means a number was re-run and
  matched. Run it before you say a report is done.
- **`tracebi verify --file <report.html>`** re-checks the shipped file offline —
  proof the numbers in the file are the ones that were computed.
- **Assert the *meaning*, not just the plumbing.** A test that checks a measure
  returns *some* number is worthless; assert it returns the *right* number on a
  fixture you computed by hand — especially that a ratio is a ratio of totals
  and not a mean of ratios ([[ratio-of-totals]]). Silent-wrong output is this
  project's cardinal sin, and only a value assertion catches it.

**The honest boundary.** `verify` proves a figure *reproduces from its query* —
it does not prove the query is the *right* analysis, and it never reads the raw
transform. Say "reproduces," never "proven correct." A green check on the wrong
measure is still the wrong answer; the judgement is yours, the reproduction is
the tool's.

**The tell.** If you're about to report a number and you can't point at the
check that would fail if it were wrong, you haven't finished — write that check
first.
