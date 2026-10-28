# Folder permissions (`_folder.yaml`)

A `_folder.yaml` in a library folder says who may see, build in, publish into
and manage that folder. A project (a top-level library folder, one area's
reports: [[workspace-and-projects]]) keeps its permissions in its own
`_folder.yaml`, and a folder inside it may have one of its own.

```yaml
# reports/finance/_folder.yaml: the finance project
view:    [finance, ceo@example.com]    # see the folder; open its reports and their builds
build:   [finance-analysts]            # + create and edit drafts in it
publish: [finance-leads]               # + publish a draft into it; change its schedules
manage:  [bi-admins]                   # + change this file
accepts: checkable                     # optional: only re-checkable numbers
```

- A library folder is any directory under `reports/` (or a mount,
  `TRACEBI_LIBRARY_MOUNTS` in [[environment-variables]]) that is not itself a
  report package. One directly under `reports/` is a project; the app lists it
  as one. The file is still `_folder.yaml`, and the API still calls it a
  folder (`/api/folders`, `folder`).
- The file is optional. With no `_folder.yaml` anywhere, the roles `viewer`,
  `analyst` and `admin` decide, and nobody is shut out.

## Permission keys

Each key is a name or a list of names. A name is a sign-in group or a person's
sign-in name (usually an email), compared ignoring case. `'*'` means every
signed-in person.

| Key | May |
|---|---|
| `view` | See the folder in lists; open its reports, past builds, traces, lineage, downloads and share links. |
| `build` | View, and start and edit drafts in the folder. |
| `publish` | Build, and publish a draft into the folder; change a report's schedule. |
| `manage` | Publish, and change the folder's permissions. |

Each level includes those above it in the table. Any other key, or a value
that is not a name or a list of names, makes the file malformed.

## `accepts`

What may be published into the folder. It binds everyone who publishes there,
admins included.

| Value | The folder takes |
|---|---|
| `labelled` (default) | Anything labelled correctly: a number that cannot be re-run says so in its trace. |
| `checkable` | Only reports whose every number a query can re-run. |

Under `checkable`, a publish (or a request) is refused with the cause when the
report has a `report.py`, or when its build holds a figure whose data is
marked `verifiable: false` or is not a single recorded query. A figure that a
page's `script.js` changes in the browser is marked in the trace when the page
runs, so it cannot be judged at publish time. Any other value is malformed,
and a malformed file reads as `checkable`.

## How a file applies

| Rule | Detail |
|---|---|
| The nearest file wins | Walking up from a report's folder to the library root (or mount), the first `_folder.yaml` is the whole rule for everything below it. It replaces the files above; it does not add to them. A sub-folder open to everyone says `view: ['*']` itself. |
| Read at request time | Edit the file and the next request sees it. No restart, no rescan. |
| Narrows, never widens | The role still limits what a person may do. A `viewer` named under `manage` is still a viewer. Roles are the ceiling; folders decide where. |
| Admins keep Manage | The `admin` role always has Manage, so a typo cannot shut out the people who fix it. So does anything with no sign-in role: the CLI, the scheduler, a notebook, an app without sign-in. |
| A bad file grants nothing | A file that cannot be read or parsed, or has an unknown key (`veiw:`) or `accepts` value, grants nobody but admins anything below it, and logs a warning. An empty file is valid and grants nobody but admins. |

## Publish into a folder, or ask to

A report draft is published into a folder you choose (`folder`, a library
path such as `finance/q3`; created if missing; the report keeps its name).
What happens depends on your level on the destination:

| Your level | Result |
|---|---|
| `publish` or more | Published. `.tracebi/history/reports/<path>/publishes.jsonl` records who and when. |
| `build` only | A publish request: a copy of the draft as it was, stored in `drafts/_requests/<id>.json`, so it survives a restart. Anyone with `publish` there can approve it (published exactly as a direct publish; the history records who asked, who approved and when) or reject it with a note. The level is checked when they decide, so a `build`-only requester cannot approve their own. |
| Less | Refused with `403`, naming the permission. |

With no `_folder.yaml` anywhere, an analyst publishes directly and there are
no requests. A person sees their own requests, and those into folders where
they hold `publish`.

In the app, a draft's **Publish** step lists where it can go (My published,
each folder where you hold `build` or more, and its own place), each marked as
a direct publish or a request. Approvers see pending requests under **Review**
(Needs attention).

## My published

Every signed-in person has a folder of their own,
`my-published/<sign-in name>/`, shown as **My published** and always listed,
even when empty. They hold `publish` there with no `_folder.yaml`, so a report
published into it can be shared and scheduled.

- Nobody else sees it. To share it, put a `_folder.yaml` inside it
  (`view: [bob@example.com]`). A file higher up, even `view: ['*']`, never
  reaches in. Admins keep `manage`.
- The app shows a folder's permissions, read-only, to people with `manage`
  and to a personal folder's owner. You edit them in the file.
- A session with no sign-in identity (the shared gateway token, the CLI, the
  scheduler, an app with no sign-in) has no personal folder. It holds `manage`
  everywhere and publishes into shared folders. `GET /api/folders` answers
  `personal: null` with the reason.
- There is none when `TRACEBI_LIBRARY_MOUNTS` is set.

## Hidden means not found

A person without `view` on a folder gets the same answer for its reports as
for a name that does not exist:

- They are not in `GET /api/reports`, the gateway's `list_reports`,
  `GET /api/discovery` or `GET /api/runs`.
- Opening, running, downloading, or reading the source, lineage or past
  builds of one is a 404 (an empty list for run history). `/r/<name>` is a
  404. `fetch_artifact` and `verify_manifest` do not find its files.
- Built outputs inherit the folder's permissions.

A person who can see a report but lacks the level an action needs gets
**403** with the permission (`build permission is needed on the folder of
finance/q3/pack`).

## Where groups come from

| Sign-in | Groups |
|---|---|
| App or `/mcp` sign-in through `TRACEBI_OIDC_ISSUER` | The ID token's groups claim (`TRACEBI_OIDC_GROUPS_CLAIM`, default `groups`), all of them, mapped to a role or not. |
| Proxy headers (`TRACEBI_AUTH_PROXY_HEADER`) | The header `TRACEBI_AUTH_GROUPS_HEADER` names, comma separated. The proxy must set or replace it. |
| Built-in `/mcp` sign-in (`TRACEBI_LOCAL_USERS`) | `name:role@group+group:password`, e.g. `alice:analyst@finance+ops:a-long-password`. |
| Basic auth | None: name the person. |
| `TRACEBI_MCP_TOKEN` | None. Beside a per-person sign-in it is the principal `mcp:<TRACEBI_MCP_ACTOR>` with the analyst role, so a folder opens to it only by that name. A gateway with only the token (or stdio) has no sign-in role, acts as the operator and sees every folder. |

An agent over `/mcp` with a per-person sign-in sees exactly what its person
sees. Folder permissions bind an agent only when it signs in as a person.

Sessions opened before folder permissions existed have no stored groups; the
person signs in again to get them.

## The CLI and the scheduler

`tracebi report build`, `tracebi schedule run` and the in-server scheduler use
the same check but run as the operator (role `cli`), which holds Manage
everywhere: they have no sign-in, and whoever runs them can already read the
files. A folder file never stops a scheduled report from running.
