### Added — sign in to the app, and `tracebi login`

- With `TRACEBI_OIDC_ISSUER` set, people sign in to the web app through the
  company identity provider (`/login`, `/login/callback`, `POST /logout`,
  `GET /api/me`). Register `<public url>/login/callback` beside the connector
  callback. Sessions are server-side (`tracebi_sessions`, Alembic revision 0004;
  only the SHA-256 of the id is stored), 12 hours idle and 7 days at most, in an
  `HttpOnly`, `SameSite=Lax` cookie (`Secure` over https). `next` only ever leads
  to a path of this app.
- Role enforcement is on in this mode: the provider's groups decide viewer,
  analyst or admin (`TRACEBI_OIDC_ROLE_MAP`). What people do is recorded under
  their name. Unauthenticated API calls get 401; page navigations are sent to
  sign in. The sidebar shows who is signed in and a Sign out button.
- **Breaking for one setup:** `TRACEBI_OIDC_ISSUER` can no longer be combined
  with `TRACEBI_AUTH_USER`/`TRACEBI_AUTH_PASS` or `TRACEBI_AUTH_PROXY_HEADER`;
  the server refuses to start.
- `tracebi login --server <url>` / `tracebi logout --server <url>`: OAuth 2.1 with
  PKCE and a loopback redirect against the server's own authorization server.
  Tokens are kept in `~/.config/tracebi/credentials.json` (mode 0600);
  `tracebi.credentials.access_token(server)` refreshes them. The app's API also
  accepts `Authorization: Bearer tbat_...` access tokens. See
  `docs/guides/sign-in.md`.
