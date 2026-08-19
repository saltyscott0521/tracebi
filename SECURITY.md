# Security Policy

## Reporting a vulnerability

Please report suspected vulnerabilities **privately** — do not open a public
issue, and do not include exploit details in a public pull request.

Use GitHub's private vulnerability reporting for this repository:
**Security → Report a vulnerability** (the "Report a vulnerability" button on
the repository's Security tab). That opens a private advisory visible only to
the maintainers.

Please include:

- the affected version or commit,
- a description of the issue and its impact,
- steps to reproduce (a minimal proof-of-concept is ideal),
- any suggested remediation.

We aim to acknowledge a report within a few business days and to keep you
updated as we investigate and prepare a fix. Please give us reasonable time to
release a fix before any public disclosure.

## Supported versions

TraceBi is pre-1.0 and moves fast; security fixes land on the default branch
(`main`). There is no long-term-support branch yet — run a recent `main`.

## Scope and hardening notes

A few security-relevant behaviors are **opt-in by design** and are the
operator's responsibility to configure before exposing a deployment:

- **Authentication and authorization are opt-in.** With no auth source
  configured, the API (including endpoints that execute code or write to the
  warehouse) is open to anyone who can reach it, and every caller resolves to
  `admin`. Set `TRACEBI_AUTH_USER`/`TRACEBI_AUTH_PASS` or
  `TRACEBI_AUTH_PROXY_HEADER` (and `TRACEBI_AUTH_ROLE_MAP` for roles) before
  exposing the server beyond localhost. See the Authorization section of
  `CLAUDE.md` and `.env.example`.
- **Bind address.** The dev server and report preview bind loopback
  (`127.0.0.1`). Do not re-expose them on `0.0.0.0` without a proxy and auth.
- **Cross-origin / CSRF.** State-changing requests from a browser are
  refused unless the `Origin` is the app's own or listed in
  `TRACEBI_ALLOWED_ORIGINS`.
- **Artifact writes.** The MCP gateway confines writes out of the installed
  package by default; set `TRACEBI_OUTPUT_ROOT` for strict confinement.
- **Error detail.** Full tracebacks are returned only under
  `TRACEBI_DEV_MODE=1`.

## What the receipt does and does not attest

The report "receipt" attests that a number **reproduces** from its recorded
query against a materialized model, and that the shipped file is
integrity-checkable — not that a number is *correct*, and not (until signing
lands) that it came from a particular party. Treat a received report as
documentation; it becomes third-party evidence only when the verifier
independently holds the warehouse or a trusted signature. See `MANIFESTO.md`.
