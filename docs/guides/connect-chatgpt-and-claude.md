# Connect ChatGPT and Claude

**People sign in to the TraceBi connector with their company login. What they
make is theirs: drafts, publishes and runs are recorded under their name, and
their role decides what they may do.**

This is for the person who runs the TraceBi server (an admin) and for the
people who then add the connector. It needs the web app, because the sign-in
pages live there. The design is in [[remote-authoring]].

---

## How it works

TraceBi runs a small OAuth server for `/mcp`. ChatGPT and Claude find it on
their own: a request to `/mcp` with no token answers `401` and points at
TraceBi's metadata, and the connector registers itself and sends the person to
TraceBi's `/authorize`. TraceBi holds no passwords. It sends the person on to
your company's identity provider (Entra ID, Okta, Google, any OIDC provider),
checks the answer, and then gives the connector its own short-lived tokens.

Because TraceBi issues the tokens, your identity provider only needs **one
ordinary app registration**. Nothing is registered for ChatGPT or Claude there,
and Entra needs no Application ID URI for the MCP address.

## Turn it on (admin)

**1. Pick the public address.** It must be `https`, and ChatGPT's and Claude's
servers must be able to reach it (a VPN-only address will not work). Set:

```bash
TRACEBI_PUBLIC_URL=https://bi.example.com
```

The MCP address is that origin plus `/mcp`: `https://bi.example.com/mcp`. This
exact address is what people paste into the connector. If yours differs, set
`TRACEBI_PUBLIC_MCP_URL` to it.

**2. Register TraceBi at your identity provider.** One web application with a
client secret:

- Redirect URI: `https://bi.example.com/oauth/callback`
- Scopes: `openid`, `email`, `profile`
- Send the person's groups in the ID token. In Entra: *Token configuration*,
  add a groups claim (security groups). In Okta: add a `groups` claim to the ID
  token. The claim carries group object IDs in Entra and group names in Okta;
  use the same values in the role map below. Entra stops listing groups when a
  person is in more than 200; assign the app to a small set of groups.

**3. Give TraceBi the registration:**

```bash
TRACEBI_OIDC_ISSUER=https://login.microsoftonline.com/<tenant-id>/v2.0
TRACEBI_OIDC_CLIENT_ID=<application id>
TRACEBI_OIDC_CLIENT_SECRET=<secret>
TRACEBI_OIDC_ROLE_MAP=<admin-group>:admin,<analyst-group>:analyst
```

The issuer is the provider's single-tenant OIDC issuer (the page at
`<issuer>/.well-known/openid-configuration` must exist). A misconfiguration
stops the server at startup with the reason; it never starts half open.

**4. Let the connectors' requests through.** If a proxy or SSO gateway sits in
front of TraceBi, these paths must reach it without a login of their own (they
carry their own authentication): `/mcp`, `/authorize`, `/token`, `/register`,
`/revoke`, `/oauth/callback` and everything under `/.well-known/`. The rest of
the app stays behind whatever you already use.

**5. Use Postgres if you run more than one worker.** Clients, codes and tokens
live in the run store (`TRACEBI_STATE_URL`), so several workers share them. See
the note on workers in [[one-server]].

Restart, then open `https://bi.example.com/.well-known/oauth-authorization-server`:
it should answer with TraceBi's endpoints.

### Roles

| Role | In the connector |
| --- | --- |
| `viewer` | reads and queries: `get_context`, `list_models`, `describe_*`, `query_model`, `list_reports`, `verify_manifest`, `fetch_artifact`, reading drafts |
| `analyst` | everything above, plus drafts, previews, `build_report`, `render_report_spec`, `resolve_pin` and publishing |
| `admin` | the same tools as analyst in the connector |

A person gets the highest role of any group in `TRACEBI_OIDC_ROLE_MAP`. A
person in none gets `TRACEBI_OIDC_DEFAULT_ROLE`, `viewer` unless you change it.
Anyone who can sign in at your identity provider and is assigned to the app can
therefore read the models: assign the app to the people you mean.

The role is read when the person signs in and kept for that sign-in. Move
someone between groups and it takes effect at their next sign-in (at most 30
days, sooner if they disconnect and reconnect).

### Automation keeps its token

`TRACEBI_MCP_TOKEN`, if also set, is still accepted for scripts and agents that
cannot sign in. Work done with it is recorded as `TRACEBI_MCP_ACTOR` (default
`agent`) with the `analyst` role. Leave it unset if you do not need it.

## Add the connector (each person)

The menu names change; the address is what matters.

**Claude** (claude.ai or the desktop app): *Settings*, *Connectors*, *Add
custom connector*. Name it, paste `https://bi.example.com/mcp`, and add. Choose
*Connect*; a window opens at your company login. Claude Code: `claude mcp add
--transport http tracebi https://bi.example.com/mcp`, then `/mcp` inside Claude
Code to sign in.

**ChatGPT**: *Settings*, *Connectors* (turn on developer mode if your plan asks
for it), *Create*. Paste the same address, choose OAuth, and sign in when the
window opens. A workspace admin may need to allow custom connectors first.

Then ask in plain words: *"Start a draft of the sales report and add a chart of
revenue by region."* The reply links the draft in the app. It is yours: other
people see it only if they are admins.

## What is kept, and for how long

- **Access tokens** last one hour. **Refresh tokens** last 7 days and are
  replaced each time they are used. A sign-in ends at 30 days at most.
- Presenting an old refresh token, or an authorization code a second time,
  ends that whole sign-in: the person signs in again.
- Codes, access tokens and refresh tokens are stored as SHA-256 hashes. A copy
  of the database holds no working token. The provider's client secret is only
  in your environment.
- Clients that register themselves (Dynamic Client Registration) are stored
  until you remove them. ChatGPT and Claude may instead identify themselves with
  a Client ID Metadata Document, which TraceBi fetches from the client's
  public https address and does not store.
- Return addresses are limited to Claude's and ChatGPT's callbacks and loopback
  addresses (`localhost`, `127.0.0.1`, any port). Add others, exactly, with
  `TRACEBI_OAUTH_REDIRECTS`.

## If it does not work

| You see | Likely cause |
| --- | --- |
| The connector says it cannot reach the server | The address is not public, or a proxy blocks `/.well-known/` or `/mcp` |
| "Resource mismatch" or the sign-in loops | The address in the connector is not exactly `TRACEBI_PUBLIC_URL`'s origin plus `/mcp` (or `TRACEBI_PUBLIC_MCP_URL`) |
| "Sign-in could not be verified" on return | Wrong client secret or issuer; the provider's clock is off; the redirect URI at the provider is not `…/oauth/callback`. The reason is in the server log. |
| "Started in a different browser" | The person opened the sign-in link in another browser than the one that began it. Start again from the connector. |
| A person is a viewer who should write | Their group is not in `TRACEBI_OIDC_ROLE_MAP`, or the provider did not send groups. Check the claim, then sign in again. |

## Related

- [[remote-authoring]] — the design: drafts, publishing, and this sign-in
- [[environment-variables]] — every variable above
- [[one-server]] — hosting on one server
