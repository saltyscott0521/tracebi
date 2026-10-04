# Game plan: epics

**Status: the live plan (reconciled 2026-10-03 evening).** This is the one
list of what to build next. It comes from an audit of the code against every
plan document in the repo (original audit 2026-09-24; checkboxes reconciled
against `main` again after the afternoon NOW wave landed E5, E9, E15, and
E3's connect path, then the same evening after E3's templates, E11's
delivery leftovers, and E6's Library list landed). The other plans
([[ROADMAP]], [[production-plan]], [[product-readiness-audit]],
[[next-level-plan]]) are kept for their reasoning and history. Where they
disagree with this file on order, this file wins.

**In one line:** the engine, the agent surface, one-server install, the
state store, the reader's report experience, the dashboard cookbook, the
path onto a client's own data, and unattended schedule delivery have
shipped. The leftover on NOW is Library mounts (E6). E1 Coolify ops are done.

---

## The plan on one page

```
                NOW                              NEXT                        LATER
              ┌──────────────────────┐   ┌───────────────────────┐   ┌────────────────────────┐
DISTRIBUTION  │ E1 leftover: Coolify │   │                       │   │ PyPI (when development │
get it into   │    on the tagged img │──▶│                       │   │ settles; held on       │
people's hands│                      │   │                       │   │ purpose)               │
              │ E3: done             │   │                       │   │                        │
              │                      │   │                       │   │                        │
              └──────────────────────┘   └───────────────────────┘   └────────────────────────┘
              ┌──────────────────────┐   ┌───────────────────────┐   ┌────────────────────────┐
PLATFORM      │ E6: list done;       │──▶│                       │──▶│ E7 People, permissions │
run it for a  │    mounts still open │   │                       │   │    and publishing      │
team          │    (almost done)     │   │                       │   │                        │
              │ E4 / E5: done        │   │                       │   │                        │
              └──────────────────────┘   └───────────────────────┘   └────────────────────────┘
              ┌──────────────────────┐   ┌───────────────────────┐   ┌────────────────────────┐
FRAMEWORK     │ E8 / E9 / E14 / E15: │   │                       │──▶│ E10 Warehouse-scale    │
the engine    │    done (E14         │──▶│                       │   │     engine             │
              │    decisions remain) │   │                       │   │                        │
              └──────────────────────┘   └───────────────────────┘   └────────────────────────┘
              ┌──────────────────────┐   ┌───────────────────────┐   ┌────────────────────────┐
WORKFLOWS     │ E11: done (Teams     │   │                       │──▶│ E12 Workbench in the   │
the three     │    deferred)         │──▶│                       │   │     web app            │
paths         │                      │   │                       │   │ E13 Ask anywhere       │
              │                      │   │                       │   │                        │
              └──────────────────────┘   └───────────────────────┘   └────────────────────────┘
```

**Shipped since the 2026-09-24 audit (code on `main`; package is
`0.7.0.dev0` after the `v0.6.0` release):** E2, E3, E4, E5, E8, E9, E11
(Teams deferred), E14's buildable pieces, E15, E1's release automation +
public demo URL, E6's path discovery + `open_report` + Library list.
The app's data path (Sources → Pipelines → Data model → Explore →
Reports) is also on `main`.

**Why this order:**

1. **Own data is in.** Connect, `new-model --from`, dbt import, and both
   `init --template` starters (saas-metrics, sales-pipeline) are on
   `main`, and the scaffold leads with ask / build / schedule.
2. **Library mounts, then people.** The Library list (schedule, last run,
   builds, last change) is in. Mounts are the open E6 piece; they are
   where permissions (E7) will attach.
3. **Schedules you can leave alone — done.** Retries, owner alerts,
   alert → Runs, Slack file delivery, and bursting are in. Teams stays
   deferred unless a customer asks.
4. **Ask waits.** Still the strategy's headline path, still later — the
   model and the library come first.
5. **Finish a path end to end before starting the next.** Carried over from
   [[product-strategy]]: a half-built path is worth less than a narrow,
   complete one.

---

## What the audit found

Original run (2026-09-24): the full suite (**1,437 passed, 1 skipped, 83%
line coverage**), a fresh `tracebi init`, and every gap named in the plan
documents checked against the code. Reconcile (2026-10-03 morning): closed
sub-issues #92–#116 / #122 / #136. Afternoon reconcile: E5 (#183/#184),
E9 (#162/#87 PDF + windowing), E15 (#173), E3 connect (#179), E11 retries
+ owner alerts, demo URL (#163). Evening reconcile: E3 templates (#190,
#192) and dbt import (#188), E6 Library list (#187), E11 Slack file
(#189), bursting (#191), and alert → Runs (#186) — findings below drop
what shipped.

### The plans are behind the code

Several things the plans list as gaps have shipped. The plan documents still
list them as open, which makes the real gaps harder to see.

| Plan says missing | Actually | Where |
| --- | --- | --- |
| A model stays loaded for the whole process | ✅ Reloads when the file changes | `model_registry.py` (mtime check) |
| `info()` tables have no columns | ✅ Columns from the connector's metadata, with no table scan | `DataModel._table_info` |
| A hand-typed number can ship | ✅ The build fails on a numeral outside a figure | `template_package.py` (prose gate) |
| Web renders don't keep the receipt | ✅ Kept in `output/` when writable, in memory when not | `routers/reports.py` `_last_build` |
| A download re-renders | ✅ The HTML download is the last build | `download_report` |
| The app leads with Connectors and Pipelines | ✅ Sources → Pipelines → Data model → Explore → Reports | `Layout.jsx` |
| Selections recompute through the model | ✅ `POST /api/reports/{name}/selection` and keep | `routers/reports.py` |
| `query_model` gives no binding to paste | ✅ It returns a `report.json` binding stub | `mcp_server.py` `_binding_stub` |
| No release / no GHCR image / wrong footer version | ✅ `v0.6.0` released; footer reads `/api/health` | `release.yml`, `Layout.jsx` |
| Schedules need a second process | ✅ Opt-in in-server schedules | `TRACEBI_SCHEDULES_IN_SERVER` |
| Flat `reports/` only; no path identity | ✅ Recursive discovery; path is the identity | `report_paths.py`, `discovery.py` |
| Agent blind spots (columns, failed models, pins) | ✅ `describe_table`, `list_models.skipped`, `resolve_pin`, evals, gateway log | `mcp_server.py`, `evals/agent/` |
| Receipt drawer is ids and hashes | ✅ Plain-words first line; fingerprint behind Details | `tracebi.js` / #101 |
| No connect / draft-from-warehouse | ✅ `tracebi connect` + `new-model --from` | `connect.py` / #179 |
| One state store / Runs page | ✅ `tracebi_runs` + Alembic + `/runs` | `state.py` / #183 / #184 |
| About footer / PDF / big tables | ✅ Default About, Playwright PDF, windowed tables | #162 / #87 |
| Named page layouts | ✅ `new-report --layout brief\|dashboard\|tabbed` | #173 |
| Demo URL disagrees across docs | ✅ Public demo is `https://tracebi.com/app` | #163 |
| No dbt import / no `init --template` | ✅ `tracebi import dbt`; `init --template saas-metrics` and `sales-pipeline` | #188 / #190 / #192 |
| Library list has no schedule, last run, builds, or last change | ✅ Those columns on the Reports list; owner is an em dash until E7 | `Reports.jsx` / #187 |
| Slack file, bursting, and alert → Runs still open | ✅ Slack file upload plus a short summary, `burst`, and the owner alert links to `/runs` | `schedule.py` / #189 / #191 / #186 |

### Still open, by area

**Distribution**

| Finding | Evidence |
| --- | --- |
| Coolify pointing the demo at the tagged GHCR image | ✅ `tracebi-demo` pulls `ghcr.io/saltyscott0521/tracebi:0.6.0`; auto-deploy off | Coolify / E1 |
| A git install still ships the API with no web UI unless the UI was built (release wheel includes it). | [[ROADMAP]] item 5 |

**Platform**

| Finding | Evidence |
| --- | --- |
| Mounts are still open (a local path or a network share as a top-level library folder). The Library list is in; owner stays an em dash until E7. `open_report` is the one read seam. | `report_paths.py`, E6 |
| **The "Keep this cut" endpoint rewrites `report.json` in place, with no draft or approval step.** It requires `admin` until drafts exist. Ask is hidden in the UI today (`SHOW_ASK = false`), but the endpoint is live. It contradicts the report-library rule that published reports change only through publishing. | `POST /api/reports/{name}/selection/keep` |
| One shared Basic-auth login, one shared MCP token, and a self-declared agent name. Nobody's work can be told apart in the audit log. | `web/api/auth.py`, `TRACEBI_MCP_ACTOR` |

**Agents**

| Finding | Evidence |
| --- | --- |
| E14 decisions not yet made: draft-writing tools for remote agents (after E7), OAuth for claude.ai connectors, rendered snapshot for agents. | #111 |

**What's strong** (keep it that way): the engine, receipts and `verify`; the
agent surface (MCP, context, guides enforced by tests); the honesty
discipline; model reload; the prose gate; the workbench; one-server compose
+ guide; the release tag path; the state store and Runs page; the About
footer and PDF path; named layout recipes; the own-data starters
(`connect`, `import dbt`, `init --template`); schedule delivery (retries,
owner alerts, Slack file, bursting, Runs links).

---

## The epics

Each epic has a goal, what's in it, when it's done, and a rough size (S = days,
M = one to two weeks, L = more).

### Distribution

#### E1 · Release pipeline — S/M · Now (code done; ops leftovers)

**Goal:** a tag produces everything a client installs, and every surface
shows the same version.

- [x] One version source: `/api/health` returns it and the UI footer reads it
      (drop the hard-coded `v0.5.2`). (#92)
- [x] On a `v*` tag, CI publishes the Docker image to GHCR
      (`ghcr.io/<owner>/tracebi:<version>` and `:latest`) and attaches the
      wheel (with the built UI) and the SBOM to a GitHub release. (#93;
      `v0.6.0` cut 2026-09-25)
- [x] The CHANGELOG `[Unreleased]` section becomes the release notes.
- [x] PyPI publish is wired but switched off, so turning it on later is one
      line. (Held on purpose until development settles; `PUBLISH_PYPI`.)
- [x] Coolify pulls the tagged image instead of building from `main`, so the
      demo runs the same bits a client would. (`ghcr.io/saltyscott0521/tracebi:0.6.0`;
      git auto-deploy off; application image retention disabled on the box.)
- [x] Fix the demo link in `site/README.md` and make every external link
      agree on one URL. (#163: public demo is `https://tracebi.com/app`;
      `demo.tracebi.com` stays an internal nginx host only.)

**Done when:** `git tag v0.6.0 && git push --tags` produces an image a client
can `docker pull` and a wheel whose `tracebi serve` shows the UI, both
reporting `0.6.0`. *(Met — tag, public demo URL, and Coolify on the GHCR image.)*

#### E2 · Run it on one server — M · Shipped

**Goal:** a small shop goes from a fresh VM to their own project running, with
schedules, in under 30 minutes.

- [x] A client compose file (`deploy/compose.yml`): the published image, a
      bind-mounted project folder (the library), SQLite state by default,
      Postgres as an optional profile, SMTP settings, no demo seeding. (#94)
- [x] Schedules run inside the web server when there's one process. It's an
      opt-in setting, which the client compose file turns on, so an existing
      server never starts sending email on its own. `tracebi schedule serve`
      stays for separate workers. (#102)
- [x] A status check that says what's wrong: output folder not writable,
      files that failed discovery, SMTP not set. (#103)
- [x] A one-page guide, "Run TraceBi on one server", written from the real
      Hetzner + Coolify setup, with a plain Docker path beside it. Backups are
      "copy this folder". (#104)
- [x] Startup logs the resolved auth posture (who gets what role) in one line.
      (#95)

**Done when:** following only the guide, a fresh VM serves a client project
whose scheduled report arrives by email, timed under 30 minutes.

#### E3 · Your own data in 30 minutes — M · Shipped

**Goal:** the first-report journey in [[users-and-jobs]] works on the
builder's own database, not only the sample data.

- [x] `tracebi connect`: asks for a warehouse (Postgres, Snowflake, BigQuery,
      DuckDB), tests it, writes the secret to `.env` and a connector to
      `models/_connections/` (discovery only loads top-level `models/*.py`
      that define `model`).
- [x] `tracebi new-model --from <connector> --tables a,b,c`: drafts a star
      schema from table metadata (the column metadata `info()` already reads),
      for the builder or their agent to edit and approve. No data scanned.
- [x] `tracebi import dbt <path>`: reads a dbt project's `manifest.json` and
      drafts a model over the marts ([[target-architecture]] decision 3), so a
      team with clean tables skips phase ① entirely. (#188)
- [x] `tracebi init --template <name>`: start with **SaaS metrics** and **sales
      pipeline**, each a model plus two reports over sample data, which an
      agent then points at real tables. (#190, #192)
- [x] The scaffolded README and `tracebi --help` lead with ask / build /
      schedule, per [[vision-and-positioning]]. Receipts become the "why you
      can trust it" line. (#161)
- [x] The connection `tracebi connect` writes reads its secret the way the
      rules already require: `models/_connections/<name>.py` calls
      `load_dotenv()` itself, and the framework still never loads `.env`
      implicitly.

**Done when:** timed from `pip install` to a scheduled report on a real
Postgres, under 30 minutes, by someone who didn't write the code.

### Platform

#### E4 · Quality floor — S · Shipped (ongoing)

**Goal:** fix the cheap things that erode trust in the codebase, and cover
the parts that run unattended.

- [x] Tests write to `tmp_path`, never the repo's `output/`. (#96)
- [x] Add `tzdata` to the `dev` extra. (#97)
- [x] Remove the dead scheduling path (`registry.scheduled()`, the `scheduled/`
      scaffold folder), or route it to `report.json` schedules. One way to
      schedule. (#105: `registry.scheduled` warns; `init` no longer scaffolds
      `scheduled/`; discovery still reads the folder if an old project has it)
- [x] Contract tests for the Snowflake and BigQuery connectors (mocked
      driver: connect arguments, `column_schema`, filter pushdown). (#98;
      `tests/test_warehouse_connectors.py`)
- [x] Scheduler failure paths: a failed refresh/build, a failed verify, and
      an SMTP error are each recorded and not silent. (#106)
- [x] A browser smoke test in CI: build the UI, serve the reference project,
      and open Desk, a report, the Source tab and a download. (#107;
      `tests/test_ui_smoke.py`)
- [x] Mark the older plan documents with a pointer to this file.
      (`docs/strategy/archive/`)

**Done when:** a clean checkout's `git status` stays clean after
`pytest tests/`, and CI opens the real app in a browser.

#### E5 · One state store — M · Shipped

**Goal:** everything that happened (pipeline runs, report builds, schedule
runs, background runs) is recorded in one place, and several workers can
share it.

- [x] One `tracebi_runs` shape for every kind of run (kind, target, actor,
      status, started, finished, output path, verdict). `schedule_runs.jsonl`
      is imported once into that table. (#183)
- [x] Background runs and the last-build pointer move from memory into the
      store, so `--workers 4` on Postgres works for polls and opens. (#183)
- [x] A schedule tick takes a Postgres advisory lock per report, like
      pipelines already do, so two workers never send the same email twice.
      (#183)
- [x] A Runs page in the app: what ran, when, for whom, and whether it
      reproduced. (`GET /api/runs`, viewer; the page is `/runs`, in the
      sidebar footer beside Verify.) (#184)
- [x] Adopt a migration tool for the state store (Alembic), per [[deployment]].
      (#183)

**Done when:** a test with two worker processes on Postgres starts a run on
one and polls it on the other, and a schedule tick fires exactly once.
*(Met.)*

#### E6 · Report library: folders — M · Now (almost done)

**Goal:** steps 1–2 of [[report-library]]. Reports live in folders people can
browse, and a report is addressed by its path.

- [x] Discovery scans `reports/` recursively; a report's identity is its path
      (`finance/month_end/close_pack`). The name stays as a display label.
      (2026-09-24: CLI, web API, gateway, schedules, the workbench and the
      Desk checks all take the path; `tracebi/report_paths.py` is the one
      name guard.)
- [x] Built outputs are stored per report path, not in one flat `output/`.
- [x] A read-only Library page: folders, each report's type, last change,
      schedule, last run and past builds. *(#187: the Reports list shows
      schedule, last run, build count, and last change, grouped by folder,
      beside type, last build, and receipt. Owner waits on E7 — no named
      accounts yet; the list shows an em dash, not a fake owner field.)*
- [ ] Mounts in configuration: several folders (a local path, a network share)
      as top-level library folders. *(Needs a design pass on the config
      shape.)*
- [x] Every read of a report (open, download, Source, MCP tools, schedules)
      goes through one function, where E7 will add the permission check.
      (`open_report` in `report_paths.py`; covered by
      `tests/test_report_folders.py`.)

**Done when:** two folders each hold a `weekly_summary`, both open, build
and schedule independently, and the Library page shows them in their folders.
*(Library list met; mounts still open.)*

#### E7 · People, permissions and publishing — L · Later

**Goal:** steps 3, 4 and 6 of [[report-library]]. A shared server knows who
each person is, what they may touch, and nothing published changes without
approval.

- [ ] Named accounts without an identity provider (the small shop), then
      OIDC sign-in (Google, Microsoft, Okta) with group mapping.
- [ ] Folder permissions (View, Build, Publish, Manage), inherited, checked in
      the one function from E6 for the app, MCP, the scheduler and the CLI.
- [ ] My work (drafts) and publish-with-approval, with TraceBi's own version
      history for folders without source control.
- [ ] **"Keep this cut" writes a draft and a publish request, not
      `report.json` in place.** (It writes the file directly today, and the
      endpoint requires `admin` until drafts exist; see the findings.)
- [ ] A sign-in per person on the MCP gateway, so an analyst's agent sees what
      the analyst sees and the audit log names them.
- [ ] A plain-language review screen: rendered before and after, which
      definitions changed, who asked.
- [ ] The git adapter (publish = a commit, or a pull request where the host
      has them), any host. Optional, never required.

**Done when:** an analyst's agent, signed in as that analyst, builds a draft
in My work; an approver with Publish on the folder approves it in the app;
it goes live; and the history shows both people.

### Framework

#### E8 · Agent surface: no blind spots — S/M · Shipped

**Goal:** an agent never has to guess, and we can measure how often it gets
a report right the first time.

- [x] `list_models` over MCP names models that failed to load, with the error.
      (#99)
- [x] A `describe_table` MCP tool and `tracebi warehouse tables`: columns and
      types of warehouse tables from connector metadata (`column_schema`, no
      scan), so an agent drafting a model never invents a column. (#108)
- [x] A `--host` flag for `tracebi mcp --transport http` (default
      `127.0.0.1`), so a server install can bind where its proxy expects.
      (#109)
- [x] Excel output over the gateway: `build_report` can return the `.xlsx`
      the library already renders ([[ROADMAP]] item 8). `format="xlsx"`
      writes the workbook beside the HTML; the spreadsheet carries no
      receipt. `fetch_artifact` returns it base64-encoded. (#110)
- [x] An agent eval set: written requests against the reference project, each
      with automatic checks (builds, `verify` reproduces, package shape).
      `evals/agent/score.py` prints a first-build success rate. (#100)
- [x] Every item follows the discoverability rule: `capabilities.py`,
      `AGENTS.md` and `tracebi/_scaffold/init_agents.md` in the same change.
      (`tests/test_agent_guides.py`)

**Done when:** an agent with only the gateway can list a broken model's
error, read a warehouse table's columns, and export Excel; and the eval
script prints a first-build success rate for a run.

#### E14 · Agents work with TraceBi end to end — M/L · Shipped (decisions remain)

**Goal:** an agent connected over MCP is told one consistent story, can close
every loop it's asked to close, and leaves a record of where it struggled,
so the agent surface improves from real use. Issue #111.

- [x] Resolve a pin from the CLI and over MCP. (#112)
- [x] The gateway's `instructions` and prompts teach the package lane. Add
      `answer_question` and `address_pins` prompts. (#113)
- [x] `tracebi init` writes `.mcp.json` and `.cursor/mcp.json`;
      `tracebi mcp config` prints the snippet for other clients. A second
      init without `--force` leaves an edited file alone. `--http` prints
      `Bearer ${TRACEBI_MCP_TOKEN}`, never a token value. (#114)
- [x] An opt-in gateway call log (tool, ok or error, argument *names* only,
      never values) and `tracebi agent log` to summarize it. (#115)
- [x] Run the eval set (#100) through the gateway, and report the top errors
      agents hit. (#116; `evals/agent/README.md` gateway-only mode +
      `--gateway-log`)
- [ ] Needs a decision first: draft-writing tools for remote agents (after
      E7), OAuth for claude.ai connectors, and a rendered snapshot so an
      agent can see the page it built.

**Done when:** an MCP-only agent in a fresh `tracebi init` project is told
the package lane, builds a report, resolves its pins and leaves a call log;
and the eval set run through the gateway prints a first-build success rate
and the top three errors. *(Buildable loop met; decision items still open.)*

**The loop this closes:** agents use the gateway → the call log and the eval
set show where they stumble → those become issues → agents fix the gateway.

#### E9 · The report explains itself — M · Shipped

**Goal:** the file that travels makes sense to a reader who has never heard
of TraceBi ([[product-readiness-audit]] "Make the reader's experience the
product").

- [x] The receipt drawer in plain words. A row reads "Fair value · $285.9M",
      then what it was computed from (the measure and its cut), with the
      fingerprint behind a disclosure. The drawer shows provenance; it must
      not claim a number reproduces, which only `verify` can say. (#101)
- [x] An "About this report" footer on by default: who built it, when, from
      which definitions, and what the receipt proves and doesn't, in the
      locked language. It builds on the existing `methodology` block. (#162)
- [x] Download as PDF, tested. The PDF is the built report HTML printed by
      headless Chromium (Playwright), so charts render. `HTMLRenderer.render_pdf()`
      (WeasyPrint, no JavaScript) is unchanged. (#87)
- [x] Large tables stay fast: a table past 500 rows renders only the
      visible window in `tracebi.js` (print and download still use every
      row; find-in-page does not — `data-tb-search` does). (#87)

**Done when:** someone outside the team opens a built report, finds the
receipt, and can say in their own words what it proves; and the PDF
download works from the app. *(Met.)*

#### E10 · Warehouse-scale engine — L · Later

**Goal:** a model query runs as one SQL statement in the warehouse, not by
loading the fact table into Python ([[target-architecture]] decision 2).

- [ ] A query compiler: a model query becomes one SQL statement (joins,
      filters, measures, window measures) in the warehouse's dialect.
      DuckDB first, as the reference.
- [ ] The parity rule: on a pinned corpus, the compiled result matches the
      in-process result exactly, or the fingerprints fork. A warehouse is
      marked supported only when its corpus passes.
- [ ] Postgres, then Snowflake and BigQuery.
- [ ] A per-run query cache, so a report that asks the same thing twice pays
      once.

**Start when:** the first client dataset doesn't fit comfortably in memory,
or a typical report build passes 60 seconds. Until then the in-process path
is correct and fast enough.

#### E15 · Dashboard cookbook — S · Shipped

**Goal:** an author, or the agent helping them, picks a page structure by
name instead of inventing a layout. Each recipe is a composition of pieces
the runtime already has. Adding a recipe is a scaffold and a vocabulary
entry, not a new design system.

**Recipes:**

| Recipe | What the page is | Built from |
| --- | --- | --- |
| `brief` | One finding: answer sentence, a few KPIs, one chart | `.tb-lede`, `.tb-grid` / `.tb-kpi`, one `.tb-card` |
| `dashboard` | The finding plus the cut beside the detail | `brief`, then `.tb-cols-2` (chart and filterable table). Default for `init` / `new-report` (#168) |
| `tabbed` | Two jobs on one file, one visible at a time | Same header, then `.tb-tabs` / `data-tb-tab` (Overview and Detail) |

- [x] Recipes named in `tracebi context` (`presentation.layout`). (#173)
- [x] `tracebi new-report --layout brief|dashboard|tabbed` writes that
      skeleton; default stays `dashboard`. (#173)
- [x] The `author_report` prompt offers the three names. (#173)
- [x] Discoverability: vocabulary, both agent guides, scaffold. (#173)

**Not a recipe (still true):** a nav bar between reports; a second
stylesheet. **Decision still open for a later recipe:** an in-page section
scroll-nav — do not build until someone asks for a long single-page recipe.

**Done when:** `tracebi new-report "Weekly" --layout tabbed` writes the
tabbed skeleton, `tracebi context` lists the three names, and omitting
`--layout` still writes the dashboard row. *(Met.)*

### Workflows

#### E11 · Schedules you can leave alone — M · Shipped

**Goal:** the Schedule path's Run, Deliver and Monitor steps are finished end
to end ([[product-strategy]]).

- [x] Retries with backoff for a failed refresh or build, then a recorded
      failure. Default two retries (1 minute, then 5 minutes); `"retries"`
      0–5 overrides. A refused receipt or a send failure is not retried.
- [x] Email the report's owner on a failure, empty data, or a receipt
      that didn't reproduce. The same text is posted to Slack when
      `TRACEBI_SLACK_WEBHOOK` is set (a ping, not the file).
- [x] Slack delivery of the file itself, not only a ping, plus a short
      in-body summary (the headline figures). (#189) *(Teams deferred — not
      needed unless a customer asks.)*
- [x] Per-recipient versions ("bursting"), using the filter grammar
      parameters from [[target-architecture]] decision 5. (#191)
- [x] The run history from E5 is what the alert links to. When
      `TRACEBI_PUBLIC_URL` is set, the owner alert links to
      `/runs?kind=schedule&target=…`. (#186)

**Done when:** a scheduled report whose source goes empty sends its owner an
alert instead of an empty report, and a transient failure retries and
succeeds without anyone doing anything. *(Met. Teams file delivery stays
deferred unless a customer asks.)*

#### E12 · Workbench in the web app — L · Later

**Goal:** an analyst on the shared server gets `tracebi dev`'s workbench
without a laptop install, and the note box becomes a real way to reach an
agent.

- [ ] A draft opened from My work (E7) shows the live preview, the timeline,
      and Figures & data, served by the web app instead of the dev server.
- [ ] Notes and "Keep this" requests land on the draft and reach the agent
      working on it, through `workbench_state` on the HTTP gateway.

**Done when:** from the browser only, an analyst leaves a note on a draft,
their agent picks it up over MCP, and the preview updates.

#### E13 · Ask anywhere — M · Later

**Goal:** the Ask path, when it's time: a question answered from the model,
not only on reports that opted in.

- [ ] Turn Ask back on (hidden today, `SHOW_ASK = false` in `Reports.jsx`),
      answering only from what's on the report or in its model.
- [ ] Ask on a model, not only on an open report.
- [ ] Every answer labels each number with its measure name; the fingerprint
      sits behind a "receipt" disclosure ([[product-readiness-audit]] P1-4).
- [ ] Opt the reference dashboard into `selection`, or keep Ask hidden on
      reports that can't answer (P1-3).
- [ ] "Keep this" on an answer opens a request (E7), not a file edit.

**Done when:** a question on the Desk returns a labeled answer from the
model, and keeping it creates a draft for review.

---

## How the work runs

Much of this plan will be built by coding agents (Cursor, Claude Code)
working unattended. These rules keep that safe.

1. **Every epic is a GitHub issue labeled `epic`.** Its smaller pieces are
   sub-issues.
2. **Only issues labeled `agent-ready` are for unattended agents.** Each
   one names the files it touches, what to do, and how to know it's done.
   `needs-design` means a person decides something first; an agent may
   comment a proposal but doesn't build it.
3. **One issue, one branch, one draft pull request.** An agent never merges,
   never pushes to `main`, and never works on two issues in one branch.
4. **Every pull request shows its checks:** `pytest tests/` and
   `ruff check .` pass, the issue's "done when" is demonstrated, and a
   `changes/` fragment records anything a user would notice (do not edit
   `CHANGELOG.md`; `.github/pull_request_template.md`).
5. **Coding agents follow `CLAUDE.md`.** `AGENTS.md` is the guide for agents
   that *use* TraceBi to build reports. `.cursor/rules/develop-tracebi.mdc`
   says so, so a Cursor agent doesn't mistake one for the other.
6. **Claude reviews, a person merges.** An hourly review pass checks every
   agent pull request against its issue and `CLAUDE.md`. It approves
   (label `claude-approved`) or requests specific fixes (label
   `changes-requested`, starting "@cursor"). After three rounds a pull
   request is labeled `needs-human`. Review findings outside a pull
   request's scope become new issues. A person merges.
7. **Issues that touch the same files run one after another,** not in
   parallel, or they'll conflict.

---

## Not in this plan, on purpose

| Not now | Why |
| --- | --- |
| PyPI release | Held until development settles. E1 wires it so it's a switch. |
| Signing receipts, retention archive, auditor view | The institutional (paid) tier. It needs E5 and E7 first. |
| Offline slicing in the browser ([[production-plan]] step 4) | Waits for parity, as that plan says. |
| Helm, Terraform, SOC 2 | When a customer asks. |
| Splitting `data_model.py` (3,400 lines) and `cli.py` (2,500) | Big but working and well tested. Split only where an epic already touches them. |
