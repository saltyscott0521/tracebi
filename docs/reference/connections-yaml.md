# Connection files (YAML)

A file in `connections/` declares a database or folder that holds data: its
type and fields, with every secret kept out of the file as `${ENV_VAR}`.

```yaml
# connections/wh.yaml
name: wh                      # equals the file name
label: Sales warehouse        # optional: the name the app shows
type: postgres
url: ${TRACEBI_WH_URL}        # the value lives in .env or the environment
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

- `tracebi connect <name> --kind ...` tests a database, writes the file and
  puts any secret in `.env`.
- `.yml` works too. `TRACEBI_CONNECTIONS_DIR` moves the folder.
- The project's own warehouse is not a connection file. It is the
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
| `sql`, `postgres` | `url` | |
| `snowflake` | `account`, `user`, `password`, `warehouse`, `database` | `schema` (default `PUBLIC`), `role` |
| `bigquery` | `project`, `dataset` | `credentials` (path to a service-account file) |

| Field | Meaning |
|---|---|
| `label` | Optional name for people. The Sources page shows it large, with `name` small beside it and the kind of source in words ("Postgres", "SQLite file"). In Python: `connector.label = "..."`. Never a credential and never resolved. |

## `${ENV_VAR}`

Any value may be a reference, written as the whole value and named
`[A-Z_][A-Z0-9_]*`. `"x-${A}"` is an error.

`${NAME:-default}` adds a default, used only when the name resolves nowhere:

```yaml
url: ${TRACEBI_BANK_URL:-sqlite:///inputs/bank.sqlite}
```

| Rule | Detail |
|---|---|
| Secrets must be references | `password` always. `url` may be literal only when it carries no credential (no password, no `password=`, `token=`, `key=` and the like in the query). `sqlite:///data/x.db` is fine. |
| Defaults are checked like literals | A SQLite path passes, a URL with a password is refused, and `password` takes no default. The Sources page shows such a name as `Set · default`. |
| Literal paths stay in the project | `database` and `directory` of a `duckdb` or `csv` connection, and the file of a `sqlite:///` url: no absolute path, no `..`. Use a reference to point elsewhere. Relative paths resolve against the project root. |
| Resolved when used | Reading the file reads no environment. The variable is read when the connection is used; an unset one fails there, naming the variable. |
| Lookup order | The process environment, the project's `.env`, the project's encrypted store (`tracebi secret set NAME`, or **Set…** on the Sources page; [[credentials]]), then the default. Nothing is copied into `os.environ`. `tracebi secret list` shows which names are missing. |
| Never shown | `/api/connectors` and the Sources page show a reference as `${NAME}` and a literal URL with its password hidden. A credential is never resolved to describe a connection. |

## Discovery and precedence

- Files in `connections/` are registered at startup and when they change, so
  the Sources page (`/data/sources`) lists them.
- A model's `connection: <x>` reads `connections/<x>.yaml` first, then the
  older `models/_connections/<x>.py` that `tracebi connect --python` writes.
- `tracebi migrate connection models/_connections/<x>.py [--write]` converts a
  module to YAML. It never deletes the module, and refuses a module that is not
  one of the types above or that builds a credential in code.
