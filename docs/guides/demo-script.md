# A ten-minute demo for a non-technical audience

**A click-by-click script for showing TraceBi to people who read and approve
reports: finance, operations, compliance, leadership. No terminal on screen
and no code on screen.**

The story you are telling has three beats: *here is a report*, *every number
has a receipt*, *a changed number gets caught*. Everything else is optional.
If the audience needs the concepts first, send them [[plain-english]] ahead of
the meeting.

---

## Before the meeting (15 minutes, once)

Someone comfortable with a terminal does this part.

```bash
pip install -e ".[dev]"                 # from the repo root
cd examples/portfolio_project
python run_workflow.py                  # builds the demo data (≈1 second)
tracebi serve                           # → http://127.0.0.1:8000
```

Then, in the browser:

1. **Build the two reports you will show**, so they open instantly on the day.
   The app opens on **Reports**, the library. Under Direct Lending Portfolio,
   open **Portfolio Dashboard** and **Portfolio Showcase** in turn. A report
   that has never been built says so; press **Build it now**, and it is kept.
2. **Make the "edited" copy for beat 3.** Open Portfolio Dashboard and choose
   **Export → HTML** in the bar above it. The build also saved the matching pair in
   `examples/portfolio_project/output/`:
   `portfolio_dashboard.html` and `portfolio_dashboard.html.manifest.json`.
   Copy both into a folder on your desktop called `demo/`. Then make a second
   copy of the pair named `edited.html` and `edited.html.manifest.json`.
   Also download `portfolio_showcase` with **Export → HTML** into
   `demo/`. You will use it for beat 2.
3. Open `edited.html` in a plain text editor (TextEdit in plain-text mode, or
   Notepad). Find `285904445.21` (it appears once) and change it to
   `295904445.21`. Save. Open `edited.html` in the browser and check the
   headline now reads **$295,904,445**, $10 million more than the real
   report.
4. Close every other tab. The app opens on **Reports**, the library, which is
   where the demo starts.

## The script

### Beat 0: the problem (1 minute, no clicks)

> "AI can now write a full financial report in minutes. The problem is that a
> wrong number looks exactly like a right one. It's the same font and the same
> chart. So the question is no longer *who can make the chart*, it's *which
> numbers can we believe*."

### Beat 1: a report built from definitions (2 minutes)

On **Reports**, open **Portfolio Dashboard**.

> "This is a fund's holdings report: fair value, positions, breakdowns by
> sector and fund. It could have been built by an analyst or by an AI
> assistant. Either way, nobody typed these numbers in."

Point at the green **Reproduces** chip beside the report's title.

> "Each number was looked up from a written-down definition of what 'fair
> value' means, and the chip says the app re-ran every one of those lookups
> and got the same numbers. Nobody can quietly use a different formula on one
> page."

Optional: click **Data** in the sidebar, then Direct Lending Portfolio. Its
**Model** tab shows the definitions in one screen. Go back to **Reports**.

### Beat 2: every number has a receipt (2 minutes)

Open `demo/portfolio_showcase.html` straight from the desktop. It's an ordinary
file in an ordinary browser tab, with no server involved. Click **Receipt**
beside the chip under the title.

> "This is the file you'd email. It works offline. Every figure carries a receipt, like the one from a shop. It records where
> the number came from and a fingerprint of the exact data behind it. If a
> single digit changes, the fingerprint no longer matches."

Point at the **unverified** tag on one line of the receipt.

> "And a number that *can't* be checked, like an estimate someone typed in, is
> labelled as such. It can't pass itself off as checked."

### Beat 3: a changed number gets caught (3 minutes) ★ the moment

Show the browser tab with `edited.html` open.

> "Say someone emails this report around and a number gets changed on the way,
> by accident or on purpose. Fair value now says $295 million. It looks
> completely normal."

Click **Review** in the sidebar, then its **Verify** tab. Drag in `edited.html`
and `edited.html.manifest.json`, then click **Verify offline**.

The screen turns red: **FILE ALTERED**, with the exact figures listed.

> "Caught in about a second, and it points to exactly which numbers were
> touched. This check needs no database access and no login."

Then drag in the untouched pair (`portfolio_dashboard.html` and its
`.manifest.json`) and verify again. It reads **FILE INTACT**.

### Beat 4: ask a question (1 minute, optional)

Click **Ask** in the sidebar. With Direct Lending Portfolio picked, tick
`fair_value` and `sector`, then **Run query**.

> "You can ask your own question of the same definitions, and the answer
> comes with the exact query behind it, so it can be checked the same way."


### Beat 5: the honest boundary (1 minute, don't skip)

> "One thing TraceBi does *not* claim: a receipt shows a number is consistent
> and unedited, not that it's *correct*. If bad data goes in at the start, the
> report will faithfully show the bad number. That's why a person still
> approves the definitions and the cleaning. TraceBi makes sure that what they
> approved is what gets shipped."

Being upfront about this builds more trust with a finance or compliance
audience than any feature.

## Likely questions

| They ask | You answer |
| --- | --- |
| "Does this replace Tableau / Power BI?" | "No. It's for the reports where being able to prove the number matters most: board packs, investor reports, regulatory filings, anything an AI drafts." |
| "Can the AI change our data?" | "No. The AI builds the report through a gateway that has no write access to the data it reports on. A person approves every change." |
| "What does the reader need?" | "A web browser. The report is one file that works offline. To check it, they need that file and its receipt file." |
| "Who issued the receipt? Could someone fake both?" | "Today the receipt is made by whoever built the report, so between companies it's documentation. Signed receipts that prove who issued them are on the roadmap." |
| "Where does the data live?" | "In your environment. TraceBi runs where your data is. Nothing is sent to us." |

## Words to avoid on stage

Engineers love these words. A non-technical room does not. Here's what to say
instead:

| Instead of | Say |
| --- | --- |
| manifest | receipt |
| SHA-256 fingerprint / hash | fingerprint |
| star schema, grain, semantic layer | the definitions |
| sink, warehouse, DuckDB | the clean data |
| transform / pandas | the cleaning step |
| MCP gateway / agent | the AI assistant |
| reproduces | re-runs to the same number |
