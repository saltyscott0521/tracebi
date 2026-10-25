# A ten-minute demo

A click-by-click script for showing TraceBi to people who read and approve
reports: finance, operations, compliance, leadership. No terminal and no code
appear on screen.

The demo has three moments: here is a report, every number has a trace, and a
changed number gets caught. Send [[plain-english]] ahead of the meeting if the
audience wants the ideas first.

## Before you begin

Someone comfortable with a terminal prepares this once, about 15 minutes
before the meeting.

1. Build the demo data and serve it:

   ```bash
   pip install -e ".[dev]"                 # from the repository root
   cd examples/portfolio_project
   python run_workflow.py                  # builds the data and every report, about 10 seconds
   tracebi serve                           # http://127.0.0.1:8000
   ```

2. In the browser, open **Reports**. Under **Direct Lending Portfolio**, open
   **Portfolio Dashboard** and **Portfolio Showcase** to check they load. A
   report that was never built says so; **Build it now** builds it.
3. Make a folder on your desktop called `demo/`. Copy these two files from
   `examples/portfolio_project/output/portfolio_model/` into it:
   `portfolio_dashboard.html` and `portfolio_dashboard.html.manifest.json`.
4. Make a second copy of the pair in `demo/`, named `edited.html` and
   `edited.html.manifest.json`.
5. Open Portfolio Showcase in the app and choose **Export → HTML**. Save it in
   `demo/` as `portfolio_showcase.html`.
6. Open `edited.html` in a plain text editor (TextEdit in plain-text mode, or
   Notepad). Replace both copies of `285904445.21` with `295904445.21`. Save.
7. Open `edited.html` in the browser. The headline should read
   **$295,904,445**, $10 million more than the real report.
8. Close every other tab and leave the app on **Reports**.

## The script

### 1. The problem (1 minute, no clicks)

> "AI can now write a full financial report in minutes. The problem is that a
> wrong number looks exactly like a right one. Same font, same chart. So the
> question is no longer who can make the chart. It's which numbers we can
> believe."

### 2. A report built from definitions (2 minutes)

1. On **Reports**, open **Portfolio Dashboard**.

   > "This is a fund's holdings report: fair value, positions, breakdowns by
   > sector and fund. An analyst or an AI assistant could have built it.
   > Either way, nobody typed these numbers in."

2. Point at the green **Reproduces** chip beside the title.

   > "Each number was looked up from a written-down definition of what 'fair
   > value' means. This chip says the app re-ran every lookup and got the same
   > numbers. Nobody can quietly use a different formula on one page."

3. Optional: click **Data** in the sidebar. The board shows where the numbers
   come from, left to right. Click the Direct Lending Portfolio card; its
   **Model** tab shows the definitions on one screen. Go back to **Reports**.

### 3. Every number has a trace (2 minutes)

1. Open `demo/portfolio_showcase.html` from the desktop. It is an ordinary file
   in an ordinary browser tab, with no server.
2. Click **Trace** beside the chip under the title.

   > "This is the file you'd email. It works offline. Every figure carries its
   > trace: where the number came from, and a fingerprint of the exact data
   > behind it. Change one digit and the fingerprint no longer matches."

3. Point at the **unverified** tag on one line of the trace.

   > "A number that can't be checked, like an estimate someone typed in, is
   > labelled as such. It can't pass itself off as checked."

### 4. A changed number gets caught (3 minutes)

This is the moment the demo is for.

1. Show the tab with `edited.html`.

   > "Say this report gets emailed around and a number changes on the way, by
   > accident or on purpose. Fair value now says $295 million. It looks
   > completely normal."

2. Click **Review** in the sidebar, then the **Verify** tab.
3. Drag in `edited.html` and `edited.html.manifest.json`, then click
   **Verify offline**. The screen turns red: **FILE ALTERED**, with the
   changed figures listed.

   > "Caught in about a second, and it points to exactly which numbers were
   > touched. This check needs no database and no login."

4. Drag in the untouched pair, `portfolio_dashboard.html` and its
   `.manifest.json`, and verify again. It reads **FILE INTACT**.

### 5. Ask a question (1 minute, optional)

1. Open **Direct Lending Portfolio** in the sidebar and click **Ask this
   model**.
2. Build the sentence "Show fair value by sector" (type, or pick each word),
   then click **Ask**.

   > "You can ask your own question of the same definitions. The answer comes
   > with the exact query behind it, so it can be checked the same way."

### 6. What it does not claim (1 minute, don't skip)

> "One thing TraceBi does not claim: a trace shows a number is consistent and
> unedited, not that it's correct. If bad data goes in at the start, the
> report will show the bad number every time. That's why a person still
> approves the definitions and the cleaning. TraceBi makes sure that what they
> approved is what gets shipped."

A finance or compliance audience trusts this more than any feature.

## Likely questions

| They ask | You answer |
| --- | --- |
| "Does this replace Tableau or Power BI?" | "No. It's for the reports where proving the number matters most: board packs, investor reports, regulatory filings, anything an AI drafts." |
| "Can the AI change our data?" | "No. The AI builds reports through a gateway with no write access to the data it reports on. A person approves every change." |
| "What does the reader need?" | "A web browser. The report is one file that works offline. To check it, they need that file and its manifest file." |
| "Who issued the trace? Could someone fake both?" | "Today the trace is made by whoever built the report, so between companies it's documentation. Signed traces that prove who issued them are on the roadmap." |
| "Where does the data live?" | "In your environment. TraceBi runs where your data is. Nothing is sent to us." |

## Words to use on stage

| Instead of | Say |
| --- | --- |
| manifest | trace |
| SHA-256 fingerprint, hash | fingerprint |
| star schema, grain, semantic layer | the definitions |
| sink, warehouse, DuckDB | the clean data |
| transform, pandas | the cleaning step |
| MCP gateway, agent | the AI assistant |
| reproduces | re-runs to the same number |
