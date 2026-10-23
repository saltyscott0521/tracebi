# Credentials

**The secrets a project's connections need: which names, where each is set,
and a store on the server you can set them in without touching `.env`.**

A connection keeps its secret out of the file as `${NAME}`
([[connections-yaml|connection files]]; `key_id` and `secret` in
[`tracebi.yaml`](tracebi-yaml.md)). Each `${NAME}` is looked up, in order:

1. the **process environment**,
2. the project's **`.env`**,
3. the project's **credential store**, `.tracebi/secrets.json`.

The environment comes first, so a deployment's own configuration (a vault or
secrets manager that injects variables) always wins over anything saved
through the app, and a project with no store behaves exactly as it did.
Nothing is ever copied into `os.environ`.

A value may also carry a **default**, `${NAME:-default}`, used only when the
name resolves nowhere. The default is written in the file, so it is checked
like any literal of its field: a SQLite path or a URL without a password is
fine, a URL with a password is refused, and a `password` has no default at
all. A secret cannot hide behind one.

---

## Which names a project needs

`tracebi secret list` (and Data → Sources, a connection's **Connection**
section) lists every `${NAME}` the project's files reference, what uses it,
and where it is set:

```
TRACEBI_CRM_URL · set in store · used by crm.url
TRACEBI_BANK_URL · default · used by bank.url
TRACEBI_SNOW_PASSWORD · MISSING · used by snow.password
```

A name is only ever "missing" against something that references it.
`tracebi validate` prints one line for each missing name.

## The store

`.tracebi/secrets.json` in the project root, mode `0600`, created on the
first write. Each value is encrypted with
[Fernet](https://cryptography.io/en/latest/fernet/) (`pip install
'tracebi[web]'` brings `cryptography`), with who set it and when beside it;
never in clear.

The key is `TRACEBI_SECRET_KEY` (a Fernet key) when set, else
`.tracebi/secret.key`, generated `0600` on the first write. One server can
keep its own key file. **Several workers or replicas must share
`TRACEBI_SECRET_KEY`**, as they share `TRACEBI_STATE_URL`. A store read under
a different key fails naming the file, never as "not set". Make a key with:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Both files are gitignored (`tracebi init` writes the lines). `tracebi push`
never packages `.tracebi/`, and nothing reads it into a report or a session
export.

## On the server: `tracebi secret`

```bash
tracebi secret set TRACEBI_CRM_URL            # prompts, no echo
printf %s "$URL" | tracebi secret set TRACEBI_CRM_URL --from-stdin
tracebi secret list
tracebi secret unset TRACEBI_CRM_URL          # the store's value only
tracebi connect crm --kind postgres --url ... --store secret   # the store instead of .env
```

## In the app

On Data → Sources, a connection's **Connection** section shows each name it
uses with where it is set (`Set · environment`, `Set · .env`, `Set here`,
`Set · default`, `Missing`). A signed-in admin sees **Set…** / **Replace…**
and, for a value the store holds, **Remove**; after saving, **Test
connection** opens the connection, counts its tables and closes it. Viewers
and analysts see the states, never the buttons. No page ever shows a value,
including one just typed.

**Writes need an identified admin**: a sign-in role of `admin` (OIDC sign-in,
a proxy role header, or Basic auth with `TRACEBI_AUTH_ROLE_MAP`). With no
sign-in at all every caller is admin by default, so a write there is refused
(403, `credentials are set on the server: tracebi secret set NAME`); otherwise
anyone who can reach an open server could point its connections at a host of
their choosing.

## API

| Route | Role | Answer |
|---|---|---|
| `GET /api/credentials` | viewer | `{credentials: [row], key_source: env\|file, can_change}` |
| `PUT /api/credentials/{name}` `{value}` | identified admin | the row; 201 new, 200 replaced, 422 for a name nothing references |
| `DELETE /api/credentials/{name}` | identified admin | 204; 404 when the store holds none |
| `POST /api/connectors/{name}/test` | admin | `{ok: true, tables: n}` or `{ok: false, reason}` |

A row is `{name, used_by: [{kind: connection|warehouse, name, field,
default}], set, source: environment|dotenv|store|default|null, stored,
updated_at?, updated_by?, problem?}`; never a value. A test's reason has
every resolved credential value replaced by `***`.

Each set or unset, from the app or the CLI, records one row in the run store
(`kind: credential`, `target: NAME`, `status: set|unset`, the actor), shown in
History. Never the value.

## What this is not

- Not a vault integration: a vault injects environment variables, which win.
- Not per-person: one project, one set of connection secrets.
- Not for the app's own settings (`TRACEBI_OAUTH_SECRET`,
  `TRACEBI_STATE_URL`, `TRACEBI_SECRET_KEY` itself): those configure the
  process and stay in its environment.
