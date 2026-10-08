### Added — a sign-in per person for the MCP connector

- Set `TRACEBI_OIDC_ISSUER` (with `TRACEBI_OIDC_CLIENT_ID` and
  `TRACEBI_OIDC_CLIENT_SECRET`) and the web app serves `/mcp` with OAuth 2.1
  sign-in, so ChatGPT and Claude connectors work with the company login. TraceBi
  is its own authorization server (protected-resource and authorization-server
  metadata, Client ID Metadata Document and Dynamic Client Registration clients,
  PKCE S256, one-hour access tokens, rotating refresh tokens) and an ordinary
  OIDC client of the identity provider, so the provider needs one app
  registration and no Application ID URI. Groups map to viewer, analyst and
  admin with `TRACEBI_OIDC_ROLE_MAP`; a viewer's connector reads and queries but
  cannot write drafts, build, render or publish.
- The person is the audit actor and the drafts owner for what they do through
  the connector. `TRACEBI_MCP_TOKEN` still works beside it for automation.
- Clients, grants, codes and tokens are in the run store (`tracebi_oauth_*`,
  Alembic revision 0003); codes and tokens are stored as SHA-256 hashes.
- `TRACEBI_PUBLIC_MCP_URL` and `TRACEBI_OAUTH_REDIRECTS` are new. See
  `docs/guides/connect-chatgpt-and-claude.md`.
