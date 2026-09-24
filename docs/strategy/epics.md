# Game plan: epics

**Status: the live plan (2026-09-24).** This is the one list of what to build
next. It comes from an audit of the code against every plan document in the
repo. The other plans ([[ROADMAP]], [[production-plan]],
[[product-readiness-audit]], [[next-level-plan]]) are kept for their reasoning
and history. Where they disagree with this file on order, this file wins.

**In one line:** the engine is ready and most of the production plan's first
step has shipped. What's missing is almost all *around* the engine: a
repeatable way to get TraceBi onto a client's server, a way onto a client's
own data, and the team features (folders, people, run history) a shared
server needs.

---

## The plan on one page

```
                NOW (next ~4 weeks)         NEXT                        LATER
              ┌──────────────────────┐   ┌───────────────────────┐   ┌────────────────────────┐
DISTRIBUTION  │ E1 Release pipeline  │   │ E3 Your own data in   │   │ PyPI (when development │
get it into   │ E2 Run it on one     │──▶│    30 minutes         │   │ settles; held on       │
people's hands│    server            │   │                       │   │ purpose)               │
              └──────────────────────┘   └───────────────────────┘   └────────────────────────┘
              ┌──────────────────────┐   ┌───────────────────────┐   ┌────────────────────────┐
PLATFORM      │ E4 Quality floor     │   │ E5 One state store    │   │ E7 People, permissions │
run it for a  │    (the quick fixes) │──▶│ E6 Report library:    │──▶│    and publishing      │
team          │                      │   │    folders            │   │                        │
              └──────────────────────┘   └───────────────────────┘   └────────────────────────┘
              ┌──────────────────────┐   ┌───────────────────────┐   ┌────────────────────────┐
WORKFLOWS     │                      │   │ E8 Schedules you can  │   │ E9 Workbench in the    │
the three     │                      │   │    leave alone        │   │    web app             │
paths         │                      │   │                       │   │ E10 Ask anywhere       │
              └──────────────────────┘   └───────────────────────┘   └────────────────────────┘
```

**Why this order:**

1. **Small-shop gaps first.** [[deployment]] already says it: they are cheaper,
   and small teams are where early adoption comes from. The Hetzner + Coolify
   setup this project runs on today is the template for a client install.
   E1 and E2 turn it into something a client can repeat.
2. **Folders before people.** Permissions need somewhere to attach. The
   library (E6) is that place, and it needs one state store (E5) under it.
3. **Ask waits.** It is the strategy's headline path, but it isn't needed
   right away. The model it answers from, and the reports it grows into, come
   first.
4. **Finish a path end to end before starting the next.** Carried over from
   [[product-strategy]]: a half-built path is worth less than a narrow,
   complete one.

---

## What the audit found

Run, not only read: the full suite (**1,437 passed, 1 skipped, 83% line
coverage**), a fresh `tracebi init` (under a second), and every gap named in
the plan documents checked against the code.

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
| The app leads with Connectors and Pipelines | ✅ Desk, Report, Contract lead | `Layout.jsx` |
| Selections recompute through the model | ✅ `POST /api/reports/{name}/selection` and keep | `routers/reports.py` |
| `query_model` gives no binding to paste | ✅ It returns a `report.json` binding stub | `mcp_server.py` `_binding_stub` |

That's most of step 1 of [[production-plan]], plus its step 2.

### Still open, by area

**Distribution**

| Finding | Evidence |
| --- | --- |
| No release has ever been cut. No git tags; the release workflow builds a wheel and publishes nothing. | `git tag` is empty; `.github/workflows/release.yml` says "no publish" |
| No Docker image is published. Every server builds from a checkout. | `docs/strategy/deployment.md` |
| A git install ships the API with no web UI. The built UI is gitignored and only the release workflow builds it. | [[ROADMAP]] item 5 |
| The app shows the wrong version: the footer is hard-coded `v0.5.2`; the package is `0.6.0.dev0`. | `web/ui/src/components/Layout.jsx:305` |
| The only compose file is the demo stack with seeded data. A client has nothing to point at their own project. | `docker-compose.yml` |
| No "run it on one server" guide, even though that's how this project runs today (Hetzner + Coolify). | `docs/guides/` |
| No path onto a client's own data: no connection setup, no model drafted from warehouse tables, no `init --template`. | `tracebi init --help` |
| Messaging disagrees with the strategy. The CLI help and the `init` README lead with "the trust layer for AI-generated analytics"; [[vision-and-positioning]] makes receipts a supporting feature and leads with ask / build / schedule. | `tracebi --help`, the scaffolded `README.md` |
| `site/README.md` still points "Try the demo" at `demo.tracebi.com`, which didn't resolve at the last check. | `site/README.md:48`, `UX_FEEDBACK.md` |

**Platform**

| Finding | Evidence |
| --- | --- |
| Background runs and the last-build cache live in one process's memory. With `--workers 4`, a poll can land on a worker that never saw the run. | `web/api/run_store.py`, `_LAST_BUILD` |
| Run history is in three places: pipeline tables, `schedule_runs.jsonl`, and the in-memory run store. | `pipeline/runner.py`, `schedule.py`, `run_store.py` |
| Schedules need a second process (`tracebi schedule serve`). A one-box install needs them inside the server. | [[deployment]] "Next" |
| Reports are keyed by name and discovery reads one flat folder, so two folders can't both hold a `weekly_summary`. | `web/discovery.py` (`os.listdir`) |
| **The "Keep this cut" endpoint rewrites `report.json` for any analyst, with no draft or approval step.** Ask is hidden in the UI today (`SHOW_ASK = false`), but the endpoint is live. It contradicts the report-library rule that published reports change only through publishing. | `POST /api/reports/{name}/selection/keep` |
| One shared Basic-auth login, one shared MCP token, and a self-declared agent name. Nobody's work can be told apart in the audit log. | `web/api/auth.py`, `TRACEBI_MCP_ACTOR` |
| A dead scheduling path is still scaffolded: `registry.scheduled()` is never read, and `tracebi init` still creates `scheduled/`. | [[target-architecture]] debt 1 |

**Quality**

| Finding | Evidence |
| --- | --- |
| The warehouse connectors companies will use most are the least tested: Snowflake 20%, BigQuery 39%. | coverage run |
| The scheduler, the thing that must run unattended, is at 65%. | `tracebi/schedule.py` |
| The React app has no tests and no lint; CI only checks that it builds. | `.github/workflows/ci.yml` |
| Tests write receipts into the repo's `output/`, so every contributor sees stray files after a run. | [[product-readiness-audit]] P2-1, still open |
| `tzdata` isn't a dev dependency, so one test file fails on slim Linux images. | P2-4, still open |
| Eight overlapping plan documents, with no single marker saying which one is current. | `docs/strategy/`, `docs/architecture/`, `docs/ROADMAP.md`, `NOTES.md` |

**What's strong** (keep it that way): the engine, receipts and `verify`; the
agent surface (MCP, context, guides enforced by tests); the honesty
discipline; model reload; the prose gate; and the workbench.

---

## The epics

Each epic has a goal, what's in it, when it's done, and a rough size (S = days,
M = one to two weeks, L = more).

### Distribution

#### E1 · Release pipeline — S/M · Now

**Goal:** a tag produces everything a client installs, and every surface
shows the same version.

- [ ] One version source: `/api/health` returns it and the UI footer reads it
      (drop the hard-coded `v0.5.2`).
- [ ] On a `v*` tag, CI publishes the Docker image to GHCR
      (`ghcr.io/<owner>/tracebi:<version>` and `:latest`) and attaches the
      wheel (with the built UI) and the SBOM to a GitHub release.
- [ ] The CHANGELOG `[Unreleased]` section becomes the release notes.
- [ ] PyPI publish is wired but switched off, so turning it on later is one
      line. (Held on purpose until development settles.)
- [ ] Coolify pulls the tagged image instead of building from `main`, so the
      demo runs the same bits a client would.
- [ ] Fix the demo link in `site/README.md` and make every external link
      agree on one URL.

**Done when:** `git tag v0.6.0 && git push --tags` produces an image a client
can `docker pull` and a wheel whose `tracebi serve` shows the UI, both
reporting `0.6.0`.

#### E2 · Run it on one server — M · Now

**Goal:** a small shop goes from a fresh VM to their own project running, with
schedules, in under 30 minutes.

- [ ] A client compose file (`deploy/compose.yml`): the published image, a
      bind-mounted project folder (the library), SQLite state by default,
      Postgres as an optional profile, SMTP settings, no demo seeding.
- [ ] Schedules run inside the web server when there's one process (a
      setting, on by default with SQLite). `tracebi schedule serve` stays for
      separate workers.
- [ ] A health check that says what's wrong: output folder not writable,
      warehouse unreachable, SMTP not set.
- [ ] A one-page guide, "Run TraceBi on one server", written from the real
      Hetzner + Coolify setup, with a plain Docker path beside it. Backups are
      "copy this folder".
- [ ] Startup logs the resolved auth posture (who gets what role) in one line.

**Done when:** following only the guide, a fresh VM serves a client project
whose scheduled report arrives by email, timed under 30 minutes.

#### E3 · Your own data in 30 minutes — M · Next

**Goal:** the first-report journey in [[users-and-jobs]] works on the
builder's own database, not only the sample data.

- [ ] `tracebi connect`: asks for a warehouse (Postgres, Snowflake, BigQuery,
      DuckDB), tests it, writes the secret to `.env` and a connector to
      `models/`.
- [ ] `tracebi new-model --from <connector> --tables a,b,c`: drafts a star
      schema from table metadata (the column metadata `info()` already reads),
      for the builder or their agent to edit and approve. No data scanned.
- [ ] `tracebi init --template <name>`: start with **SaaS metrics** and **sales
      pipeline**, each a model plus two reports over sample data, which an
      agent then points at real tables.
- [ ] The scaffolded README and `tracebi --help` lead with ask / build /
      schedule, per [[vision-and-positioning]]. Receipts become the "why you
      can trust it" line.
- [ ] The connection `tracebi connect` writes reads its secret the way the
      rules already require: the generated model file calls `load_dotenv()`
      itself, and the framework still never loads `.env` implicitly.

**Done when:** timed from `pip install` to a scheduled report on a real
Postgres, under 30 minutes, by someone who didn't write the code.

### Platform

#### E4 · Quality floor — S · Now (and ongoing)

**Goal:** fix the cheap things that erode trust in the codebase, and cover
the parts that run unattended.

- [ ] Tests write to `tmp_path`, never the repo's `output/`.
- [ ] Add `tzdata` to the `dev` extra.
- [ ] Remove the dead scheduling path (`registry.scheduled()`, the `scheduled/`
      scaffold folder), or route it to `report.json` schedules. One way to
      schedule.
- [ ] Contract tests for the Snowflake and BigQuery connectors (mocked
      driver: connect arguments, `column_schema`, filter pushdown).
- [ ] `schedule.py` to 85%+: a failed build, a failed verify, an SMTP error,
      and a missed tick are each recorded and not silent.
- [ ] A browser smoke test in CI: build the UI, serve the reference project,
      and open Desk, a report, the Source tab and a download (Playwright is
      already used in development).
- [ ] Mark the older plan documents with a pointer to this file.

**Done when:** a clean checkout's `git status` stays clean after
`pytest tests/`, and CI opens the real app in a browser.

#### E5 · One state store — M · Next

**Goal:** everything that happened (pipeline runs, report builds, schedule
runs, background runs) is recorded in one place, and several workers can
share it.

- [ ] One `tracebi_runs` shape for every kind of run (kind, target, actor,
      status, started, finished, output path, verdict). `schedule_runs.jsonl`
      is migrated in.
- [ ] Background runs and the last-build pointer move from memory into the
      store, so `--workers 4` on Postgres works for polls and opens.
- [ ] A schedule tick takes a Postgres advisory lock per report, like
      pipelines already do, so two workers never send the same email twice.
- [ ] A Runs page in the app: what ran, when, for whom, and whether it
      reproduced.
- [ ] Adopt a migration tool for the state store (Alembic), per [[deployment]].

**Done when:** a test with two worker processes on Postgres starts a run on
one and polls it on the other, and a schedule tick fires exactly once.

#### E6 · Report library: folders — M · Next

**Goal:** steps 1–2 of [[report-library]]. Reports live in folders people can
browse, and a report is addressed by its path.

- [ ] Discovery scans `reports/` recursively; a report's identity is its path
      (`finance/month_end/close_pack`). The name stays as a display label.
- [ ] Built outputs are stored per report path, not in one flat `output/`.
- [ ] A read-only Library page: folders, each report's type, owner, last
      change, schedule, last run and past builds.
- [ ] Mounts in configuration: several folders (a local path, a network share)
      as top-level library folders.
- [ ] Every read of a report (open, download, Source, MCP tools, schedules)
      goes through one function, where E7 will add the permission check.

**Done when:** two folders each hold a `weekly_summary`, both open, build
and schedule independently, and the Library page shows them in their folders.

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
      `report.json` in place.** (It writes the file directly today; see the
      findings.)
- [ ] A sign-in per person on the MCP gateway, so an analyst's agent sees what
      the analyst sees and the audit log names them.
- [ ] A plain-language review screen: rendered before and after, which
      definitions changed, who asked.
- [ ] The git adapter (publish = a commit, or a pull request where the host
      has them), any host. Optional, never required.

**Done when:** an analyst's agent, signed in as that analyst, builds a draft
in My work; an approver with Publish on the folder approves it in the app;
it goes live; and the history shows both people.

### Workflows

#### E8 · Schedules you can leave alone — M · Next

**Goal:** the Schedule path's Run, Deliver and Monitor steps are finished end
to end ([[product-strategy]]).

- [ ] Retries with backoff for a failed refresh or build, then a recorded
      failure.
- [ ] Alerts to the report's owner on a failure, empty data, or a receipt
      that didn't reproduce: email first, Slack after.
- [ ] Slack and Teams delivery of the file itself, not only a ping, plus a
      short in-body summary (the headline figures).
- [ ] Per-recipient versions ("bursting"), using the filter grammar
      parameters from [[target-architecture]] decision 5.
- [ ] The run history from E5 is what the alert links to.

**Done when:** a scheduled report whose source goes empty sends its owner an
alert instead of an empty report, and a transient failure retries and
succeeds without anyone doing anything.

#### E9 · Workbench in the web app — L · Later

**Goal:** an analyst on the shared server gets `tracebi dev`'s workbench
without a laptop install, and the note box becomes a real way to reach an
agent.

- [ ] A draft opened from My work (E7) shows the live preview, the timeline,
      and Figures & data, served by the web app instead of the dev server.
- [ ] Notes and "Keep this" requests land on the draft and reach the agent
      working on it, through `workbench_state` on the HTTP gateway.
- [ ] Excel output over the gateway (the renderer already exists;
      [[ROADMAP]] item 8).

**Done when:** from the browser only, an analyst leaves a note on a draft,
their agent picks it up over MCP, and the preview updates.

#### E10 · Ask anywhere — M · Later

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

## Not in this plan, on purpose

| Not now | Why |
| --- | --- |
| PyPI release | Held until development settles. E1 wires it so it's a switch. |
| Warehouse query pushdown ([[ROADMAP]] 15) | Needed at warehouse scale. The first clients will fit in memory; revisit with the first large dataset. |
| Signing receipts, retention archive, auditor view | The institutional (paid) tier. It needs E5 and E7 first. |
| Offline slicing in the browser ([[production-plan]] step 4) | Waits for parity, as that plan says. |
| Helm, Terraform, SOC 2 | When a customer asks. |
| Splitting `data_model.py` (3,400 lines) and `cli.py` (2,500) | Big but working and well tested. Split only where an epic already touches them. |
