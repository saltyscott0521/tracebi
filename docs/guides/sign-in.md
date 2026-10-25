# Sign in with your company login

Turn on single sign-on so people sign in to TraceBi with their company account
and get a role from their groups. The CLI uses the same sign-in through
`tracebi login`.

## Before you begin

- An OIDC identity provider (Okta, Entra ID, Google Workspace, Keycloak)
- The connector setup from [[connect-chatgpt-and-claude]], which registers the
  app with your provider

## For admins: turn it on

1. Set these variables on the server: `TRACEBI_OIDC_ISSUER`,
   `TRACEBI_OIDC_CLIENT_ID`, `TRACEBI_OIDC_CLIENT_SECRET`,
   `TRACEBI_OIDC_ROLE_MAP` and `TRACEBI_PUBLIC_URL`. The app's sign-in turns on
   with them.
2. At your identity provider, add a second redirect URI to the same app
   registration: `https://bi.example.com/login/callback`. The first,
   `https://bi.example.com/oauth/callback`, is the connectors'.
3. Map your admins' group in `TRACEBI_OIDC_ROLE_MAP` before you restart.
   Roles apply from the first request.
4. Restart. The log prints `app sign-in: /login`.

### What changes

- **Roles are enforced.** `viewer` reads and queries. `analyst` also runs
  reports and writes drafts. `admin` also runs pipelines and keeps selection
  cuts. A person in no mapped group gets `TRACEBI_OIDC_DEFAULT_ROLE`
  (`viewer`). Without sign-in, enforcement is off so a running server is never
  shut out of its own pipelines; turning sign-in on is your choice to
  enforce.
- **It replaces Basic and proxy-header auth.** The server refuses to start
  with `TRACEBI_OIDC_ISSUER` and either `TRACEBI_AUTH_USER`/`TRACEBI_AUTH_PASS`
  or `TRACEBI_AUTH_PROXY_HEADER`.
- **A proxy in front must let some paths through.** If a proxy has a login of
  its own, let `/login`, `/logout`, `/login/callback`, `/authorize`, `/token`,
  `/register`, `/revoke`, `/oauth/callback`, `/mcp` and `/.well-known/`
  through without it.

## For users: sign in to the app

1. Open the app. Without a session you are sent to the company login, then
   back to the page you asked for.
2. The sidebar shows the places your role uses: Reports and Docs for
   everyone; Review and Data for analysts and admins. Only an admin runs a
   refresh or sets a credential.
3. To sign out, click **Sign out** in the sidebar footer. This ends the
   TraceBi session. Your identity provider may still be signed in, so the next
   visit can sign you back in without a password.

## For users: sign in from the command line

```bash
tracebi login --server https://bi.example.com
```

This opens your browser at the company login and stores the result in
`~/.config/tracebi/credentials.json` (`$XDG_CONFIG_HOME` is respected),
readable only by you. The address must be `https`, or loopback for local
testing.

```bash
tracebi logout --server https://bi.example.com
```

This revokes the sign-in at the server and removes the tokens from the file.

Tools that call the API for you send `Authorization: Bearer <token>` and act
as you, with your role. `tracebi.credentials.access_token(server)` returns a
valid token and refreshes it when needed. When the sign-in has ended it tells
you to run `tracebi login` again.

## What happened

- **The session** is a random id in a cookie (`tracebi_session`: `HttpOnly`,
  `Secure` over https, `SameSite=Lax`). The database stores only its SHA-256.
  It ends after 12 hours unused, 7 days in all, or when you sign out.
- **Your role** is read at sign-in. A change of group applies at the next
  sign-in.
- **Protected paths.** The page shell (`/`, `/assets`) loads without a
  session because it holds no data. Every `/api`, `/r/` and `/dashboards/`
  request needs one: the API answers `401` and the app sends you to sign in.
  `/api/health` stays open for health checks.
- **Who am I.** `GET /api/me` returns `{actor, role, sign_in}`, where
  `sign_in` is `oidc`, `basic`, `proxy` or `none`.
- **CLI tokens** are TraceBi access tokens that last one hour, with a refresh
  token that rotates on each use (7 days sliding, 30 days at most). The CLI
  receives them on a one-time listener on `127.0.0.1` (a random port), and
  registers itself with the server once.

## If it does not work

| You see | Likely cause |
| --- | --- |
| "Sign-in could not be verified" after the company login | Wrong client secret or issuer, or `…/login/callback` is not registered at the provider. The server log has the reason. |
| "Started in a different browser" | The sign-in link was opened in a different browser from the one that started it. Start again. |
| A `403` for something you could do before | Your group is not mapped to a role that allows it. |
| `tracebi login`: "says its address is …" | `TRACEBI_PUBLIC_URL` on the server differs from the address you passed. |
| `tracebi login` waits and the browser shows a client error | The server lost its record of this CLI. Run it again; it registers afresh. |

## Next

- Push work from your laptop once signed in: [[push-from-a-laptop]]
- Every variable: [[environment-variables]]
