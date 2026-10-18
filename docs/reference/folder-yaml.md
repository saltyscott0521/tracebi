# Folder permissions (`_folder.yaml`)

**Who may see, build in, publish into and manage a folder of the report library,
in a small file that sits in the folder.**

A folder in the library is any directory under `reports/` (or a mount, see
`TRACEBI_LIBRARY_MOUNTS` in [[environment-variables]]) that is not itself a
report package. Put a `_folder.yaml` in it to say who may do what there. The
file is optional: with no `_folder.yaml` anywhere, the roles `viewer`,
`analyst` and `admin` decide, exactly as before, and nobody is locked out.

---

## Example

```yaml
# reports/finance/_folder.yaml
view:    [finance, ceo@example.com]    # see the folder; open reports and their builds
build:   [finance-analysts]            # + create and edit drafts in it
publish: [finance-leads]               # + publish a draft into it; its schedules
manage:  [bi-admins]                   # + change this file
accepts: checkable                     # optional: only re-checkable numbers (see below)
```

---

## Keys

Four keys, each a name or a list of names. Names are sign-in **groups** or
**person names** (the sign-in name: usually an email), compared ignoring case.
`'*'` means every signed-in person.

| key | may |
|---|---|
| `view` | see the folder in lists; open its reports, past builds, traces, lineage, downloads and share links |
| `build` | view, and start and edit drafts in the folder |
| `publish` | build, and publish a draft into the folder; change a report's schedule |
| `manage` | publish, and change the folder's permissions |

A level includes the ones above it in the table: someone named under `publish`
also builds and views. Any other key, or a value that is not a name or a list
of names, makes the file malformed (see below).

---

## What a folder accepts

`accepts` is the one key that is not a permission. It says what may be
published into the folder, and binds everyone who publishes there, admins
included.

| value | the folder takes |
|---|---|
| `labelled` (default) | anything honestly labelled: a number that cannot be re-run says so in its trace |
| `checkable` | only reports whose every number a query can re-run |

Under `checkable`, publishing a draft (or asking to) is refused with a plain
message naming the cause when the report has a `report.py` (Python computes its
numbers), or when its build holds a figure's data that is marked
`verifiable: false` or is not a single recorded query. A figure that a page's
`script.js` changes in the browser is marked in the trace when the page runs,
so it cannot be judged at publish time. Any other value of `accepts` makes the
file malformed (below), and a malformed file reads as `checkable`.

---

## Publishing into a folder, and asking to

A draft of a report is published to a folder you choose (`folder`, a library
path such as `finance/q3`; it is created if it does not exist, and the report
keeps its last name). What happens depends on the level you hold on the
destination, checked against its nearest `_folder.yaml`:

- **`publish`** (or more): it is published, as before. The history beside the
  kept versions (`.tracebi/history/reports/<path>/publishes.jsonl`) records who
  published and when.
- **`build` only**: it becomes a **publish request**, not a publish. The
  request holds a copy of the draft as it was when asked. It is a file,
  `drafts/_requests/<id>.json`, so it survives a restart. Anyone with
  `publish` on the destination can **approve** it (the copy is published
  exactly as a direct publish would, and the history records who asked, who
  approved and when) or **reject** it with a note. The permission is checked
  when they decide, not when it was asked, so a requester with only `build`
  cannot approve their own.
- **less than `build`**: refused, `403`, naming the permission.

With no `_folder.yaml` anywhere, roles decide as before: an analyst publishes
directly and there are no requests. A person sees their own requests, and those
into folders where they hold `publish`.

---

## My published

Every signed-in person has a folder of their own, `my-published/<their sign-in
name>/` under the library (shown in the app as **My published**, always listed,
even empty). They hold `publish` there without any `_folder.yaml`, so a report
published into it is shareable and schedulable without the shared folders.

- Nobody else sees it. To share it, put a `_folder.yaml` **inside that folder**
  (`view: [bob@example.com]`). A `_folder.yaml` higher up, even `view: ['*']`,
  never reaches in. Admins keep `manage`, as everywhere.
- The app shows a folder's permissions, read-only, to people with `manage` and
  to the owner of a personal folder. Editing is file-only for now, and the app
  says so.
- A session with no sign-in identity (the shared gateway token, the command
  line, the scheduler, an app with no sign-in) has no personal folder; it holds
  `manage` everywhere and publishes into a shared folder. `GET /api/folders`
  answers `personal: null` with the reason.
- Not offered when `TRACEBI_LIBRARY_MOUNTS` is set: the library is then several
  labelled roots with no place for it.

In the app, a draft's **Publish** step lists the places it can go (My published,
each folder where you hold `build` or more, and its own place) and says for
each whether it publishes directly or sends a request. Approvers (`publish` on
the folder) see pending requests under **Review** (Needs attention) and approve, or decline with
a reason the requester sees.

---

## How a file applies

1. **The nearest file wins.** Starting at a report's folder and walking up to
   the library root (or the mount), the first `_folder.yaml` found is the whole
   rule for everything below it. It replaces the files above it; it does not add
   to them. A sub-folder that should be open to everyone says so itself
   (`view: ['*']`).
2. **It is read at request time.** Edit the file and the next request sees it:
   no restart, no rescan.
3. **A folder narrows a role; it never widens one.** The role still limits what
   kind of thing a person may do: a `viewer` who is named under `manage` is
   still only a viewer, because the routes keep checking roles. Roles are the
   ceiling, folders decide where.
4. **Admins keep the folder.** The `admin` role always has Manage, so a typo in a
   file cannot lock out the people who can fix it. So does anything with no
   sign-in role at all: the command line, the scheduler, a notebook, and an app
   run without authentication.
5. **A malformed file fails closed.** If the file cannot be read or parsed, or
   has a key it does not know (`veiw:`) or an `accepts` it does not know, nobody but admins is granted anything
   under it, a warning is logged, and nothing else breaks. An **empty** file is
   valid and grants no one but admins.

---

## What "hidden" means

A person without `view` on a folder gets the same answer for its reports as for
a name that does not exist: they are not in `GET /api/reports`, the agent
gateway's `list_reports`, `GET /api/discovery` or `GET /api/runs`; opening,
running, downloading, reading the source, lineage or past builds of one is a
404 (or, for the run history, an empty list); the share link `/r/<name>` is a
404; `fetch_artifact` and `verify_manifest` do not find its built files. Built
outputs inherit the folder's permissions.

A person who can see a report but lacks the level an action needs is refused
with **403** and the permission it needs (`build permission is needed on the
folder of finance/q3/pack`): starting a draft in the folder needs `build`,
publishing a draft into it needs `publish` (with `build` only, it becomes a
request, below).

---

## Where the groups come from

| Sign-in | Groups come from |
|---|---|
| App sign-in or `/mcp` sign-in through `TRACEBI_OIDC_ISSUER` | the ID token's groups claim (`TRACEBI_OIDC_GROUPS_CLAIM`, default `groups`), all of them, whether or not `TRACEBI_OIDC_ROLE_MAP` maps them to a role |
| Proxy headers (`TRACEBI_AUTH_PROXY_HEADER`) | the header named by `TRACEBI_AUTH_GROUPS_HEADER`, comma separated; the proxy must set or replace it, like the role header |
| Built-in `/mcp` sign-in (`TRACEBI_LOCAL_USERS`) | `name:role@group+group:password`, e.g. `alice:analyst@finance+ops:a-long-password` |
| Basic auth | no groups: name the person |
| The static `TRACEBI_MCP_TOKEN` | no groups. Beside a per-person sign-in it is the principal `mcp:<TRACEBI_MCP_ACTOR>` with the analyst role, so a folder opens to it only by that name. A gateway with only the token (and stdio) has no sign-in role at all, so it is the operator and sees every folder |

An agent acts as the person using it: over `/mcp` with a per-person sign-in, the
agent's list and reads are exactly the person's. Folder permissions only bind
an agent that signs in as a person.

---

## The command line and the scheduler

`tracebi report build`, `tracebi schedule run` and the in-server scheduler ask
the same check but run as the operator (role `cli`), which holds Manage
everywhere: they have no sign-in, and whoever runs them can already read the
files. A folder file does not stop a scheduled report from running.

Sessions opened before this feature have no stored groups: the person signs in
again to get their groups.
