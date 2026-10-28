# Workspace and projects

TraceBi has three levels: one workspace per company, a project for each
area's reports, and the reports themselves.

```
Workspace     tracebi.yaml, the warehouse, sources,
│             transforms, models (shared), the brand
│
├─ Project    reports/saas_model/
│  ├─ Report  mrr_dashboard
│  └─ Report  cohort_brief
├─ Project    reports/portfolio_model/
│  ├─ Folder  q3/   (a folder stays a folder)
│  │  └─ Report  …
│  └─ Report  portfolio_dashboard
└─ My published   reports/my-published/<you>/
                  (your own space, not a project)
```

Any project may read any model in the workspace.

| Level | What it is | Where it lives |
|---|---|---|
| Workspace | Everything one `tracebi.yaml` covers: one warehouse, its sources, transforms and models, the brand and the default house theme. One per company. | The folder `tracebi init` creates |
| Project | One area's reports: a top-level library folder, named for the model or models it reads. It keeps its permissions in its `_folder.yaml`. | `reports/<project>/` |
| Report | One page whose every figure is a query against a model ([[report]]). | `reports/<project>/<report>/` |

## What is shared, and what is a project's own

- **Shared at the workspace:** sources, transforms, the warehouse and the
  models. Two projects can read one model; neither owns it. A model change
  reaches every report that reads it, whichever project it is in.
- **A project's own:** its reports, its folders, and who may see, build in
  and publish into it (`reports/<project>/_folder.yaml`, [[folder-yaml]]).
- **Themes are set at two levels only:** a report (`report.json` `"theme"`)
  or the workspace (`tracebi.yaml` `brand: {theme: …}`). There is no project
  theme ([[chart-style]]).

## In the app

The library (`/`) shows a tile per project, then a row of covers for each.
A project's page (`/?folder=<project>`) names it **Project** above its title
and lists its reports by kind, the models it reads, and its permissions. The
sidebar's library tree lists the same projects; ⌘K finds them under
**Projects**.

Data (`/data`) is the workspace: every source, transform, warehouse table and
model, whichever project reads it.

## Older words

Before 2026-10-28 the handbook called the workspace a "project". Nothing
moved on disk and nothing was renamed in the files or the API:

- `tracebi.yaml` keeps its name and keys; `project_config.py` and the
  `TRACEBI_PROJECT_DIR` deploy variable keep theirs.
- The API and the files still say *folder*: `/api/folders`, `?folder=` (the app
  also takes `?project=`), the `folder` field, `_folder.yaml`.
- The gateway's `describe_project` keeps its name; it describes the workspace.
  `describe_workspace` is the same tool under the new word.
- `--project` on `tracebi connect` is a BigQuery GCP project id, as before.

## Next

- Lay out a workspace: [[quickstart]]
- Who may do what in a project: [[folder-yaml]]
- How data moves through a workspace: [[the-three-phase-workflow]]
