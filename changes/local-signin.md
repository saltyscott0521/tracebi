### Added — a built-in sign-in for the MCP gateway

- With no identity provider, `TRACEBI_DEMO_LOGIN=<role>` adds a **Continue as
  the demo user** button, and `TRACEBI_LOCAL_USERS=name:role:password,…` adds a
  name-and-password form, to a sign-in page the gateway serves itself at
  `/oauth/callback`. Claude and ChatGPT connect to `/mcp` the same way as with
  a company login; work is recorded under the name and limited by the role.
  Needs `TRACEBI_PUBLIC_URL` and `TRACEBI_OAUTH_SECRET`; cannot be combined with
  `TRACEBI_OIDC_ISSUER`. Failed passwords are throttled per name and address.
  It signs in to `/mcp` only; the app's own pages are unchanged. For demos and
  small teams: the demo button lets in anyone with the address.
