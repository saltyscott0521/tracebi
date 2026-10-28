# Connection files (YAML)

A file in `connections/` declares a database or folder that holds data: its
type and fields, with every secret kept out of the file as `${ENV_VAR}`.

```yaml
# connections/wh.yaml
name: wh                      # equals the file name
label: Sales warehouse        # optional: the name the app shows
type: postgres
host: db.example.com
port: '5432'
database: sales
user: reader
password: ${TRACEBI_WH_PASSWORD}   # the value lives in the store, .env or the environment
ssl: require
```

The same connection as one URL, which also works:

```yaml
name: wh
type: postgres
url: ${TRACEBI_WH_URL}        # postgresql+psycopg://reader:...@db.example.com:5432/sales?sslmode=require
```

A model uses it by name:

```yaml
# models/sales.yaml
connectors:
  - name: wh
    connection: wh
```

A SQL transform reads one of its tables with a header line
`-- source: wh.<table>` ([[transform-sql]]).

- **Add a connection** on the Sources page (`/data/sources`) writes the file
  for a signed-in admin, with any secret in the encrypted store
  ([[connect-a-database]]).
- `tracebi connect <name> --kind ...` tests a database, writes the file and
  puts any secret in `.env` (or the store, with `--store secret`):
  `--host`, `--port`, `--database`, `--user`, `--password-stdin` or
  `--password-var NAME`, `--ssl` write the fields; `--url` writes a URL.
  `tracebi connect <name> --test` tests an existing connection.
- `.yml` works too. `TRACEBI_CONNECTIONS_DIR` moves the folder.
- The workspace's own warehouse is not a connection file. It is the
  `warehouse:` block of `tracebi.yaml` ([[tracebi-yaml]]), and a model reads it
  with `type: warehouse`. That block resolves `${VAR}` the same way, and its
  remote tier may name a duckdb connection file here.
- The file loads with `yaml.safe_load` rules. A repeated key is an error, and
  an unknown key is refused with a suggestion.

## Fields

Every file has `name` and `type`. All values are strings.

| `type` | Required | Optional |
|---|---|---|
| `duckdb` | `database` | `directory` |
| `csv` | `directory` | `encoding` |
| `sql` | `url` | |
| `postgres`, `mysql` | `url`, or `host` and `database` | with the fields: `port`, `user`, `password`, `ssl`, `options`, `connect_timeout` |
| `snowflake` | `account`, `user`, `warehouse`, `database`, and `password` with the password sign-in | `schema` (default `PUBLIC`), `role`, `authenticator`, `private_key_path` |
| `bigquery` | `project`, `dataset` | `credentials` (path to a service-account file), or `credentials_json` |
| `upload` | `file` (a `.csv` or `.parquet` file under `inputs/`) | |

`sql` takes any SQLAlchemy URL (`sqlite:///inputs/bank.sqlite` for a file in
the workspace). `postgres` and `mysql` are `sql` with the database said in the
type (`postgresql+psycopg://…`, `mysql+pymysql://…`).

### URL or fields

A `postgres` or `mysql` file says its connection one of two ways: one `url`,
or its fields, from which the connection builds the URL. Never both: a file
with `url` and `host` is refused. The app's form shows both as **Fields** and
**URL** tabs of one connection, and writes the fields. A URL sent to it with a
password in it is written as the fields, so the password gets its own
`${NAME}`; a URL naming another driver (`postgresql+psycopg2://`) stays a URL.

| Field | `postgres` | `mysql` |
|---|---|---|
| `host` | The server's name or address. Required. | Same. |
| `port` | A whole number. `5432` when unset. | `3306` when unset. |
| `database` | Required. | Required. |
| `user` | The user it signs in as. | Same. |
| `password` | Always `${NAME}`. The app and `tracebi connect --host` name it `TRACEBI_<CONNECTION>_PASSWORD`. | Same. |
| `ssl` | `disable`, `prefer`, `require` or `verify-full` (libpq's `sslmode`). | `on` or `off`. |
| `options` | More query parameters, `application_name=tracebi&...`. No credential, and not `sslmode` or `connect_timeout`. | Same (`charset=utf8mb4`). |
| `connect_timeout` | Seconds to wait for the server. | Same. |

The URL is built with the type's driver, `postgresql+psycopg` (installed by
the `postgres` extra) or `mysql+pymysql`, the user, password and database
percent-encoded. In code, `tracebi.connections.build_url(type, fields)` and
`parse_url(type, url)` are that mapping both ways. A password that is
`${NAME}` stays `${NAME}` in a built URL, so the URL the app shows and copies
names the variable, never the value.

### Snowflake sign-in

`authenticator` is `password` (the default), `externalbrowser` (the identity
provider's page opens on the server) or `key_pair` (reads `private_key_path`,
a `.p8` file on the server, relative to the workspace root). Only the password
sign-in takes `password`.

### BigQuery credentials

`credentials` is a path to a service account's JSON key file on the server.
`credentials_json` is the key itself, pasted into the app's form: it goes to
the encrypted store and the file names it as `${NAME}`. Give one or the other. An `upload` connection is
one file read as one table, named after the file: `file: inputs/orders.csv` is
the table `orders`. The app's upload puts the file there (`POST /api/inputs`, at
most 50 MB).

| Field | Meaning |
|---|---|
| `label` | Optional name for people. The Sources page shows it large, with `name` small beside it and the kind of source in words ("Postgres", "SQLite file"). In Python: `connector.label = "..."`. Never a credential and never resolved. |

## `agents`

Which of the connection's tables an agent may read through the gateway.
Absent, none.

```yaml
agents:
  tables: [accounts, clients]   # or "*" for every table, now and later
```

`tracebi connect <name> --agents accounts,clients` (or `all`) writes it, and
so does ticking **Agents may read** on the connection's Tables list.
`tracebi connect --list` prints each connection with its list. TraceBi's own
tables (`tracebi_*`, `alembic_version`) are never readable, whatever it says.
In code, `tracebi.connections.agent_may_read(connection, table)` is the one
check; a loaded connector carries the list as `agent_tables` (`["*"]` for
all, `None` for none).

## `${ENV_VAR}`

Any value may be a reference, written as the whole value and named
`[A-Z_][A-Z0-9_]*`. `"x-${A}"` is an error.

`${NAME:-default}` adds a default, used only when the name resolves nowhere:

```yaml
url: ${TRACEBI_BANK_URL:-sqlite:///inputs/bank.sqlite}
```

| Rule | Detail |
|---|---|
| Secrets must be references | `password` and `credentials_json` always. `url` may be literal only when it carries no credential (no password, no `password=`, `token=`, `key=` and the like in the query). `sqlite:///data/x.db` is fine. |
| Defaults are checked like literals | A SQLite path passes, a URL with a password is refused, and `password` takes no default. The Sources page shows such a name as `Set · default`. |
| Literal paths stay in the workspace | `database` and `directory` of a `duckdb` or `csv` connection, an `upload`'s `file`, and the file of a `sqlite:///` url: no absolute path, no `..`. Use a reference to point elsewhere. Relative paths resolve against the workspace root. |
| Resolved when used | Reading the file reads no environment. The variable is read when the connection is used; an unset one fails there, naming the variable. |
| Lookup order | The process environment, the workspace's `.env`, the workspace's encrypted store (`tracebi secret set NAME`, or **Set…** on the Sources page; [[credentials]]), then the default. Nothing is copied into `os.environ`. `tracebi secret list` shows which names are missing. |
| Never shown | `/api/connectors` and the Sources page show a reference as `${NAME}` and a literal URL with its password hidden. A credential is never resolved to describe a connection. |

## Discovery and precedence

- Files in `connections/` are registered at startup and when they change, and
  forgotten when deleted, so the Sources page (`/data/sources`) lists them.
- The app edits a file in place: the keys it changes are rewritten where they
  stand, and comments and order stay. It deletes a file only when no
  transform, pipeline step or model reads the connection, and otherwise says
  which do.
- A model's `connection: <x>` reads `connections/<x>.yaml` first, then the
  older `models/_connections/<x>.py` that `tracebi connect --python` writes.
- `tracebi migrate connection models/_connections/<x>.py [--write]` converts a
  module to YAML. It never deletes the module, and refuses a module that is not
  one of the types above or that builds a credential in code.
