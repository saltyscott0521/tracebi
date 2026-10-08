# Sign in to the app and the CLI

**With the company login turned on, everyone signs in to the TraceBi app as
themselves, and their role decides what they may do. The command line signs in
the same way: `tracebi login`.**

This is for the person who runs the server (an admin) and for the people who
use it. It uses the same identity-provider registration as the connector setup
in [[connect-chatgpt-and-claude]]; set that up first, then the one extra
redirect address below.

---

## Turn it on (admin)

Set the OIDC variables from [[connect-chatgpt-and-claude]]
(`TRACEBI_OIDC_ISSUER`, `TRACEBI_OIDC_CLIENT_ID`, `TRACEBI_OIDC_CLIENT_SECRET`,
`TRACEBI_OIDC_ROLE_MAP`, `TRACEBI_PUBLIC_URL`). The app's own sign-in comes on
with them. At your identity provider, **register two redirect URIs** on the one
app registration:

- `https://bi.example.com/oauth/callback` (the connectors)
- `https://bi.example.com/login/callback` (the app)

Restart. The server log says `app sign-in: /login`.

**This turns on role enforcement.** Elsewhere enforcement is opt-in so a
running server is never locked out of its own pipelines. Here you chose
per-person sign-in, so roles apply from the first request: `viewer` reads and
queries, `analyst` runs reports and writes drafts, `admin` also runs pipelines
and keeps selection cuts. A person in no mapped group gets
`TRACEBI_OIDC_DEFAULT_ROLE` (`viewer`). Map your admins before you restart.

**It replaces Basic and proxy-header auth.** The server refuses to start with
`TRACEBI_OIDC_ISSUER` and `TRACEBI_AUTH_USER`/`TRACEBI_AUTH_PASS` or
`TRACEBI_AUTH_PROXY_HEADER` together: pick one way to say who a person is. If a
proxy in front of TraceBi has a login of its own, let `/login`, `/logout`,
`/login/callback`, `/authorize`, `/token`, `/register`, `/revoke`,
`/oauth/callback`, `/mcp` and `/.well-known/` through without it.

## In the browser

Open the app. Without a session you are sent to the company login and, once
signed in, back to the page you asked for. The sidebar footer shows who you are
and a **Sign out** button. Signing out ends the session at TraceBi; your
identity provider may still be signed in, so the next visit signs you back in
without a password.

What is kept:

- The session is a random id in a cookie (`tracebi_session`: `HttpOnly`,
  `Secure` over https, `SameSite=Lax`). The database holds only its SHA-256.
- A session ends after **12 hours unused** or **7 days** in all, or when you
  sign out. Your role is read at sign-in; a change of group applies at the next
  one.
- The page shell (`/`, `/assets`) loads without a session because it holds no
  data. Every `/api`, `/r/` and `/dashboards/` request needs the session; the
  API answers `401` and the app sends you to sign in. `/api/health` stays open
  for probes.
- `GET /api/me` says who you are: `{actor, role, sign_in}`. `sign_in` is
  `oidc`, `basic`, `proxy` or `none`.

## From the command line

```bash
tracebi login --server https://bi.example.com
```

The command opens your browser at the company login, receives the answer on a
one-shot listener on `127.0.0.1` (a random port), and stores the result in
`~/.config/tracebi/credentials.json` (`$XDG_CONFIG_HOME` is respected), readable
by you alone (mode 0600). It registers itself with the server once and
remembers that. The address must be `https` (or loopback for local testing).

```bash
tracebi logout --server https://bi.example.com
```

revokes the sign-in at the server and removes the tokens from the file.

The tokens are TraceBi access tokens (one hour) with a refresh token (rotated
on each use, 7 days sliding, 30 days at most). Tools that call the server's API
for you send `Authorization: Bearer <token>`, acting as you with your role;
`tracebi.credentials.access_token(server)` returns a valid one and refreshes it
when it is about to expire. When the sign-in has ended it says to run
`tracebi login` again.

## If it does not work

| You see | Likely cause |
| --- | --- |
| "Sign-in could not be verified" after the company login | Wrong client secret or issuer, or `…/login/callback` is not registered at the provider. The reason is in the server log. |
| "Started in a different browser" | The sign-in link was opened in another browser than the one that began it. Start again. |
| A `403` for something you could do before | Enforcement is on: your group is not mapped to a role that allows it. |
| `tracebi login`: "says its address is …" | `TRACEBI_PUBLIC_URL` on the server differs from the address you passed. |
| `tracebi login` waits, the browser shows an error about the client | The server lost its record of this CLI. Run it again; it registers afresh. |

## Related

- [[connect-chatgpt-and-claude]]: the identity-provider registration and the connectors
- [[environment-variables]]: every variable
- [[remote-authoring]]: the design
