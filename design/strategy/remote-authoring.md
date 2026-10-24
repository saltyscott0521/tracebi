# Remote authoring

> Written before the 2026-10 IA; page names updated to the five places (Reports, Ask, Data, Review, Docs).

**People build and change reports from wherever their agent runs: a hosted
chat (ChatGPT or Claude, through the TraceBi connector), or Claude Code on
their own laptop. Everything they make lands as a draft on the TraceBi server,
is seen rendered in the app while it is being made, and goes live only by
publishing. Code that runs on the server, pipelines and transforms, is
published only after someone approves it.**

Status: built (decided 2026-10-08; steps 1 to 4 shipped by 2026-10-17).
Builds steps 4 and 6 of [Report library](report-library.md). How to use it:
[Connect ChatGPT and Claude](../../docs/guides/connect-chatgpt-and-claude.md), [Push from a laptop](../../docs/guides/push-from-a-laptop.md), [Folder permissions (_folder.yaml)](../../docs/reference/folder-yaml.md). The
sandbox for remote Python is still ahead.

---

## Two environments: dev and prod

| | Dev: drafts | Prod: the published library |
|---|---|---|
| Where | `drafts/<owner>/` on the server | `reports/`, `models/`, `pipelines/`, `transforms/` |
| Who changes it | The owner (their agent) | Only publishing |
| Seen in the app | Its draft page under Review, rendered live | Every page, as today |
| Scheduled, delivered | No | Yes |

A UAT stage can sit between them later. Nothing here assumes two.

## Three ways in, one destination

```
 Hosted chat (ChatGPT, Claude)  ─┐  /mcp, signed in as the person
                                 ├──────────────► drafts/<owner>/ ──publish──► library
 Claude Code on a laptop ────────┤  tracebi push, or a git PR ─────────────────► library
                                 │
 The app (browser) ──────────────┘  sees drafts live, publishes, approves
```

**Submit code, never data.** A laptop builds against its own connections and a
local warehouse to preview. What reaches the server is files. The server runs
pipelines with its own secrets and builds its own warehouse; sink contracts
check what landed there. Connections are named (`tracebi connect` writes
`connections/<name>.yaml`, whose secrets are `${NAME}` references), so the
same code runs on the laptop with a dev secret and on the server with the
production one ([Connection files (YAML)](../../docs/reference/connections-yaml.md), [Credentials](../../docs/reference/credentials.md)).

## What may come in which way

A report package is a closed vocabulary that can only ask the model questions,
so it is safe to accept from anyone allowed to build. Python runs on the server
with production secrets, so it is not.

| | Report package | Declarative model (`models/<name>.yaml`) | Code: `report.py`, `models/*.py`, transforms (`.sql` or `.py`), pipelines, connections |
|---|---|---|---|
| Hosted chat over `/mcp` | draft → publish | draft → publish | refused |
| Laptop: `tracebi push` | draft → publish | draft → publish | publish **request** → approval |
| Laptop: git PR | review → merge | review → merge | review → merge |

A sandbox that runs remote Python drafts (a locked-down worker with dev
credentials and no production secrets) is a later step, TraceBi Cloud first.

## Roles

The existing roles, unchanged in meaning (Authorization in `CLAUDE.md`):

| Role | Drafts | Publish | Approve code |
|---|---|---|---|
| viewer | none (read-only tools only over `/mcp`) | no | no |
| analyst | their own | reports and declarative models | no |
| admin | everyone's | yes | yes |

Folder permissions ([Folder permissions (_folder.yaml)](../../docs/reference/folder-yaml.md)) narrow this per folder; the check
stays in one place.

---

## Step 1 — Drafts (contracts)

### Storage: `tracebi/drafts.py`

- Root: `TRACEBI_DRAFTS_DIR`, default `drafts/` beside the project.
- Owner: the acting principal (`tracebi.audit` actor), slugged to
  `[a-z0-9._-]` (lowercase; anything else becomes `-`). Over `/mcp` with the
  shared token it is `TRACEBI_MCP_ACTOR`'s value; after step 2 it is the
  signed-in person.
- Layout:
  - `drafts/<owner>/reports/<path>/` — `report.json`, `template.html`,
    `style.css`, `script.js`. `<path>` is a report path (`folder/name`), validated by
    `report_paths.report_name_error`.
  - `drafts/<owner>/models/<name>.json` — a declarative model.
- Files a draft may hold: exactly those. No `report.py`, no other file.
  `script.js` is accepted because the browser, not a review of the code, is
  its boundary: every report frame is sandboxed, so it cannot reach the app
  (see `analyst-freedom`, "Custom JavaScript in reports"). Each at most 512 KB, UTF-8 text.
- Starting a draft from a published report copies its four files; a
  published report with a `report.py` cannot be drafted remotely (the error
  says to edit it from a laptop).
- Functions (all take `owner` explicitly; the web and MCP layers pass the
  actor): `start_draft`, `list_drafts`, `read_draft`, `write_draft_file`,
  `delete_draft`, `draft_dir`, `publish_draft`.

### Publishing

- `publish_draft(owner, kind, path, actor, note=None)`:
  1. Validate: a report package must render (`TemplatePackage(...).render`
     into a temporary file, against published models plus the owner's draft
     models); a declarative model must compile and load.
  2. Keep the previous published version under
     `.tracebi/history/<kind>/<path>/<UTC timestamp>/`.
  3. Copy the draft's files into the library (`reports/<path>/` in the first
     library root, or `models/<name>.json`).
  4. Record a run: `kind="publish"`, `target=<kind>/<path>`, actor, detail
     `{version, note}`.
- Live discovery picks the published files up within
  `TRACEBI_DISCOVERY_INTERVAL`. The draft is kept.

### Preview

The draft preview is the dev-mode workbench preview pointed at the draft's
directory: `workbench.package_version(dir)` for change detection and
`TemplatePackage(dir).render_exploration(models)` for the page. Models are the
published ones, with the owner's draft models shadowing published ones of the
same name (preview only). Not a build: no file written, no trace.

### MCP tools (analyst and up; viewers get none of them)

| Tool | Does |
|---|---|
| `list_drafts` | The caller's drafts: kind, path, updated, whether published differs |
| `start_draft(kind, path, from_published=False)` | Create an empty draft or copy the published one |
| `read_draft(kind, path)` | The draft's files |
| `write_draft_file(kind, path, file, content)` | Write one allowed file |
| `preview_draft(kind, path)` | Validate and render; errors, warnings, and the draft's URL |
| `publish_draft(kind, path, note="")` | Publish (see above) |

The draft URL is `{TRACEBI_PUBLIC_URL}/drafts/<owner>/<kind>/<path>`. It is
stable: it outlives MCP sessions and chats. The agent gives it to the person
once.

### HTTP API

| Method | Path | Role |
|---|---|---|
| GET | `/api/drafts` | viewer: own drafts (an admin sees everyone's) |
| POST | `/api/drafts` | analyst: start (or open) your own draft of a published report or model |
| PUT | `/api/drafts/{owner}/{kind}/{path}/files/{file}` | analyst; owner or admin (returns the new version) |
| GET | `/api/drafts/{owner}/{kind}/{path}/version` | owner or admin |
| GET | `/api/drafts/{owner}/{kind}/{path}/preview` | owner or admin (HTML) |
| GET | `/api/drafts/{owner}/{kind}/{path}/files` | owner or admin |
| POST | `/api/drafts/{owner}/{kind}/{path}/publish` | analyst; owner or admin |
| DELETE | `/api/drafts/{owner}/{kind}/{path}` | analyst; owner or admin |

### UI

- **Drafts** under Review (`/review/drafts`): the person's drafts, newest
  first.
- **The Draft page** (`/drafts/<owner>/<kind>/<path>`): the report rendered
  live (polls `version`, re-fetches `preview` when it changes), its files in a
  Files tab, and **Publish** with an optional note. For an analyst or admin
  the Files tab is editable: **Edit** opens a file in a text box, **Save**
  writes it and the preview follows.
- **A signed-in person can start and edit a draft in the app**, without an
  agent: the `EditAsDraft` button (`web/ui/src/components/EditAsDraft.jsx`)
  calls `POST /api/drafts` for the published report or model, which copies it
  into the person's own drafts (or opens the one they already have), then goes
  to the Draft page. A Python model, or a report with a `report.py`, is
  refused with the same "edit it from a laptop" line as over MCP. A viewer is
  not offered the button and the routes refuse them.

### Declarative model: `models/<name>.json`

The JSON mirrors the builder calls one to one:

```json
{
  "name": "sales_model",
  "connectors": [{"name": "warehouse", "type": "duckdb", "database": "data/warehouse.duckdb"}],
  "tables": [{"name": "fact_orders", "connector": "warehouse", "source": "fact_orders"}],
  "dimensions": [{"name": "dim_region", "table": "dim_region", "key": "region_id", "attributes": ["region"]}],
  "facts": [{"name": "fact_orders", "table": "fact_orders", "measures": ["amount"],
             "foreign_keys": {"dim_region": "region_id"}}],
  "measures": [{"name": "revenue", "column": "amount", "agg": "sum", "format": "currency0"}]
}
```

- Connectors: `duckdb` with a project-relative `database`, or `{"name": X,
  "connection": X}` naming an existing `models/_connections/X.py`. No
  credentials in the file, ever.
- Measures take the same keywords `DataModel.add_measure` takes.
- Discovered beside `models/*.py`, structurally validated at discovery, loaded
  lazily like the Python form.

---

## Step 2 — A sign-in per person

ChatGPT and Claude connectors both sign people in with OAuth 2.1 as the MCP
authorization spec describes: a `401` pointing at protected-resource metadata
(RFC 9728), authorization-server metadata (RFC 8414), PKCE with S256, and a
client identity they get on their own: a Client ID Metadata Document (CIMD,
ChatGPT's preference) or Dynamic Client Registration (DCR). Company identity
providers (Entra ID, Okta) usually allow neither for outside apps, and Entra
also wants the MCP URL registered as an Application ID URI.

So **TraceBi runs its own small authorization server for `/mcp`, and hands
the actual login to the company's provider:**

```
 ChatGPT / Claude ──OAuth 2.1 (CIMD or DCR, PKCE)──► TraceBi /authorize, /token, /register
                                                        │  "who are you?"
                                                        ▼
                                              company IdP (OIDC: Entra, Okta, Google)
                                              one ordinary app registration
```

- TraceBi is an ordinary OIDC client of the company's provider (one app
  registration, any provider). The same login signs people into the app.
- For connectors, TraceBi's authorization server advertises CIMD
  (`client_id_metadata_document_supported`, `none` in
  `token_endpoint_auth_methods_supported`) and a `registration_endpoint` for
  DCR, requires PKCE S256, issues short-lived access tokens and rotating
  refresh tokens (`offline_access`), and answers refresh failures with
  `invalid_grant`. The MCP SDK's authorization-server hooks host these routes.
- Redirect URIs are allowlisted: `https://claude.ai/api/mcp/auth_callback`,
  ChatGPT's callback, and loopback on any port for Claude Code
  (`localhost` and `127.0.0.1`). The allowlist is configurable.
- Grants, clients and tokens live in the run store (Alembic revision), so
  several workers share them.
- The provider's groups map to viewer, analyst and admin through the existing
  role map. The person is the audit actor and the drafts owner everywhere.
- `tracebi login --server <url>` signs the CLI in through the same server
  (loopback redirect, as Claude Code does).
- The shared token stays for local and demo use.

## Step 3 — Submitting from a laptop

- `tracebi push <paths> --server <url>`: uploads report packages and
  declarative models into the person's drafts (the same checks as step 1), and
  Python files as a publish request (step 4).
- A library folder can be a git checkout; `POST /api/library/sync` (a webhook
  with its own secret) pulls `main`, and live discovery picks up the change.

Built 2026-10-17: `tracebi push` (`tracebi/_push.py`) and `POST /api/library/sync`
(`tracebi/web/api/routers/library.py`); [Push from a laptop](../../docs/guides/push-from-a-laptop.md). Connections
(`connections/*.yaml`) go as code too: they decide which server secrets a
transform reads.

## Step 4 — Pipelines, published with approval

- A publish request holds Python files (`pipelines/`, `transforms/`,
  `models/*.py`, `report.py`) with who asked and why. It is stored under
  `.tracebi/requests/<id>/`, with a row in a new run-store table (Alembic).
- An admin sees the request in the app (**Review**: the files, the diff
  against what is published) and approves or rejects it with a note.
- Approval copies the files in, keeps history as in step 1, and runs the
  pipeline once with the server's secrets; its sink contract checks what
  landed. The request records the run.

Built 2026-10-17: `tracebi/code_requests.py`, `tracebi_code_requests`
(Alembic 0006), **Code requests** under Review (Needs attention). The pipelines an approval
runs are the ones in the request plus each `pipelines/*.yaml` whose
`transform` it changes.

---

## Declarative by default (decided 2026-10-08)

Everything after the sink is data, not code; only transforms stay code
(phase ① is unconstrained by design). That also simplifies trust: only
transforms ever need code review and approval.

| Piece | Form |
|---|---|
| Models | `models/<name>.yaml` (or `.json`: JSON is YAML, one loader). Python models still load, for anything exotic |
| Sources | `connections/<name>.yaml`: a type and fields; secrets only as `${ENV_VAR}` references, never inline |
| Pipelines | `pipelines/<name>.yaml`: the transform, the models, the reports to rebuild, the schedule |
| Report packages | unchanged: `report.json` + HTML/CSS (`report.py` stays a laptop-only escape hatch) |
| Transforms | SQL by default (`transforms/<name>.sql` + `.contract.yaml`); Python is the escape hatch |

YAML because these files are written and reviewed by people, and a semantic
contract needs comments (why a measure is weighted, which trap it avoids).
`tracebi new-model` writes YAML; `tracebi migrate model models/x.py` converts
an existing model from its loaded form.

## Order of work

1. Drafts: storage, publish, MCP tools, HTTP API, the Drafts UI, the
   declarative model. Works with the shared token, so the loop can be demoed
   end to end from a connector.
2. A sign-in per person.
3. Submitting from a laptop.
4. Pipelines published with approval.
5. Later: a sandbox for remote Python drafts.
