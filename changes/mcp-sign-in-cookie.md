### Fixed — connector sign-in keeps nothing on the server until it succeeds

- `/authorize` (connector sign-in over `/mcp`) no longer writes a
  `tracebi_oauth_pending` row per request. What the return trip needs (the
  grant, nonce, PKCE verifier) travels in the same `HttpOnly` per-flow cookie
  that binds the sign-in to the browser that began it, now signed with a key
  derived from the identity provider client secret. A stranger's requests can
  no longer grow the run store. The table stays (unused) so no migration is
  needed.
