# Project settings (`tracebi.yaml`)

**Where the warehouse lives, and the limits of the engine that answers model
queries, in one file at the project root.**

`tracebi.yaml` sits beside `models/` and `reports/`. `tracebi init` writes a
commented one. Every key is optional: a missing file, block or key means the
default. A key the file does not know, or a value of the wrong shape, is an
error naming the file and the key, never a silent default, because a limit an
operator wrote must be the limit that applies. The file is read from the
working directory (the project root) and re-read when it changes.

---

## Example

```yaml
# tracebi.yaml
warehouse:
  tier: file                         # file (default) | object | remote
  location: data/warehouse.duckdb
engine:
  memory_limit: 1GB                  # past it, a query spills to temp_directory
  threads: 4                         # default: min(4, CPUs)
  temp_directory: data/.duckdb-tmp   # relative to the project root
  query_timeout_s: 30                # Ask and agent queries stop here
```

---

## `warehouse`

The freeze point between phase ① and phase ②: where a transform sinks its
tables and where a model reads them. Three tiers, one setting; the tables are
the same on each, only their address moves.

| tier | location | a transform's `write(df, table)` | the model reads |
|---|---|---|---|
| `file` (default) | a `.duckdb` path, default `data/warehouse.duckdb` | a table in the file | the file, attached read-only |
| `object` | `s3://bucket/prefix`, `gs://bucket/prefix` (R2 and MinIO: `s3://` plus an `endpoint`), or a local directory | `COPY … TO '<location>/<table>.parquet' (FORMAT PARQUET)` | one view per file over `read_parquet`, in place |
| `remote` | a DuckDB database to `ATTACH`: `md:my_db` (MotherDuck), a path, or the name of a `connections/<name>.yaml` of type duckdb | a table in that database | the database, attached read-only |

Two files follow it without naming a path:

- **A model** says `connectors: - {name: warehouse, type: warehouse}`. That is
  the project's warehouse on whichever tier. `type: duckdb` with a
  `database:` path still names one file explicitly (the file tier).
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
  the local directory) on a fresh clone. A medallion layer whose sink is the
  project's warehouse writes through the same `write()`.

### Object-tier keys

| key | meaning |
|---|---|
| `endpoint` | An S3-compatible endpoint (MinIO, R2): `http://host:port` or `https://…`. `http://` turns TLS off. Omitted: AWS (or Google Cloud Storage for `gs://`). |
| `region` | The bucket's region. |
| `key_id` | The access key id. **Must be `${VAR}`.** |
| `secret` | The secret access key. **Must be `${VAR}`.** |
| `url_style` | `path` (MinIO, most endpoints) or `vhost` (AWS's default). |

`${VAR}` is the whole value, as in `connections/*.yaml`: looked up in the
environment, then the project's `.env`, when a connection is made (never when
the file is read, never copied into `os.environ`). An unset variable is an
error naming it, the key and the file. A literal `key_id` or `secret` is
refused, naming the key. `tier` and `location` are written out, because a
model reads them when it loads; a remote location that carries a credential
(`md:db?motherduck_token=…`) is refused, so keep it in a
`connections/<name>.yaml` (or MotherDuck's own `motherduck_token` variable)
and name that.

The object tier reads remote storage through DuckDB's `httpfs` extension. A
query connection only loads it; the first transform installs it if it is
missing (an air-gapped server needs it in `~/.duckdb/extensions`
beforehand). The credentials become a `CREATE TEMPORARY SECRET` scoped to the
prefix, on that one connection, before it is locked.

### What the query connection may read on each tier

The lock below applies on every tier. On the object tier the connection is
allowed exactly the Parquet files its views read (`allowed_paths`), found
when it opens; any other file or URL is refused as before. Because DuckDB
would let a statement write an allowed path, a query connection that allows
files also refuses `COPY`, `EXPORT`, `ATTACH` and `DETACH` by statement type,
from DuckDB's own parser. The transform's write connection is not locked; the
`engine` limits below apply to it as well (limits are not a lock).

### The certificate on each tier

A sink contract's certificate lives beside the warehouse: beside the file on
the file tier, `<location>/_contracts.json` inside the prefix on the object
tier, and `data/remote_warehouse.contracts.json` on the remote tier. Every
record carries `engine_version` (the DuckDB that read the tables back). On the
object tier it also carries `objects`: per table, the file's `path`, `etag`
(from a HEAD request signed with the resolved credentials; `null` where the
store gives none, as on a local directory), `size`, `last_modified` and
`version_by` (`etag` or `size+last_modified`, which of them decides). A file
rewritten since the certificate reads **stale** on that version alone, before
any fingerprint is compared, in report manifests, the Warehouse tab and
`tracebi verify --contracts` (`REWRITTEN`).

---

## `engine`

Every model query (a report build, Ask in the app, the agent
gateway's `query_model`, a selection recompute, `tracebi verify`) and every
SQL calculation runs in its own DuckDB connection. It attaches the warehouse
file read-only and holds the model's tables as views over it; a table from a
source with no engine (a `MemoryConnector`, CSV files, a SQL database) is
loaded through its connector and registered as Arrow. Then, before any query
runs, the connection is locked.

| key | default | meaning |
|---|---|---|
| `memory_limit` | `1GB` | DuckDB's memory limit for one query connection, as a size (`512MB`, `2GiB`). Past it a query spills to `temp_directory` instead of taking the process down. |
| `threads` | `min(4, CPUs)` | Worker threads per query connection, a whole number of at least 1. |
| `temp_directory` | `data/.duckdb-tmp` | Where a query spills. Relative paths are from the project root. DuckDB creates it only when it spills. |
| `query_timeout_s` | `30` | Seconds a reader's query may run: `POST /api/models/{name}/query` (Ask), `POST /api/reports/{name}/selection` and the gateway's `query_model`. Past it the query is interrupted and the caller gets an error naming the limit (HTTP 504 with the usual `{message, exception_type, traceback}` detail; the gateway's `{ok: false, errors}`). Builds and `verify` run without a timeout. |

### What a query connection cannot do

The connection sets `enable_external_access = false` and then
`lock_configuration = true`. DuckDB itself then refuses, by name:

- reading a file or a URL (`read_csv('http://…')`, `read_parquet`, `glob`,
  `SELECT * FROM 'file.csv'`), in a model's `SELECT` source, a SQL
  calculation or anything else;
- `ATTACH`, `COPY`, `INSTALL` and `LOAD`;
- any `SET` or `RESET`, so none of this can be switched back on from SQL.

A source that has to read a file or the network belongs in a transform: the
transform connection (`tracebi run-transform`, `DuckDBConnector.write`, the
sink contracts) is not locked, and runs only from the CLI, the scheduler or an
approved code request. A DuckDB connector's file source (`source:
orders.parquet` with a `directory`) is still read, through the connector, as
before.

### What stays as it was

The numbers and the trace. A view keeps the values the connector's frame held
(a NaN is a null, a DECIMAL a double, a DATE a timestamp), so every result,
dtype and fingerprint is the one the previous engine path produced, and each
`load` node still records the fingerprint of the table as `load()` returns it.
That fingerprint is computed through the connector once per warehouse version
(the file's size and modification time) and reused by every figure of a build.
