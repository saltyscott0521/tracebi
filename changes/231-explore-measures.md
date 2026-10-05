### Changed — Explore asks in the model's language

- **Explore leads with the model's named measures.** Each shows its name and what it
  means, you tick them, and the query is sent as the list a report's `data` binding
  uses (`"measures": ["fair_value", "positions", "mark"]`), so "positions by sector"
  and "mark" can be asked. The raw columns with an aggregation picker are still
  there, folded under **Other columns**; the two forms can't be mixed in one query,
  so ticking one kind switches the other off.
- **A fact only offers the measures it can run.** `GET /api/models/{name}` lists
  `runnable_measures` on each fact: the declared measures whose columns exist on
  that fact's table (a measure is declared once on the model, and the model now says
  where it works). When the connector can't describe the table, every measure is
  listed and a run reports the real error. `describe_model` / `tracebi context
  --model` carry it too.
- **Results are written the way a built report writes them.** `POST
  /api/models/{name}/query` returns `display` beside `data`: each row's cells as text,
  from the same code the report build's server-side render uses (the model's declared
  format, else the shape default: `$75,229,747`, `97.0%`, a year as `1979`). `data`
  keeps the raw values, so the CSV download is unchanged. The chart tooltip shows the
  display text, and the chart plots the picked measures that share the first one's
  unit (dollars with dollars), saying which; the rest are in the table.
- **The query as code** shows the measure list exactly as sent.
