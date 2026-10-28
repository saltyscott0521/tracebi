# Workspace settings (`tracebi.yaml`)

`tracebi.yaml` at the workspace root says where the warehouse lives and sets the
limits of the engine that answers model queries.

```yaml
# tracebi.yaml
warehouse:
  tier: file                         # file (default) | object | remote
  location: data/warehouse.duckdb
engine:
  memory_limit: 1GB                  # past it, a query spills to temp_directory
  threads: 4                         # default: min(4, CPUs)
  temp_directory: data/.duckdb-tmp   # relative to the workspace root
  query_timeout_s: 30                # Ask and agent queries stop here
```

- `tracebi init` writes a commented one.
- Every key is optional. A missing file, block or key means the default.
- An unknown key or a value of the wrong shape is an error naming the file
  and the key. A limit an operator wrote is the limit that applies.
- The file is read from the working directory (the workspace root) and re-read
  when it changes.

## `warehouse`

Where transforms write their tables and where models read them. The tables
are the same on every tier; only their address changes.

| `tier` | `location` | A transform's `write(df, table)` | The model reads |
|---|---|---|---|
| `file` (default) | A `.duckdb` path. Default `data/warehouse.duckdb`. | A table in the file | The file, attached read-only |
| `object` | `s3://bucket/prefix`, `gs://bucket/prefix` (R2 and MinIO: `s3://` plus an `endpoint`), or a local directory | `COPY … TO '<location>/<table>.parquet' (FORMAT PARQUET)` | One view per file over `read_parquet`, in place |
| `remote` | A DuckDB database to `ATTACH`: `md:my_db` (MotherDuck), a path, or the name of a `connections/<name>.yaml` of type duckdb | A table in that database | The database, attached read-only |

Models and transforms follow the tier without naming a path:

- **A model** uses `connectors: - {name: warehouse, type: warehouse}`.
  `type: duckdb` with `database:` still names one file (the file tier).
- **A transform** writes to `sink_target()`:

  ```python
  from tracebi.project_config import sink_target
  WAREHOUSE = sink_target(ROOT)           # the path, the prefix, or the attach string
  DuckDBConnector("warehouse", database=WAREHOUSE).write(df, "fact_orders")
  with contract("orders", warehouse=WAREHOUSE) as c:
      ...
  ```

  `sink_target()` returns a string that remembers its warehouse, so the
  connector and the contract follow the tier. `write()` creates `data/` (or
  the local directory) on a fresh clone. A medallion layer that sinks into the
  workspace's warehouse writes through the same `write()`.

### Object-tier keys

| Key | Meaning |
|---|---|
| `endpoint` | An S3-compatible endpoint (MinIO, R2): `http://host:port` or `https://…`. `http://` turns TLS off. Omitted: AWS, or Google Cloud Storage for `gs://`. |
| `region` | The bucket's region. |
| `key_id` | The access key id. Must be `${VAR}`. |
| `secret` | The secret access key. Must be `${VAR}`. |
| `url_style` | `path` (MinIO, most endpoints) or `vhost` (AWS's default). |

- `${VAR}` is the whole value, as in `connections/*.yaml`. It is looked up in
  the environment, then the workspace's `.env`, when a connection is made. It is
  never copied into `os.environ`.
- An unset variable is an error naming it, the key and the file. A literal
  `key_id` or `secret` is refused.
- `tier` and `location` are written out, because a model reads them when it
  loads. A remote location carrying a credential (`md:db?motherduck_token=…`)
  is refused; put it in a `connections/<name>.yaml` (or MotherDuck's own
  `motherduck_token` variable) and name that.
- The object tier reads storage through DuckDB's `httpfs` extension. A query
  connection only loads it; the first transform installs it if missing (an
  air-gapped server needs it in `~/.duckdb/extensions` first). The
  credentials become a `CREATE TEMPORARY SECRET`, scoped to the prefix, on
  that one connection before its settings are frozen.

### What a query connection may read on each tier

On the object tier a query connection may read exactly the Parquet files its
views use (`allowed_paths`), found when it opens. Any other file or URL is
refused. Because DuckDB would let a statement write an allowed path, such a
connection also refuses `COPY`, `EXPORT`, `ATTACH` and `DETACH` by statement
type. The transform's write connection has none of these restrictions, but
the `engine` limits below apply to it too.

### Where the certificate lives

| Tier | Sink contract certificate |
|---|---|
| `file` | Beside the warehouse file |
| `object` | `<location>/_contracts.json` |
| `remote` | `data/remote_warehouse.contracts.json` |

Every record carries `engine_version`, the DuckDB that read the tables back.
On the object tier it also carries `objects`: per table, the file's `path`,
`etag` (from a signed HEAD request; `null` where the store gives none, as on a
local directory), `size`, `last_modified` and `version_by` (`etag` or
`size+last_modified`). A file rewritten since the certificate reads **stale**
on that alone, before any fingerprint is compared: in report manifests, the
Warehouse folder and `tracebi verify --contracts` (`REWRITTEN`).

## `engine`

Every model query (a build, Ask, the gateway's `query_model`, a selection
recompute, `tracebi verify`) and every SQL calculation runs in its own DuckDB
connection. It attaches the warehouse read-only and holds the model's tables
as views. A table from a source with no engine (a `MemoryConnector`, CSV files,
a SQL database) is loaded through its connector and registered as Arrow.

| Key | Default | Meaning |
|---|---|---|
| `memory_limit` | `1GB` | Memory limit for one query connection, as a size (`512MB`, `2GiB`). Past it a query spills to `temp_directory`. |
| `threads` | `min(4, CPUs)` | Worker threads per query connection, at least 1. |
| `temp_directory` | `data/.duckdb-tmp` | Where a query spills, relative to the workspace root. Created only when needed. |
| `query_timeout_s` | `30` | Seconds a reader's query may run: `POST /api/models/{name}/query` (Ask), `POST /api/reports/{name}/selection` and the gateway's `query_model`. Past it the query stops with an error naming the limit (HTTP 504 with `{message, exception_type, traceback}`; the gateway's `{ok: false, errors}`). Builds and `verify` have no timeout. |

### What a query connection cannot do

Before any query runs, the connection sets `enable_external_access = false`,
then `lock_configuration = true`. DuckDB then refuses:

- reading a file or a URL (`read_csv('http://…')`, `read_parquet`, `glob`,
  `SELECT * FROM 'file.csv'`), in a model's `SELECT` source, a SQL
  calculation or anywhere else;
- `ATTACH`, `COPY`, `INSTALL` and `LOAD`;
- any `SET` or `RESET`, so none of this can be switched back on from SQL.

A source that must read a file or the network belongs in a transform. The
transform connection (`tracebi run-transform`, `DuckDBConnector.write`, the
sink contracts) has no such limits, and runs only from the CLI, the scheduler
or an approved code request. A DuckDB connector's file source (`source:
orders.parquet` with a `directory`) is still read through the connector.

### Numbers and fingerprints

A view keeps the values the connector's frame held (a NaN is a null, a
DECIMAL a double, a DATE a timestamp), so every result, dtype and fingerprint
is the same as through the connector. Each `load` node records the table's
fingerprint as `load()` returns it. That fingerprint is computed once per
warehouse version (the file's size and modification time) and reused by every
figure of a build.

## `brand`

The workspace's brand: the look every report and dashboard of the workspace
takes, its charts included. One block, and every page follows.

```yaml
brand:
  theme: ledger                  # the house theme: ledger (default) | nightdesk | signal
  name: Cedar Capital            # the firm mark, beside the logo; the kicker stays the model's label
  logo: brand/logo.svg           # svg or png under the workspace, inlined
  accent: "#0f6b5c"              # --tb-accent, and what each ground needs from it
  palette: ["#0f6b5c", "#c8902e", "#5b6ee1", "#d1495b", "#3c9d9b", "#8a5a44"]
  font: brand/Inter.woff2        # optional; inlined @font-face, the pages' and charts' face
  mode: auto                     # optional: light | dark | auto, for a page that names none
```

| Key | What it sets |
|---|---|
| `theme` | The workspace's house theme ([[chart-style]]): `ledger` (the default), `nightdesk` or `signal`. A report's own `report.json` `"theme"` wins over it. The rest of the brand layers on top: its accent, palette, font and logo replace the theme's colours and face, and the theme keeps its surfaces, depth, density, radius and numerals. |
| `name` | The firm's name, in small type beside the logo in the masthead's mark slot (`.tb-masthead-mark`); with no logo, the name alone is the mark. It never replaces the kicker: the kicker (the small line over the title) stays the model's label, so a page still says what it is about. At most 60 characters. |
| `logo` | The masthead's mark (`.tb-masthead-mark`), with the name beside it: above the kicker on a template page and in an app's `<Masthead>`, its sidebar included. A mark the author drew (a filled `.tb-masthead-mark`, `<Masthead mark>`) wins; `mark={null}` shows none. An `.svg` or `.png` under the workspace, inlined as a `data:` URI. On a filled ground (the editorial hero, a banner title) it is drawn in the ground's ink. |
| `accent` | `--tb-accent`. From it: `--tb-accent-text` (the same hue deepened to 4.5:1 for links and small text), `--tb-on-accent`, `--tb-surface-accent`, and the dark ground's `--tb-dark-accent` / `--tb-dark-accent-text` (lifted to read on the dark card). |
| `palette` | `--tb-chart-1..8`, in the order a chart's series take them: 1 to 8 colours, cycled to eight. On the dark ground each is lifted only as far as it takes to read there. With no palette, `--tb-chart-1` is the accent. |
| `font` | A `.woff2`, `.woff`, `.ttf` or `.otf` under the workspace, inlined as an `@font-face` that `--tb-font` (and so `--tb-chart-font`) names first, Geist after it. |
| `mode` | The ground a page takes when it names none (a template's `<html data-tb-mode>`, an app's `report.json` `"look"`). Default: the house theme's, `auto` (the reader's system) except Nightdesk, which opens `dark`. |

- Colours are hex, `#rgb` or `#rrggbb`, and quoted: YAML reads an unquoted
  `#` as the start of a comment.
- The build fails, naming the key and the fix, on a missing file, a colour
  that is not hex, an accent below 3:1 on the white card (it names a deeper
  shade of the same hue that passes), or a logo or font over 400 KB. A page
  carries both inlined, and a page stays under its 16 MB budget.
- Where it sits: right after the shipped `tracebi.css` and the house theme,
  before `reports/_theme.css`. So the workspace's own theme and a report's
  `style.css` still win, in that order; on the dark ground its colours are
  lifted against the house theme's own card. `tracebi theme list` shows it.
- A brand changes how a page looks, never a number. Agents never hard-code a
  colour in a chart's `option`: a series takes the palette.

The reference workspace carries no brand: its four demos are unrelated
businesses, so each report keeps the house default (Ledger) and the SaaS
reports name Nightdesk in their `report.json`. The house themes, and the chart look the palette and
tokens feed, are in [[chart-style|House themes and chart style]].
