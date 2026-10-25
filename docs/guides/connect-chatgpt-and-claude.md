# Connect ChatGPT and Claude

Let people add TraceBi as a connector in ChatGPT or Claude and sign in with
their company login. What they make is recorded under their name, and their
role decides what they may do.

## Before you begin

- The TraceBi web app running at a public `https` address that ChatGPT's and
  Claude's servers can reach (a VPN-only address will not work)
- An OIDC identity provider (Entra ID, Okta, Google, any OIDC provider), or
  see [[#No identity provider]] below
- Postgres for the run store if you run more than one worker

## How it works

TraceBi runs a small OAuth server for `/mcp`. A request to `/mcp` with no token
answers `401` and points at TraceBi's metadata. The connector registers itself
and sends the person to TraceBi's `/authorize`, which sends them on to your
identity provider. TraceBi checks the answer and gives the connector its own
short-lived tokens. It stores no passwords.

Because TraceBi issues the tokens, your provider needs one ordinary app
registration. Nothing is registered there for ChatGPT or Claude, and Entra
needs no Application ID URI for the MCP address.

## For admins: turn it on

1. Set the public address:

   ```bash
   TRACEBI_PUBLIC_URL=https://bi.example.com
   ```

   The MCP address is that origin plus `/mcp`: `https://bi.example.com/mcp`.
   People paste this exact address into the connector. If yours differs, set
   `TRACEBI_PUBLIC_MCP_URL`.

2. Register TraceBi at your identity provider as one web application with a
   client secret:

   - Redirect URI: `https://bi.example.com/oauth/callback`. If people also
     sign in to the app and the CLI, add `https://bi.example.com/login/callback`
     ([[sign-in]]).
   - Scopes: `openid`, `email`, `profile`.
   - Send the person's groups in the ID token. In Entra: *Token
     configuration*, add a groups claim (security groups). In Okta: add a
     `groups` claim to the ID token. Entra sends group object IDs and Okta
     sends group names; use the same values in the role map. Entra stops
     listing groups past 200, so assign the app to a small set of groups.

3. Give TraceBi the registration:

   ```bash
   TRACEBI_OIDC_ISSUER=https://login.microsoftonline.com/<tenant-id>/v2.0
   TRACEBI_OIDC_CLIENT_ID=<application id>
   TRACEBI_OIDC_CLIENT_SECRET=<secret>
   TRACEBI_OIDC_ROLE_MAP=<admin-group>:admin,<analyst-group>:analyst
   ```

   The issuer is the provider's single-tenant issuer;
   `<issuer>/.well-known/openid-configuration` must exist. A mistake stops the
   server at startup with the reason. It never starts half open.

4. If a proxy or SSO gateway sits in front of TraceBi, let these paths through
   without its login (they carry their own authentication): `/mcp`,
   `/authorize`, `/token`, `/register`, `/revoke`, `/oauth/callback`,
   `/login`, `/login/callback`, `/logout` and everything under
   `/.well-known/`.

5. With more than one worker, point `TRACEBI_STATE_URL` at Postgres. Clients,
   codes and tokens live in the run store, so workers must share it
   ([[one-server]]).

6. Restart, then open
   `https://bi.example.com/.well-known/oauth-authorization-server`. It should
   answer with TraceBi's endpoints.

### Roles

| Role | In the connector |
| --- | --- |
| `viewer` | Reads and queries: `get_context`, `list_models`, `describe_*`, `query_model`, `list_reports`, `verify_manifest`, `fetch_artifact`, reading drafts |
| `analyst` | All of the above, plus drafts, previews, `build_report`, `render_report_spec`, `resolve_pin` and publishing |
| `admin` | The same tools as `analyst` |

A person gets the highest role of any of their groups in
`TRACEBI_OIDC_ROLE_MAP`. A person in none gets `TRACEBI_OIDC_DEFAULT_ROLE`,
`viewer` unless you change it. So anyone your provider lets sign in to the app
can read the models: assign the app only to the people you mean.

The role is read at sign-in and kept for that sign-in. A change of group takes
effect at the next sign-in: at most 30 days, sooner if they disconnect and
reconnect.

### Keep a token for automation

`TRACEBI_MCP_TOKEN`, if also set, still works for scripts and agents that
cannot sign in. Their work is recorded as `TRACEBI_MCP_ACTOR` (default
`agent`) with the `analyst` role. Leave it unset if you don't need it.

## No identity provider

For a demo, a trial or a small team, TraceBi can sign people in itself. Set
these instead of the `TRACEBI_OIDC_*` variables (the two cannot be combined):

```bash
TRACEBI_PUBLIC_URL=https://bi.example.com
TRACEBI_OAUTH_SECRET=<openssl rand -hex 32>
TRACEBI_DEMO_LOGIN=admin                         # a one-click demo user
TRACEBI_LOCAL_USERS=alice:analyst:a-long-password,vera:viewer:another-one
```

Use either or both. **Connect** then opens a TraceBi page: named users type a
name and password, and the demo user is one button, **Continue as the demo
user**. Work is recorded under the name (`demo`, `alice`), and the role in the
variable decides what each may do.

- **The demo button lets in anyone who has the address.** Use it only on a
  server with sample data, and give it the lowest role that shows what you
  want.
- **Passwords live in the environment** and are compared as written. There
  is no reset and no sign-up page. For a growing team, move to your company
  login.
- **Ten wrong passwords** for one name stop that name for ten minutes, per
  process. Run one worker.
- **It covers `/mcp` only.** The app's own pages are not put behind it.

## For users: add the connector

The menu names change; the address is what matters.

- **Claude** (claude.ai or the desktop app): *Settings*, *Connectors*, *Add
  custom connector*. Name it, paste `https://bi.example.com/mcp`, and add.
  Choose *Connect*; your company login opens.
- **Claude Code:** `claude mcp add --transport http tracebi https://bi.example.com/mcp`,
  then `/mcp` inside Claude Code to sign in.
- **ChatGPT:** *Settings*, *Connectors* (turn on developer mode if your plan
  asks), *Create*. Paste the same address, choose OAuth, and sign in. A
  workspace admin may need to allow custom connectors first.

Then ask: *"Start a draft of the sales report and add a chart of revenue by
region."* The reply links the draft in the app. Only you and admins can see
it.

## What happened

- **Tokens.** Access tokens last one hour. Refresh tokens last 7 days and are
  replaced on each use. A sign-in ends at 30 days at most. Reusing an old
  refresh token or an authorization code ends the whole sign-in.
- **Storage.** Codes and tokens are stored as SHA-256 hashes, so a copy of the
  database holds no working token. The provider's client secret is only in
  your environment.
- **Clients.** Clients that register themselves (Dynamic Client
  Registration) are stored until you remove them. ChatGPT and Claude may
  instead identify themselves with a Client ID Metadata Document, which
  TraceBi fetches from their public https address and does not store.
- **Redirects.** Only Claude's and ChatGPT's callbacks and loopback addresses
  (`localhost`, `127.0.0.1`, any port) are allowed. Add others, exactly, with
  `TRACEBI_OAUTH_REDIRECTS`.

## If it does not work

| You see | Likely cause |
| --- | --- |
| The connector cannot reach the server | The address is not public, or a proxy blocks `/.well-known/` or `/mcp`. |
| "Resource mismatch", or the sign-in loops | The address in the connector is not exactly `TRACEBI_PUBLIC_URL`'s origin plus `/mcp` (or `TRACEBI_PUBLIC_MCP_URL`). |
| "Sign-in could not be verified" | Wrong client secret or issuer, the provider's clock is off, or the redirect URI at the provider is not `…/oauth/callback`. The server log has the reason. |
| "Started in a different browser" | The sign-in link was opened in a different browser. Start again from the connector. |
| A person is a viewer who should write | Their group is not in `TRACEBI_OIDC_ROLE_MAP`, or the provider sent no groups. Check the claim, then sign in again. |

## Next

- The same login for the app and the CLI: [[sign-in]]
- Host it: [[one-server]]
