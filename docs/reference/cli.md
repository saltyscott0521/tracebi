# CLI reference

Every `tracebi` command, grouped by task. Most days you use these five:

```bash
tracebi dev                      # the app in dev mode (no name: the workspace feed)
tracebi run-transform holdings   # clean the inputs and write the warehouse (.sql, .py or .ipynb)
tracebi report build my_report   # build one self-contained .html and its trace
tracebi report status my_report  # what each figure has earned
tracebi verify output/my_report.html.manifest.json
```

Global flags come before the subcommand:

```bash
tracebi [--models-dir DIR] [--pipelines-dir DIR] [--connections-dir DIR] <command> [...]
```

Their defaults come from the environment ([[environment-variables]]).

## Create a workspace

### `tracebi init`

```bash
tracebi init <workspace> [--force] [--template NAME]
```

Creates a complete workspace: `tracebi.yaml`, `inputs/`, `connections/`,
`transforms/`, `models/`, `pipelines/` and `reports/`, with a sample input,
transform (pandas), model, pipeline and report
(`reports/sample_model/sample_dashboard/`), plus `.gitignore`, `.env.example`,
`README.md`, `AGENTS.md`, `.mcp.json` and `.cursor/mcp.json`. `data/` and
`output/` appear on the first run.

| Flag | Effect |
|---|---|
| `--template NAME` | Start from `saas-metrics` or `sales-pipeline` instead of the sample. An unknown name is refused with the list. |
| `--force` | Overwrite existing files; required for a non-empty directory. Without it, existing files are skipped with a note. |

### `tracebi connect`

```bash
tracebi connect <name> --kind postgres|snowflake|bigquery|duckdb [--test|--no-test] [--force] [--store dotenv|secret]
tracebi connect wh --kind postgres --url postgresql://user:pass@host/db
tracebi connect wh --kind snowflake --account ACCT --user USER --password SECRET \
    --warehouse WH --database DB --schema PUBLIC [--role ROLE]
tracebi connect wh --kind bigquery --project PROJ --dataset ANALYTICS \
    [--credentials /path/service-account.json]
tracebi connect wh --kind duckdb --database data/warehouse.duckdb
tracebi connect crm --agents accounts,clients   # which tables agents may read
tracebi connect --list
```

Tests the connection, then writes `connections/<name>.yaml`
([[connections-yaml]]) with the secret named as `${NAME}`, and the secret
itself to `.env`.

| Flag | Effect |
|---|---|
| `--no-test` | Skip the connection test. Nothing is written when the test fails. |
| `--force` | Replace an existing `.env` key or connection file. |
| `--store secret` | Put the secret in the encrypted store (`.tracebi/secrets.yml.enc`, [[credentials]]) instead of `.env`. |
| `--agents a,b` | Which tables agents may read (`agents:` in the file; `all` for every table). With no `--kind`, changes only that on an existing connection. |
| `--list` | Print each connection with its type and the tables agents may read. |
| `--python` | Write the older module `models/_connections/<name>.py` instead. It calls `load_dotenv()` and always reads `.env`. |

The secret is never printed, and other lines in `.env` stay as they are.
Missing required flags are prompted on a terminal (passwords without echo);
otherwise the command exits 2 and names them. BigQuery requires `--dataset`.
A model reads `connections/<name>.yaml` first, then a module of that name.

### `tracebi secret`

```bash
tracebi secret list
tracebi secret set NAME [--from-stdin]
tracebi secret unset NAME
tracebi secret edit
```

| Subcommand | Effect |
|---|---|
| `list` | Every `${NAME}` the connection files and `tracebi.yaml` use, where it is set (`set from environment`, `set from .env`, `set in store`, `default`, `MISSING`) and what uses it. |
| `set` | Prompts without echo (or reads stdin with `--from-stdin`) and encrypts the value into `.tracebi/secrets.yml.enc`. Never prints it. |
| `unset` | Removes the store's value only. |
| `edit` | Opens the decrypted `NAME: value` YAML in `$VISUAL` or `$EDITOR`, then encrypts what you saved. A line that is not a name and a non-empty string is refused, and nothing changes. |

The environment and `.env` win over the store. Each change records a
`credential` row in the run store. See [[credentials]].

### `tracebi import dbt`

```bash
tracebi import dbt <path> [--name NAME] [--connection NAME] [--schema SCHEMA] [--force]
tracebi import dbt ./jaffle_shop --connection wh --name jaffle
tracebi import dbt target/manifest.json --connection wh
```

Reads a dbt `manifest.json` (a dbt project root containing
`target/manifest.json`, or the file itself) and drafts `models/<name>.py`. It
does not run dbt or load `.env`.

| Flag | Effect |
|---|---|
| `--name` | The model name. Default: the dbt project's name, else the folder's. |
| `--schema` | Keep only this schema. |
| `--connection` | Wire `models/_connections/<name>.py` from `tracebi connect`; refused when that module is missing. |
| `--force` | Replace an existing model file. |

Tables are dbt models (`resource_type` model, not ephemeral). Relationships
and measures are drafted as `# DRAFT: review` comments; no foreign key is
invented.

## Scaffold files

### `tracebi new-transform` · `tracebi new-model` · `tracebi new-report` · `tracebi new-dashboard` · `tracebi new-pipeline`

```bash
tracebi new-transform "Orders Clean"  [--force] [--python] [--transforms-dir DIR]
tracebi new-model     "Sales Model"   [--force] [--python]
tracebi new-model     "Sales" --from wh --tables fact_sales,dim_customer,dim_product
tracebi new-report    "Portfolio Book"[--force] [--reports-dir DIR]
                      [--layout editorial|brief|tabbed|dashboard]
                      [--mode light|dark|auto] [--density comfortable|compact]
                      [--nav top|side] [--title-at left|center|banner|nav] [--theme NAME]
tracebi new-dashboard "Ops Board"     [--model NAME] [--force] [--reports-dir DIR] [--html]
                      [--job overview|trend|leaderboard|scorecard|monitor|funnel]
                      [--mode …] [--density …] [--nav top|side] [--title-at …] [--theme NAME]
tracebi new-pipeline  "Sales ETL"     [--force] [--python]
```

The title becomes the file name: `"Portfolio Book"` → `portfolio_book`. Each
refuses to overwrite without `--force`.

| Command | Writes |
|---|---|
| `new-transform` | `transforms/<name>.sql` and `<name>.contract.yaml`. `--python`: a notebook-shaped pandas `.py`. |
| `new-model` | `models/<name>.yaml`. `--python`: `models/<name>.py`. |
| `new-report` | `reports/<name>/` with `report.json` and `template.html`: by default an editorial page ([[template-html]]). |
| `new-dashboard` | `reports/<model>/<name>/` with `report.json` and `app.jsx`, a dashboard from the kit ([[app-jsx]]), in the project folder of the model it reads. `--model NAME` names it, and with more than one model it must (or put the title in the model's folder, `"<model>/<Name>"`); otherwise it refuses, naming the models. `--html`: a `template.html` dashboard instead. |
| `new-pipeline` | `pipelines/<name>.yaml`. `--python`: `pipelines/<name>.py`. |

`new-report` and `new-dashboard` write no `script.js` or `style.css`. The
runtime draws every figure from the stamped rows.

**Folders.** `new-report "Finance/Month end/Close pack"` creates
`reports/finance/month_end/close_pack/`. The report is then named by that path
everywhere: `tracebi report build finance/month_end/close_pack`,
`output/finance/month_end/close_pack.html`, and in the app's folders. Two
folders can each hold a report of the same name.

**`--layout`** (template pages):

| Value | Page |
|---|---|
| `editorial` (default) | A kicker, a headline that states the finding, a standfirst, a byline with the build time, prose with bound numbers, captioned figures, a pull-stat, "What to do" and the methodology. Reads with JavaScript off, prints and emails. |
| `brief` | The answer, KPIs, one chart. |
| `tabbed` | Overview and Detail tabs. |
| `dashboard` | The template dashboard. |

**`--job`** (dashboards):

| Value | Starts from |
|---|---|
| `overview` (default) | A KPI strip with a lead, a chart beside its ranking, a filterable detail. |
| `trend` | The latest period and its series. Needs a time dimension. |
| `leaderboard` | The leader, the top ten and the full ranking. |
| `scorecard` | Every measure (up to four) with its trend. |
| `monitor` | The latest period of each measure, its trend and a watch list, lowest first. |
| `funnel` | The fact's count measures as stages, widest first, each conversion a report-level ratio in `report.json` `"measures"`. |

**Look flags.** `--mode`, `--density`, `--nav` (top tabs or a sidebar) and
`--title-at` (`nav` puts the title at the top of the sidebar). For an app they
shape its navigation and title, and mode and density go in `report.json`
`"look"`. For a template they set the `<html>` attributes and the title block
(`--nav` implies the tabbed layout). `--theme ledger|nightdesk|signal` writes
the house theme into `report.json` `"theme"` ([[chart-style]]); a deprecated
accent preset still works and says so.

**`new-model --from <connection> --tables a,b,c`** drafts `models/<name>.yaml`
(`--python`: a `.py`) from the connection's column metadata, with no row scan.
The workspace's own warehouse (`connections/warehouse.yaml`, which `tracebi
init` writes) is written `type: warehouse`, as the reference models are; any
other connection `connection: <name>`. A table named `fact_*`, or one
with numeric non-key columns and `*_id`/`*_key` columns matching another
listed table's key, becomes a fact; the rest become dimensions. Relationships
follow those key names, and each numeric non-key column on a fact becomes a
`sum` measure. Every guess is marked `# DRAFT: review`. `--tables` is required
with `--from`.

### `tracebi theme`

```bash
tracebi theme list                 # the house themes, then the deprecated presets
```

`list` shows the three house themes ([[chart-style]]), Ledger marked the
default and the workspace's `tracebi.yaml` `brand.theme` marked as its choice,
then the six deprecated accent presets, then the workspace's brand. A workspace
picks its house theme with `brand: {theme: …}` ([[tracebi-yaml]]); one report
with `report.json` `"theme"` ([[report-json]]). `tracebi theme use <preset>
[--force]` still copies a deprecated accent preset to `reports/_theme.css`;
named with a house theme, it says where that setting goes instead.

## Build and check

### `tracebi report build`

```bash
tracebi report build <name> [--output PATH] [--format html|pdf] [--badges] [--reports-dir DIR]
```

Builds one self-contained, offline `.html` and its
`<output>.html.manifest.json`. Default output: `output/<name>.html`. A `.json`
spec is compiled to a package first.

| Flag | Effect |
|---|---|
| `--output` | Where to write the HTML. |
| `--format pdf` | Also write a `.pdf`, printed from the built HTML by headless Chromium. Its last pages, "How these numbers were made", print each figure's query in one line and a short fingerprint, the sink contracts, the build time and git SHA, and the `tracebi verify` command; the PDF itself is not verifiable, the HTML and manifest are. Needs `pip install 'tracebi[pdf]'` and `python -m playwright install chromium`. |
| `--badges` | Draw a provenance badge on each figure. The manifest is the same either way. |

With the `pdf` extra installed, every build also writes
`output/<name>.cover.png`: the first screen at 1200×750, recorded as `cover`
in the manifest and never fingerprinted. Without it, the build prints one line
saying why there is no cover.

### `tracebi report status`

```bash
tracebi report status <name> [--json]
```

Prints one line per figure (`✓` verified, `·` derived or unverified, `✗`
otherwise), then unused and failing bindings. Exits 1 on any binding error.
Packages only.

### `tracebi report pins`

```bash
tracebi report pins <name>
tracebi report pins <name> --resolve <id> [--note "what changed"]
```

Lists open reviewer pins (id, kind, note). `--resolve` moves one to the
resolved list in the session's `pins.json`, with a timestamp, the actor and
the note. An unknown id is an error.

### `tracebi verify`

```bash
tracebi verify <manifest.json> [--strict] [--contracts] [--local]
tracebi verify --file <report.html> [--manifest PATH] [--strict]
```

Two separate checks ([[trace]]).

**With a manifest** it re-runs every recorded query and classifies each
section: `REPRODUCES`, `SOURCE DRIFT`, `MODEL CHANGED`, `UNEXPLAINED` or
`UNVERIFIABLE`.

**With `--file`** it re-hashes the rows embedded in the HTML against the
manifest, offline, with no model or database. It catches a number edited in
the file.

| Flag | Effect |
|---|---|
| `--strict` | Fail unless every figure reproduces. Use it as a CI gate. |
| `--contracts` | Also re-run the warehouse's [[sink-contracts]] and compare certified fingerprints to the data now. Reported separately; never changes a figure's status. |
| `--local` | Also replay what the built page recomputes under a selection: every plan not fixed at build, over the slice the file carries (its `payload_sha256` checked first), under the authored selection and one per filter, by the page engine in Node and by the server. They must agree cell by cell; the first difference is named. Without Node, the engine half is skipped and says so. |
| `--manifest` | The manifest for `--file`. Default: `<file>.manifest.json`. |

| Exit | Meaning |
| --- | --- |
| `0` | Everything reproduces or is unverifiable. |
| `2` | Explained drift only. |
| `1` | Anything unexplained or errored, or a manifest with nothing to verify. |

Verify is read-only. It refuses a review snapshot by name.

### `tracebi validate`

```bash
tracebi validate
```

Checks the workspace layout, reports discovery imports that failed, and runs
`DataModel.validate()` on every model, chiefly that dimension keys are unique.
Prints one line per credential a connection uses that is set nowhere. Exits 1
on any problem.

### `tracebi update`

```bash
tracebi update [--check] [--yes]
```

Says whether a newer TraceBi is out, what changed, and the command that
updates this install. A pip install can run it after asking. `--yes` skips the
question; `--check` never runs it. See [[updating]].

## Work live

### `tracebi dev`

```bash
tracebi dev [name] [--port 8001] [--no-browser] [--classic]
```

Opens the web app in dev mode, on `127.0.0.1` only.

- **With a report name** it opens the report in Build mode. The page
  re-renders on each save; a timeline lists which figures each save changed
  (and lets you go back); click a figure to point your agent at it. The panel
  lists **Data** (each binding: its model, rows × columns, the figures that
  read it, a few rows) and **Checks** (figures with no data, bindings no
  figure reads, numbers typed outside figures), and has a note box for your
  agent.
- **With no name** it opens the Data page. What your scripts post with
  `tracebi.workbench.show` appears under *From your agent*, with the notes you
  leave.
- **`--classic`** serves the older preview server: the report at the root and
  the workbench at `/__workbench`. With no name it lays out the warehouse
  tables, sink contracts, models and packages beside the feed. It also runs,
  with a note, when the `web` extra is not installed. `--app` is still
  accepted; it is the default.

### `tracebi report preview`

```bash
tracebi report preview <name> [--port 8080] [--no-browser]
```

Builds, then serves the built file on `127.0.0.1` only (it serves rendered
reports without authentication).

### `tracebi serve`

```bash
tracebi serve [--host 127.0.0.1] [--port 8000] [--reload]
```

Serves the workspace's web app. Refuses, with what to do, when the current
directory has no workspace or `uvicorn` is not installed.

### `tracebi warehouse tables`

```bash
tracebi warehouse tables [--connector NAME] [--table T] [--json]
```

Column names and types of a warehouse table, from connector metadata, with no
row scan. Connectors come from the models in `models/`, plus
`data/warehouse.duckdb` when it exists. Omit `--table` to list tables. A
connector that fails is reported in place (`error`: the exception type and
first line) and the others still list. The MCP tool `describe_table` is the
same lookup.

### `tracebi session`

```bash
tracebi session export [name] [-o PATH] [--format {html,md}] [--title T]
tracebi session clear  [name]
```

Saves or resets the workbench feed `tracebi dev` writes (under
`.tracebi/workbench/<name>/`). Omit `name` for the workspace feed.

| Subcommand | Effect |
|---|---|
| `export` | Writes one record per session, overwriting the same file so git shows the history as a diff. `--format md` is the version for pull requests. It carries no manifest, and `verify` refuses it. |
| `clear` | Resets the feed. Refused while `tracebi dev` is running (a heartbeat under 15 seconds old). |

## Share and deliver

### `tracebi login` · `tracebi logout`

```bash
tracebi login  --server <url> [--timeout 300]
tracebi logout --server <url>
```

`login` signs this machine in to a server through the browser (the company
login, OAuth with PKCE) and keeps the token in
`~/.config/tracebi/credentials.json`. `logout` revokes it on the server and
forgets it. See [[sign-in]].

### `tracebi push`

```bash
tracebi push <paths…> --server <url> [--note "why"]
```

Sends files to a server you signed in to. Report packages and
`models/<name>.yaml` or `.json` become your drafts. `transforms/`,
`pipelines/`, `models/<name>.py`, `connections/` and a package's `report.py`
become one code request an admin approves; it needs `--note`. Data files are
refused. See [[push-from-a-laptop]].

### `tracebi report send`

```bash
tracebi report send <name> --to a@b.com[,c@d.com] [--subject S] [--force]
```

Builds, verifies the new manifest, then emails the HTML and its trace.
Refuses to send a report that does not verify. `--force` sends anyway, with
the failing verdict in the email body. Needs `TRACEBI_SMTP_URL` and
`TRACEBI_SMTP_FROM`; `TRACEBI_SLACK_WEBHOOK` adds a ping after a successful
send.

### `tracebi schedule`

```bash
tracebi schedule list [--json]              # scheduled packages, each with its last run
tracebi schedule run <name> [--no-send]     # refresh, build, verify, email, record: now
tracebi schedule serve                      # run every schedule until Ctrl+C
```

Reads the `schedule` block in each package's `report.json` ([[report-json]]).
A run is `report send` with the package's recipients.

| Behaviour | Detail |
|---|---|
| Refusal | A report that does not verify is recorded `refused` and nothing is sent. |
| Retries | A failed refresh or build is retried twice (after 1, then 5 minutes). `"retries"` (0–5) changes the count. A refused trace or a send failure is not retried. |
| Owner alert | An optional `owner` address gets a plain-text alert when a run ends `failed`, `refused` or `empty`, and that run is not sent to `to`. |
| Slack upload | With `TRACEBI_SLACK_BOT_TOKEN` and `TRACEBI_SLACK_CHANNEL` set, a successful send also uploads the HTML and manifest. A failed upload is recorded and not retried. `--no-send` skips Slack. |
| Record | Every run is a row in `tracebi_runs` (kind `schedule`), with the verdict and who ran it. An existing `output/schedule_runs.jsonl` is imported once. |
| Status | `delivered`, `built` (nothing to deliver, or `--no-send`), `refused`, `empty` (a figure's binding returned no rows) or `failed`. |

`serve` needs `pip install "tracebi[pipeline]"` (APScheduler) and reads the
schedules at startup, so restart it after a change. To use your own scheduler,
call `run` from it:

```bash
0 7 * * MON cd /path/to/project && tracebi schedule run weekly
```

### `tracebi report snapshot`

```bash
tracebi report snapshot <name> [--output PATH]
```

Writes a sendable working copy: exploration blocks kept, a review banner, a
read-only code appendix, and no manifest. `verify --file` refuses it by name.

## Agents

### `tracebi context`

```bash
tracebi context [--model NAME] [--brief] [--compact]
```

TraceBi's vocabulary as JSON, generated from the code. An agent reads it first.

| Flag | Effect |
|---|---|
| `--brief` | The smaller version: semantic model, figure grammar, contracts, conventions. |
| `--model NAME` | Also include that model's schema. |

### `tracebi knowledge`

```bash
tracebi knowledge [slug]
```

Lessons on analysis and design. No argument lists them; a slug prints one.

### `tracebi mcp`

```bash
tracebi mcp [--transport {stdio,http}] [--host 127.0.0.1] [--port 8765] [--insecure]
```

Serves the agent gateway over MCP.

| Flag | Effect |
|---|---|
| `--transport http` | Refuses to start until you set `TRACEBI_MCP_TOKEN` or pass `--insecure`. |
| `--host` | Default `127.0.0.1`. A non-loopback host with `--insecure` and no token also needs `--allow-insecure-bind`: anyone who can reach the port gets full query access. In a container, bind `0.0.0.0` and set the token. |

### `tracebi mcp config`

```bash
tracebi mcp config --client claude-code|cursor|claude-desktop [--http URL]
```

Prints an MCP client snippet as JSON; it does not start a server.
`tracebi init` already writes `.mcp.json` (Claude Code) and
`.cursor/mcp.json` (Cursor), both running `tracebi mcp` over stdio.

| Flag | Effect |
|---|---|
| `--client claude-desktop` | Uses an absolute path to `tracebi` (`shutil.which("tracebi")`, else `sys.executable -m tracebi.cli`). Not offered with `--http`: add the URL as a custom connector in Claude Desktop's settings. That combination exits 1 and prints nothing. |
| `--http URL` | Prints the streamable-HTTP form for Claude Code and Cursor. The placeholder is `Bearer ${TRACEBI_MCP_TOKEN}` for Claude Code and `Bearer ${env:TRACEBI_MCP_TOKEN}` for Cursor. A token value is never printed. |

### `tracebi agent log`

```bash
tracebi agent log [--since 7d] [--json]
```

Summarizes `.tracebi/gateway_log.jsonl`, which the gateway writes only with
`TRACEBI_MCP_LOG=1`: one line per tool call with the tool, ok or error, the
duration, the actor and the names of the arguments. Values, results and tokens
are never written; an error line masks any echoed value as `<value>`. Nothing
leaves the machine.

The summary shows calls and error rate per tool, the ten most common errors,
and the first-build success rate (`build_report` calls that succeeded on a
report's first attempt in a session). `--since` takes a number and `d`, `h`
or `m`.

## Pipelines

### `tracebi run-transform`

```bash
tracebi run-transform <name>
```

Runs `transforms/<name>.sql`, `.py` or `.ipynb` (the suffix is optional) top
to bottom in a fresh state: SQL in one new warehouse connection, Python in a
new namespace. Then runs `<name>.contract.yaml` if there is one. Prints
`form: sql | python | notebook`. Two forms of one name are refused, naming
both. See [[transform-sql]].

### `tracebi run-pipeline`

```bash
tracebi run-pipeline <name> [--layer LAYER] [--refresh] [--status]
```

Runs a pipeline's layers, upstream first.

| Flag | Effect |
|---|---|
| `--layer` | Run only this layer. |
| `--refresh` | With `--layer`, also run its upstream chain. |
| `--status` | Show each layer's last run. Runs and records nothing. |

It does not stop at the first failure: it reports every failure, then a
summary, and exits 1. It records the OS user as the actor, so cron and CI runs
say who ran them. The run is a `pipeline_run` row in the state store (the
app's **History** lists it) with its log in
`data/logs/pipelines/<name>/<id>.log`. If the state store is unreachable the
pipeline still runs and says it is not being recorded.

### `tracebi list-models` · `tracebi list-pipelines`

List the files in `models/` or `pipelines/`. A missing or empty folder prints
a note and exits 0.

## Older forms

### `tracebi spec`

```bash
tracebi spec {schema|validate|render} [file] [--theme CSS] [--output PATH]
```

Works with the JSON `ReportSpec`: print its JSON Schema, validate it without
running, or compile and render it. A package's `report.json` is refused by
name, pointing at `tracebi report build`.

### `tracebi migrate spec`

```bash
tracebi migrate spec reports/<name>.json [--force]
```

Compiles a spec into `reports/<name>/` beside the original, which it never
replaces. The folder takes precedence at discovery, so deleting it rolls back.

### `tracebi migrate model` · `connection` · `pipeline`

```bash
tracebi migrate model      models/<name>.py [--write] [--force]
tracebi migrate connection models/_connections/<name>.py [--write]
tracebi migrate pipeline   pipelines/<name>.py [--write]
```

Converts the Python form to YAML: prints it, or with `--write` writes the
`.yaml`. The Python file is never deleted. For a model or pipeline the `.py`
wins while both exist, so delete it to switch; a connection's YAML is read
first. See [[model-json]], [[connections-yaml]] and [[pipeline-yaml]].
