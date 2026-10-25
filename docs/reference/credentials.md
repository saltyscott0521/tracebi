# Credentials

The secrets a project's connections need: which names, where each is set, and
an encrypted store on the server.

```bash
tracebi secret list
```

```
TRACEBI_CRM_URL · set in store · used by crm.url
TRACEBI_BANK_URL · default · used by bank.url
TRACEBI_SNOW_PASSWORD · MISSING · used by snow.password
```

A connection names its secret as `${NAME}` ([[connections-yaml]]; also
`key_id` and `secret` in [[tracebi-yaml]]). Each name is looked up in this
order:

1. the process environment,
2. the project's `.env`,
3. the project's credential store, `.tracebi/secrets.yml.enc`,
4. a default written as `${NAME:-default}`.

The environment wins, so a vault or secrets manager that injects variables
always overrides the store. Nothing is copied into `os.environ`. A default is
checked like a literal value of its field: a SQLite path or a URL with no
password is fine, a URL with a password is refused, and `password` takes no
default.

A name is "missing" only when something references it. `tracebi validate`
prints one line for each missing name.

## Commands

```bash
tracebi secret set TRACEBI_CRM_URL            # prompts, no echo
printf %s "$URL" | tracebi secret set TRACEBI_CRM_URL --from-stdin
tracebi secret list
tracebi secret unset TRACEBI_CRM_URL          # the store's value only
tracebi secret edit                           # the decrypted YAML in $EDITOR, encrypted on save
tracebi connect crm --kind postgres --url ... --store secret   # the store instead of .env
```

## The store

| Property | Value |
|---|---|
| File | `.tracebi/secrets.yml.enc` in the project root, mode `0600`, created on the first write |
| Format | Decrypted: plain YAML, one `NAME: value` per line. On disk: one [Fernet](https://cryptography.io/en/latest/fernet/) ciphertext. `pip install 'tracebi[web]'` brings `cryptography`. |
| Key | `TRACEBI_SECRET_KEY` (a Fernet key) when set, else `.tracebi/secret.key`, generated `0600` on the first write |
| Several workers | Must share `TRACEBI_SECRET_KEY`, as they share `TRACEBI_STATE_URL`. A store read with a different key fails naming the file, never as "not set". |
| History | Who set a value and when is in History (one row per change), not in the file. |
| Older store | `.tracebi/secrets.json` (before 0.9) is still read and is rewritten in the new form on the next change. |
| Git | Both files are gitignored (`tracebi init` writes the lines). `tracebi push` never sends `.tracebi/`, and nothing puts it in a report or a session export. |

Make a key:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## In the app

On Data → Sources, a connection's **Connection** section shows each name it
uses and where it is set: `Set · environment`, `Set · .env`, `Set here`,
`Set · default` or `Missing`.

- A signed-in admin sees **Set…** or **Replace…**, and **Remove** for a value
  the store holds. After saving, **Test connection** opens the connection,
  counts its tables and closes it.
- Viewers and analysts see the states, not the buttons.
- No page ever shows a value, including one just typed.

Writes need an identified admin: an `admin` role from OIDC sign-in, a proxy
role header, or Basic auth with `TRACEBI_AUTH_ROLE_MAP`. With no sign-in,
everyone is admin by default, so a write is refused with 403
(`credentials are set on the server: tracebi secret set NAME`). Otherwise
anyone who could reach an open server could point its connections at a host
of their choosing.

## API

| Route | Role | Answer |
|---|---|---|
| `GET /api/credentials` | viewer | `{credentials: [row], key_source: env\|file, can_change}` |
| `PUT /api/credentials/{name}` `{value}` | identified admin | The row: 201 new, 200 replaced, 422 for a name nothing references |
| `DELETE /api/credentials/{name}` | identified admin | 204; 404 when the store holds none |
| `POST /api/connectors/{name}/test` | admin | `{ok: true, tables: n}` or `{ok: false, reason}` |

A row is `{name, used_by: [{kind: connection|warehouse, name, field,
default}], set, source: environment|dotenv|store|default|null, stored,
updated_at?, updated_by?, problem?}`. It never holds a value. A test's reason
has every resolved credential replaced by `***`.

Each set or unset, from the app or the CLI, records one row in the run store
(`kind: credential`, `target: NAME`, `status: set|unset`, the actor), shown in
History. Never the value.

## Limits

- It is not a vault integration. A vault injects environment variables, which
  win.
- It is not per person: one project, one set of connection secrets.
- It does not hold the app's own settings (`TRACEBI_OAUTH_SECRET`,
  `TRACEBI_STATE_URL`, `TRACEBI_SECRET_KEY`). Those stay in the process
  environment.
