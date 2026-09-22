# TraceBi in plain English

**TraceBi makes reports where every number comes with a receipt, so anyone can
check later that the number still matches what it was built from.**

This page is for people who read, approve or pay for reports and don't write
code. No technical background is needed. Engineers should start at
[[quickstart]].

---

## The problem

AI tools can now write a full report in minutes: charts, tables, headline
numbers. That is useful. But **a wrong number looks exactly like a right one.**
A figure the AI got wrong shows up in the same font and the same chart as the
ones it got right.

Today, most of the checking happens by memory and by trust. People ask "where
did this number come from?", someone digs through a spreadsheet, and the answer
is "I think it was the March export." When reports get made faster than anyone
can check them, that approach stops working.

## The idea, in one picture

Think of a **store receipt**. When you buy something, the receipt lists each
item and its price, so you can check it against the shelf later. You don't have
to trust the cashier's memory.

TraceBi gives every number in a report a receipt like that. The receipt records:

- **where the number came from:** which data and which definition (for example
  "total fair value = the sum of fair value across all holdings"), and
- **what came out:** a tamper-evident "fingerprint" of the exact data behind
  it. If one digit changes, the fingerprint no longer matches.

Anyone can later ask two questions, and a computer answers them in seconds:

1. **"If I run this again today, do I get the same number?"** TraceBi calls this
   *reproduces*.
2. **"Has anyone edited the numbers in this file since it was made?"** If
   someone changed a figure by hand, the check says *file altered* and points to
   the figure.

## How a report gets made: three steps

A report travels through three stages. Each one is a separate folder, owned by
whoever is best at that job.

| Stage | In everyday terms | Who usually does it |
| --- | --- | --- |
| **1. Clean** (`transforms/`) | Take messy exports and tidy them into clean, well-labelled tables. Like prepping ingredients before cooking. | An analyst, an engineer or an AI assistant |
| **2. Define** (`models/`) | Write down, once, what each business term means: what "fair value" is, what a "sector" is, how totals add up. Like a recipe card everyone cooks from. | An analyst, reviewed by someone who knows the business |
| **3. Present** (`reports/`) | Lay out the page: headline numbers, charts, tables. Every number on the page is looked up from step 2, never typed in by hand. | An analyst or an AI assistant |

Because the definitions in step 2 are written down once, "revenue" means the
same thing in every report. Nobody can quietly use a different formula on one
page.

## Who does what

- **The builder** (a person or an AI assistant) prepares the data and designs
  the report.
- **The reviewer** reads the definitions and the finished page, then approves
  them. The changes arrive as a proposal to approve, edit or reject, the way
  engineers review code. An AI working through TraceBi's gateway can check its
  own work, but it has no write access to the data it reports on.
- **The reader** gets one file. It opens in any web browser, works offline, and
  carries its own receipt. They can check it with the **Verify** page in the app
  by dropping in the report and its receipt file.

## What the receipt does *not* promise

This matters, and TraceBi is deliberately strict about it.

- **A receipt shows a number is consistent. It does not show the number is
  right.** If bad data went in at step 1, the report will faithfully and
  repeatably show the bad number. The receipt proves it *reproduces*, not that
  it is *correct*.
- **Step 1, the cleaning, is checked by people, not by the receipt.** TraceBi
  can run simple checks on the cleaned tables ("no duplicate holdings", "every
  holding belongs to a known fund"). When they pass, the phrase is *"the sink
  satisfied its contract."* It is not a guarantee that the analysis was right.
- **The receipt is made by whoever made the report.** Between two companies it
  is good documentation, not independent proof. It becomes proof when the
  person checking also has access to the original data. Signed receipts, which
  prove *who* issued them, are planned but not built yet.

## Words you will see in the app

| Word in the app | What it means |
| --- | --- |
| **Receipt** / **manifest** | The record of where each number came from and its fingerprint. Saved as a small `.manifest.json` file next to the report. |
| **Fingerprint** | A short code computed from the exact data. Any change to the data gives a different code. |
| **Reproduces** | Running it again gave exactly the same data. |
| **File altered** | Someone changed numbers in the file after it was built. |
| **Unverified** | The author marked this number as not checkable, for example a hand-written note. It is labelled, never hidden. |
| **Model** / **Contract** | The written-down definitions from step 2: what each measure and category means. |
| **Measure** | A defined calculation, such as "total fair value" or "average spread". |
| **Sink** / **warehouse** | The clean tables produced by step 1, stored in one file. |
| **Contract satisfied / no contract** | Whether the cleaned tables passed their declared checks, or have no checks declared. |
| **Desk** | The app's home page: what needs a person's attention right now. |
| **Draft / exploration** | A report still being worked on. It contains scratch work that is removed before publishing. |
| **Agent** | An AI assistant that builds reports using the same rules as a person. |

## The one-sentence version for your boss

> "Our reports are built from written-down definitions, every number carries a
> receipt, and anyone can check in seconds that a number still matches its
> source and hasn't been edited, including numbers an AI produced."

## Next

- See it working: [[demo-script]], a ten-minute walkthrough you can give to
  anyone.
- The technical version of this page: [[the-three-phase-workflow]] and
  [[receipts]].
