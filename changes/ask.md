### Added — Ask: a question as a sentence, an answer with its definitions, Keep this

- `/ask?model=<m>` is one input: **Show [measure] by [dimension] for [filter],
  [order], top [n]**. Each slot is a token the model offers: its declared
  measures (with their descriptions), the dimension attributes the fact joins,
  their values (`GET /api/models/{name}/dimensions/{dim.attr}/values`, new),
  largest / smallest first or a dimension A to Z, and top 3 / 5 / 8 / 10 / 20
  or any number typed. Clicking a slot lists it; typing finds tokens over
  labels and descriptions, so "fair value by sector top 8" takes one token per
  part with Enter. Enter on an empty input asks; Backspace removes the last
  token. A measure another fact runs moves the question to that fact.
- **No language model in the app.** Free text only finds tokens; a question
  is always a query the model can run. Plain-English questions are the
  connected agent's job: when the app serves the gateway at `/mcp`, or runs in
  dev mode, a line under the input says "Or ask your agent: it answers from
  the same definitions" (`GET /api/status` gains `gateway`).
- The answer runs `POST /api/models/{name}/query` and draws only its rows:
  the question as a sentence with the row count from the response; a bar
  chart (one measure by one dimension, at most 12 rows; bars at 55% of the
  band, direct labels from the response's `display` text, labels wrapped,
  never cut) with a Chart | Table switch, a table (numbers right-aligned in
  the model's formats), or the number itself; each measure's definition in
  words ("Total fair value: the sum of fair value, in dollars"); the query in
  one line as the receipt writes it; and a **Not checked** chip ("A live query
  against <model>; built reports re-run and are checked — this answer is
  not"). Never green; no number is computed in the browser. "The query as
  code" holds the request JSON, the Python and the `report.json` binding.
- The question is in the URL (`&q=`), so a link reproduces it; the last five
  of the session sit under the input as **Recent**.
- **Keep this** (analyst and admin only) starts a report draft at an unused
  `<model>/<measures>_by_<dimensions>` and writes `report.json` (one binding,
  `answer`, holding the query, never its numbers) and `app.jsx` (a masthead
  with the question as its title, one `<Chart>`, `<Table>` or `<Kpi>` of that
  binding, the footer), then opens the draft's page, where preview and
  publish take over. A refusal is the server's own sentence in a toast.
- **Advanced** under the answer is the query builder (fact, measures with
  their descriptions, other columns, group by, filters, the full result and
  its lineage), editing the same question: a token picked above is ticked
  below and Run asks it. The code tabs moved up into the answer.
- The hidden `AskCut` on the report page (`SHOW_ASK = false`) is deleted, with
  the two selection hooks only it used.
