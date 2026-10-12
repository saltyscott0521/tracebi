### Changed — a model's page is its Overview: the line from transform to report

- The sidebar is **Overview**, **Explore**, **Drafts** and **Verify a file**
  (Help in the footer). Data model, Refresh, Sources and Runs are no longer
  separate pages: they live inside the Overview, or behind its **History** link.
- The Overview draws how a model is made as three stations joined by two
  hand-offs: ① Transform (the transform its pipeline runs, and when it last
  ran), ② Model (its tables and joins), ③ Reports (how many are built and
  scheduled). The hand-offs name the warehouse file and the model's measures.
  Each station is a link with an address of its own: `/m/<model>/transform`,
  `/m/<model>/model` and `/m/<model>/reports` (also `/m/<model>`), so back,
  forward and deep links work; `?r=<report>` still opens a report.
- Only an exception is coloured, and always with words and a glyph: `✕ Failed
  2 min ago`, `△ 4 source changed`, `○ 1 never built`. The warehouse hand-off
  says what the sink contract says: `✕ 1 check failed`, `△ doesn't match its
  last check`, `○ no checks declared`; a fine thing is a plain fact. When the
  latest run failed, a line above the line says so and "See why" opens the
  Transform stage with the failing check open.
- **Refresh data** (admin) runs the model's pipeline from the Overview's header.
- `/m/<model>/refresh` and `/m/<model>/sources` open the Transform stage;
  `/refresh` opens the list of models. `/` opens the Overview of the model you
  were last in. Runs is called **History**. On a screen under 860px the line
  stands on end and the sidebar sits behind the menu button.

### Added — `transform` and `description` in `GET /api/pipelines`

- Each pipeline now says the transform it runs and its one-line `description`,
  as its `pipelines/<name>.yaml` states them.
