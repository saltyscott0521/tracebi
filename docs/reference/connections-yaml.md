# Connection files (YAML)

**A source as data: a type and its fields, with every secret kept out of the
file as a `${ENV_VAR}` reference.**

`connections/<name>.yaml` (`.yml` works too; `TRACEBI_CONNECTIONS_DIR` moves
the folder) declares a place data lives. `tracebi connect <name> --kind ...`
tests a warehouse, writes the file, and puts any secret in `.env`. A model
points at it with `connection: <name>` in its `connectors:`.

The file loads with `yaml.safe_load` semantics, a repeated key is an error,
and the schema is closed: an unknown key is refused with a suggestion.

---

## Example

```yaml
# connections/wh.yaml
name: wh                      # equals the file name
type: postgres
url: ${TRACEBI_WH_URL}        # the value lives in .env or the environment
```

```yaml
# models/sales.yaml
connectors:
  - name: wh                  # equals the connection's name
    connection: wh
```

---

## Fields

Every file has `name` and `type`. `type` is one of:

| type | required | optional |
|---|---|---|
| `duckdb` | `database` | `directory` |
| `csv` | `directory` | `encoding` |
| `sql`, `postgres` | `url` | |
| `snowflake` | `account`, `user`, `password`, `warehouse`, `database` | `schema` (default `PUBLIC`), `role` |
| `bigquery` | `project`, `dataset` | `credentials` (path to a service-account file) |

All values are strings.

## `${ENV_VAR}`

Any value may be a reference, written as the whole value and named
`[A-Z_][A-Z0-9_]*`. `"x-${A}"` is an error.

- **Secrets must be references.** `password` always. `url` may be a literal
  only when it carries no credential (no password, no `password=`, `token=`,
  `key=`... in the query); `sqlite:///data/x.db` is fine, a URL with a
  password is a validation error.
- **Paths stay inside the project when literal.** `database` and `directory`
  of a `duckdb`/`csv` connection: no absolute path, no `..`. Use a reference
  to point elsewhere. Relative paths resolve against the project root.
- **Resolved lazily.** Reading the file builds a connector and reads no
  environment. The variable is read when the connection is used; an unset one
  fails there with an error naming the variable (and not its value).
  Lookup is the process environment, then the project's `.env`. `.env` is
  never copied into `os.environ`, and only the names a connection references
  are read.
- **Never shown.** `/api/connectors` and the Sources page show a referenced
  value as `${NAME}` and a literal URL with its password redacted; a
  credential is never resolved to describe a connection.

## Discovery and precedence

Files in `connections/` are registered at startup and as they change, so the
Sources page lists them. A model's `connection: <x>` reads
`connections/<x>.yaml` first, then the legacy `models/_connections/<x>.py`
that `tracebi connect --python` writes. `tracebi migrate connection
models/_connections/<x>.py [--write]` converts one (it never deletes the
module) and refuses, with a reason, a module that is not one of the types
above or that builds a credential in code.
