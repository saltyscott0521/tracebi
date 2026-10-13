### Added — folder permissions for the report library

- A folder in the library (any directory that is not a report package) may hold
  a `_folder.yaml` granting `view`, `build`, `publish` and `manage` (each
  includes the ones before it) to sign-in groups or names. The nearest file
  wins and is read on every request. With no `_folder.yaml` anywhere nothing
  changes: roles decide. Admins always keep the folder, and a malformed file
  grants nobody else anything instead of failing open. See
  `docs/reference/folder-yaml.md`.
- One check, `tracebi.permissions`, asked by `open_report` (the one read of a
  named report), so the web app, the agent gateway, the scheduler and the CLI
  share it. A report in a folder you cannot view is not in the lists
  (`/api/reports`, `/api/runs`, `/api/discovery`, `list_reports`) and every
  route, share link and tool answers as for a name that does not exist;
  `fetch_artifact` and `verify_manifest` do not find its built files. Drafting
  in a folder needs `build`, publishing into it needs `publish` (`403`).
- Groups reach the check from the OIDC groups claim (app and `/mcp` sign-in,
  stored with the session and the access token), from
  `TRACEBI_AUTH_GROUPS_HEADER` in proxy mode, and from
  `TRACEBI_LOCAL_USERS=name:role@group+group:password` (the old form works).
  They travel across the web/library boundary beside the audit actor.
- The command line and the scheduler run as the operator and are not limited
  by folder files.
- Browser sessions gain a `groups` column (migration `0005`); a session opened
  before the upgrade has no groups until the person signs in again.
