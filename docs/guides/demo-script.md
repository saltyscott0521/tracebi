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

1. **Open the two reports you will show**, so they open instantly on the day.
   Go to **Report** → `portfolio_dashboard`, then `portfolio_showcase`. A
   report that has never been built is built on first open and kept.
2. **Make the "edited" copy for beat 3.** On `portfolio_dashboard`, click
   **↓ HTML (with receipt)**. The build also saved the matching pair in
   `examples/portfolio_project/output/`:
   `portfolio_dashboard.html` and `portfolio_dashboard.html.manifest.json`.
   Copy both into a folder on your desktop called `demo/`. Then make a second
   copy of the pair named `edited.html` and `edited.html.manifest.json`.
   Also download `portfolio_showcase` with **↓ HTML (with receipt)** into
   `demo/`. You will use it for beat 2.
3. Open `edited.html` in a plain text editor (TextEdit in plain-text mode, or
   Notepad). Find `285904445.21` (it appears once) and change it to
   `295904445.21`. Save. Open `edited.html` in the browser and check the
   headline now reads **$295,904,445**, $10 million more than the real
   report.
4. Close every other tab. The app opens on the **Report** page, which is where
   the demo starts.

## The script

### Beat 0: the problem (1 minute, no clicks)

> "AI can now write a full financial report in minutes. The problem is that a
> wrong number looks exactly like a right one. It's the same font and the same
> chart. So the question is no longer *who can make the chart*, it's *which
> numbers can we believe*."

### Beat 1: a report built from definitions (2 minutes)

Open **Report** → `portfolio_dashboard`.

> "This is a fund's holdings report: fair value, positions, breakdowns by
> sector and fund. It could have been built by an analyst or by an AI
> assistant. Either way, nobody typed these numbers in."

Point at the green badges above the report (**Verifiable artifact**,
**reproducible**, **satisfied**).

> "Each number was looked up from a written-down definition of what 'fair
> value' means, and the badges say the data behind it passed its checks.
> Nobody can quietly use a different formula on one page."

Optional: click **Contract** in the sidebar to show the definitions in one
screen, then come back.

### Beat 2: every number has a receipt (2 minutes)

Open `demo/portfolio_showcase.html` straight from the desktop. It's an ordinary
file in an ordinary browser tab, with no server involved. Click **Receipt** in
the bottom-right corner.

> "This is the file you'd email. It works offline. Every figure carries a receipt, like the one from a shop. It records where
> the number came from and a fingerprint of the exact data behind it. If a
> single digit changes, the fingerprint no longer matches."

Point at the yellow **UNVERIFIED** tag on one line of the drawer.

> "And a number that *can't* be checked, like an estimate someone typed in, is
> labelled as such. It can't pass itself off as checked."

### Beat 3: a changed number gets caught (3 minutes) ★ the moment

Show the browser tab with `edited.html` open.

> "Say someone emails this report around and a number gets changed on the way,
> by accident or on purpose. Fair value now says $295 million. It looks
> completely normal."

Click **Verify a report file** (bottom of the sidebar). Drag in `edited.html`
and `edited.html.manifest.json`, then click **Verify offline**.

The screen turns red: **FILE ALTERED**, with the exact figures listed.

> "Caught in about a second, and it points to exactly which numbers were
> touched. This check needs no database access and no login."

Then drag in the untouched pair (`portfolio_dashboard.html` and its
`.manifest.json`) and verify again. It reads **FILE INTACT**.

### Beat 4: ask a question (1 minute, optional)

Back on **Report** → `portfolio_showcase`. In the **Ask** box, type
`what about Software` and click **Apply cut**.

> "You can ask for a slice, like just the Software sector, and the numbers are
> recalculated from the same definitions. Each answer comes with its own
> fingerprint."

Do **not** click **Keep this cut** in a demo. It rewrites the saved report.

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
