# Credentials: a store people can manage

*Built, 2026-10-23 (package U-C); the store became encrypted YAML the same
day. How to use it: `docs/reference/credentials.md`.*

## The problem

A connection keeps its secret out of the file as `${NAME}`
(`docs/reference/connections-yaml.md`). Today `${NAME}` resolves from the
process environment, then the project's `.env`. That is right for a laptop
and wrong for a server:

- An admin who wants to connect the CRM has to reach the box, edit `.env`
  (plaintext, mode whatever the editor left) or change the service's
  environment and restart.
- Nobody can see **which** credentials a project needs, which are set, and
  which connection is waiting on which name. The CRM's panel says "Not
  connected here · set `TRACEBI_CRM_URL`" and stops.
- `.env` is one flat file for everything: a transform's `load_dotenv()`
  variables, the app's own settings, and database passwords, side by side.

## What it should feel like

In the app, Data → Sources, a connection's panel shows its credentials as a
short list: the name, where it is set (environment, `.env`, here, or
missing), and for a signed-in admin a **Set…** button. Setting one opens a
dialog with a password field and Save; the panel then offers **Test
connection** and, on success, the Tables list fills in. Values never come
back to the browser. On the server the same store is `tracebi secret set
NAME`. Nothing about the connection file changes: it still says
`url: ${TRACEBI_CRM_URL}`, and a checkout without the store still works from
the environment.

## Design

### The store

`.tracebi/secrets.yml.enc` in the project root, the shape Rails credentials
(`credentials.yml.enc` + `master.key`) and Ansible Vault use: one file whose
plaintext is a plain YAML mapping, `NAME: value`, encrypted whole with
[Fernet](https://cryptography.io/en/latest/fernet/) (`cryptography`, in the
`web` extra; a store read without it fails loudly per core invariant 4), mode
`0600`, created on first write. `tracebi secret edit` decrypts it to a `0600`
temp file, opens `$VISUAL` / `$EDITOR`, validates what comes back (names,
non-empty string values) and encrypts it again. Who set a value and when is
the audit row, not the file. The first design (0.8) kept a JSON object of
per-value tokens with the metadata beside each; that file is still read and
is rewritten in the new form on the next change.

The key, in order: `TRACEBI_SECRET_KEY` (a Fernet key, base64, 32 bytes),
else `.tracebi/secret.key`, generated `0600` on first use. One process
generating its own key is the laptop and single-server case; several
replicas must share `TRACEBI_SECRET_KEY`, and the docs say so where
`TRACEBI_STATE_URL` already says "point every worker at the same Postgres".
A store written under one key and read under another says exactly that
(`CredentialKeyMismatch`, naming the file), never "not set".

`.tracebi/secrets.yml.enc` and `.tracebi/secret.key` go in `.gitignore`
(`tracebi init` writes it; the repo's own `.gitignore` gains the two lines).
`tracebi push` never packages `.tracebi/`; `POST /api/library/sync` never
pulls it; the session export never reads it.

### Resolution

One function, `tracebi.credentials.resolve(name, root) -> (value, source)`,
with `source` one of `environment`, `dotenv`, `store`, and `Missing` raised
otherwise. Order: **environment → `.env` → store.** The environment stays
first so a deployment's own configuration always wins over anything saved
through the app, and so the behaviour of every existing project is unchanged
(the store is only ever consulted after the two places that exist today).

Every `${NAME}` reader calls it:

- `connections._Resolved._env` (`tracebi/connections.py`), the connection
  files.
- `project_config` for the object-tier warehouse's `key_id` / `secret`
  (`tracebi.yaml`), which is a `${VAR}` by rule.

Nothing is copied into `os.environ` (the same rule as `.env` today).

### Which names a project needs

`tracebi.credentials.required(root) -> list[Requirement]`, each
`{name, used_by: [{kind: connection|warehouse, name, field}]}`: every
`${NAME}` in `connections/*.yaml` plus the warehouse block. This is the list
the page and the CLI show, so a name is only ever "missing" against
something that references it. `status(root)` joins it with `resolve`, never
with the value: `{name, used_by, set: bool, source, updated_at?,
updated_by?}`.

### API (admin; values never returned)

```
GET    /api/credentials                 → [status rows], plus key_source: env|file
PUT    /api/credentials/{name}          {value}  → the status row (201 new / 200 replaced)
DELETE /api/credentials/{name}          → 204 (store entry only; an environment value is untouched and the row says so)
POST   /api/connectors/{name}/test      → {ok: true, tables: n} | {ok: false, reason}   (opens, lists, closes; reason redacted of any secret)
```

Writes need an **identified** admin: a sign-in role of `admin` (OIDC,
proxy header, Basic with a role map, or `TRACEBI_LOCAL_USERS`). An app with
no sign-in at all, where every caller is `admin` by the no-lockout rule, gets
`403 {reason: "credentials are set on the server: tracebi secret set NAME"}`
on `PUT` and `DELETE`. The read is open to `admin` as usual. This is the one
place the no-lockout rule is narrowed, because the public demo would
otherwise let anyone point the server's connections at hosts of their
choosing. `_required_role` in `tracebi/web/api/auth.py` names the three
routes explicitly (`admin`), per authorization invariant 3.

Each write records one `tracebi_runs` row, `kind: credential`, `target:
NAME`, `status: set | unset`, with the actor; no value, ever. History shows
it like any other run.

### CLI

```
tracebi secret set NAME            # prompts, no echo; --from-stdin for scripts
tracebi secret list                # NAME · set from environment | .env | store | MISSING · used by crm.url
tracebi secret unset NAME
tracebi connect … --store secret   # write the secret here instead of .env (default stays .env)
```

`tracebi validate` (the existing checks) gains a line per missing name.

### UI

- **Sources tab, connection panel** (`web/ui/src/pages/Connectors.jsx`): a
  "Credentials" block under "Where the data lives": one row per name with a
  status chip (`Set · environment`, `Set · .env`, `Set here`, `Missing`),
  the field it fills, and for an identified admin **Set…** / **Replace…** /
  **Remove** (remove only for a store value). The dialog: name (read-only),
  a password input with a show toggle, Save. After Save: **Test connection**
  appears; on `ok` the Tables section loads.
- **Sources tab, list head**: a one-line banner when any name is missing:
  "2 credentials missing · crm, snowflake_prod" linking to the first.
- **Transform tab** (a model's page): the `-- source:` line's connection
  shows the same chip, so "why did the snapshot stand in?" has an answer
  where the question arises.
- Viewer and analyst see the chips, never the buttons. Nothing in the UI
  ever displays a value, including the one just typed after Save.

### What this is not

- Not a vault integration. A team with Vault or AWS Secrets Manager injects
  environment variables, which win. The store is the easy path, not the
  only path.
- Not per-user credentials. One project, one set of connection secrets, as
  today; the audit row says who set it.
- Not a place for the app's own settings (`TRACEBI_OAUTH_SECRET`,
  `TRACEBI_STATE_URL`): those configure the process and stay environment.

## Acceptance

`tests/e2e/test_reference_project.py` gains the steps: `crm` resolves
`TRACEBI_CRM_URL` from the store when the environment lacks it and the
certificate records the live load; `GET /api/credentials` lists the name as
missing before and `store` after; a `PUT` from an unidentified admin is 403
and from a `TRACEBI_LOCAL_USERS` admin is 201; the value never appears in
any response or log line; a store written under another key fails by name.
The folder-permissions and sign-in journeys assert viewer and analyst get
403 on `PUT`. `test_phase5`-style unit coverage only for the Fernet
round-trip and the resolution order.
