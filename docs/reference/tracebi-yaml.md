# Project settings (`tracebi.yaml`)

**The limits of the engine that answers model queries, in one file at the
project root.**

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
engine:
  memory_limit: 1GB                  # past it, a query spills to temp_directory
  threads: 4                         # default: min(4, CPUs)
  temp_directory: data/.duckdb-tmp   # relative to the project root
  query_timeout_s: 30                # Explore, Ask and agent queries stop here
```

---

## `engine`

Every model query (a report build, Explore and Ask in the app, the agent
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
| `query_timeout_s` | `30` | Seconds a reader's query may run: `POST /api/models/{name}/query` (Explore, Ask), `POST /api/reports/{name}/selection` and the gateway's `query_model`. Past it the query is interrupted and the caller gets an error naming the limit (HTTP 504 with the usual `{message, exception_type, traceback}` detail; the gateway's `{ok: false, errors}`). Builds and `verify` run without a timeout. |

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
