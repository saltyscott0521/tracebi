### Added — credentials people can manage, and `${NAME:-default}`

- A project's connection secrets can live in an encrypted store on the server,
  `.tracebi/secrets.yml.enc` (an encrypted YAML document, Fernet; `cryptography` joins the `web` extra), keyed
  by `TRACEBI_SECRET_KEY` or a generated `.tracebi/secret.key`. A `${NAME}`
  resolves from the environment, then `.env`, then the store, so every existing
  project behaves as before and a deployment's environment still wins. One
  resolver, `tracebi.project_credentials`, serves connection files and the
  object-tier warehouse keys. A store read under another key says so by name.
- `tracebi secret set|list|unset` on the server, `tracebi connect --store
  secret`, and a line per missing name in `tracebi validate`.
- `GET /api/credentials` lists every referenced name and where it is set,
  never a value; `PUT` / `DELETE /api/credentials/{name}` need a signed-in
  admin (with no sign-in, 403 naming `tracebi secret set NAME`), and each
  change records a `credential` run row. `POST /api/connectors/{name}/test`
  (admin) opens, counts tables and closes, its reason scrubbed of every
  resolved value.
- Data → Sources: a **Connection** section on each connection shows its
  credentials' states, with **Set…** / **Replace…** / **Remove** and **Test
  connection** for a signed-in admin. The Transform tab's Code view says which
  connections the transform reads and whether each is set.
- A connection value may carry a default, `${NAME:-default}`, used when the
  name is set nowhere. It is checked like a literal (a password has none; a
  URL default may not carry a credential). See `docs/reference/credentials.md`.
