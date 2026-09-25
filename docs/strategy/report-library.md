# Report library

**Reports live in folders people can browse in the app, the way QlikView showed
the documents on its server. The folders can sit on the server, on a network
share, or in any source control system. Drafts are free to edit; published
reports are approved first. Every folder carries permissions, and every door
into TraceBi (the app, agents, schedules) checks them the same way.**

Status: design. Nothing here is built yet except the pieces marked ✅.

---

## What people see

```
Library
├── Finance/                  ← \\fileserver\bi\finance   (network share)
│   ├── Month end/
│   │   ├── close_pack/            Custom     scheduled Mon 07:00   ✓ last run
│   │   └── variance.json          JSON spec
│   └── Board/
│       └── q3_board_pack/         Custom     published 12 Sep by maria
├── Sales/                    ← git checkout, branch main
│   └── pipeline_weekly.json       JSON spec  scheduled
└── My work/                  ← this person's drafts, on the server
    └── margin_deep_dive/          Custom     draft
```

- **A folder is a space.** Any folder that is not itself a report is just a
  way to organise, as deep as a team wants.
- **Each report shows** its type (JSON spec or Custom ✅), owner, last change,
  schedule, last run, its source files ✅, and its past builds: last month's
  board pack is one click away, with its receipt.
- **Models and transforms** can be browsed the same way, so an analyst can see
  which model a report reads and who owns it.

## Where the files live

The server is configured with one or more **mounts**. Each is a top-level
folder in the library.

| Mount type | Example | Good for |
|---|---|---|
| Local folder | `/srv/tracebi/library` | A single server, a first install |
| Network share | `\\fileserver\bi\finance`, an NFS mount | Teams that already keep BI files on a share |
| Source control checkout | a git clone of `main`, an SVN working copy | Teams that want full history and review |
| Cloud storage (Cloud only) | a bucket per workspace | TraceBi Cloud |

The server reads the files where they are. Nothing is imported into a
database, so leaving TraceBi still means keeping everything.

## Source control is optional

Not every company uses git, and not every git user uses GitHub. TraceBi must
work without either.

- **Publishing is TraceBi's own step, not a git feature.** Someone asks to
  publish a draft; a person with publish rights on the target folder approves
  it in the app; TraceBi copies the report into the published folder and keeps
  the previous version.
- **TraceBi keeps its own history** beside each published report: every
  version, who published it, who approved it, and when. That works on a plain
  folder or a network share.
- **Source control is an adapter.** When a mount is a git checkout, publishing
  becomes a commit (or a pull request on hosts that have them), and history
  comes from git. Git first, on any host: GitHub, GitLab, Bitbucket, Azure
  DevOps, or a plain git server. Other systems can be added behind the same
  adapter: "save this change with this message" and "list this file's history".

For comparison, Bruin's command-line tool runs on a plain folder, but a Bruin
Cloud project maps to exactly one git repository. TraceBi should not require
that.

## Drafts and published

Borrowed from Qlik's split between personal work and published streams:

| | Drafts (My work, team drafts) | Published folders |
|---|---|---|
| Who can change them | The owner, or the team | Only through publishing |
| Review | The team's own habits | Approved before it goes live |
| Can be scheduled | No | Yes |
| Fits | Build: one-off analyses | Schedule: reports that repeat |

A one-off analysis can stay a draft forever and still be shared as a built
file. Only what runs on a schedule, or sits in a folder others rely on, needs
publishing.

## Permissions

Permissions are set per folder and inherited by everything below, like a file
share.

| Permission | May |
|---|---|
| View | See the folder, open reports and their past builds |
| Build | Create and edit drafts in the folder |
| Publish | Approve a draft into the folder, change its schedule |
| Manage | Change the folder's permissions and mounts |

Rules:

1. **Rules name groups from the company's sign-in** (SSO groups, or the proxy
   header TraceBi already reads), not individual users where it can be
   avoided.
2. **One check, used everywhere.** The web app, the agent gateway (MCP), the
   scheduler and the CLI all ask the library the same question: can this
   person do this to this path? The existing roles (viewer, analyst, admin)
   become the defaults a folder can override.
3. **An agent acts as the person using it.** An analyst's Claude sees exactly
   what the analyst sees. That needs a sign-in per person on the gateway,
   not today's single shared token.
4. **Built outputs inherit the folder's permissions.** A board pack's past
   builds are no more visible than the pack.
5. **Delivery is a deliberate exception.** A scheduled email goes to whoever
   is on its list; the app shows that list next to the schedule so a publisher
   sees who will receive it.

## Using it from a personal device with Claude

Say a company runs TraceBi on its own server. An analyst on their own laptop
wants Claude to help.

```
 Analyst's laptop                         Company server
 ┌───────────────────────┐   VPN or SSO   ┌──────────────────────────┐
 │ Claude Code / Desktop │ ─────────────► │ TraceBi agent gateway     │
 │ (or claude.ai)        │   HTTPS, their │  · signs in as the analyst│
 └───────────────────────┘   own sign-in  │  · reads the library      │
                                          │  · queries the warehouse  │
 No warehouse password,                   │  · writes only to their   │
 no data files on the laptop.             │    My work folder         │
                                          └──────────────────────────┘
```

Three ways, from best to worst for a company:

1. **Remote agent gateway (recommended).** Claude connects to
   `tracebi mcp --transport http` on the server ✅, over the company VPN or
   through its sign-in proxy. Claude can ask questions, validate and build
   reports, and check their numbers, all on the server. The warehouse password
   never leaves the server and no data files land on the laptop. To make this
   complete, the gateway needs a sign-in per person (so permissions and the
   audit trail name the analyst) and tools to write drafts into that person's
   My work folder. For claude.ai, which runs outside the company network, the
   gateway also needs a public address and OAuth sign-in.
2. **A local copy.** The analyst copies or checks out a folder to the laptop,
   installs TraceBi, and works with Claude Code there, the way a developer
   would. It works today, but the laptop then needs its own read access to the
   warehouse, and the drafts live on the laptop until they are published.
3. **The browser only.** The web app, with Ask on a report. No agent help with
   building.

Whichever way, what Claude sees passes through the AI provider. Some companies
will restrict which folders or models an agent may reach; folder permissions
are where that rule belongs.

## Keep in mind while building, starting now

These cost little today and are expensive to retrofit:

- **Address a report by its path, not only its name.** ✅ Two folders can
  each hold a `weekly_summary`; the registry is keyed by `finance/weekly_summary`.
- **Route every read of a report through one place** that could check
  permissions, including the Source view ✅, downloads, MCP tools and schedules.
- **Store built outputs per report path**, not in one flat `output/` folder. ✅
- **Assume nothing about git** outside a source-control adapter.
- **Record who did it** on every publish, build and schedule change. The audit
  attribution already exists for runs ✅.

## Order of work

| Step | What | Why first |
|---|---|---|
| 1 | Scan folders recursively; a Library page that browses them read-only | Useful on day one; no new security surface |
| 2 | Mounts in configuration (local folder, network share) | Matches how BI teams already store files |
| 3 | Folder permissions, enforced in the one check | Needed before anyone shares a server widely |
| 4 | My work, publish with approval, TraceBi's own version history | The Build → Schedule path, without git |
| 5 | Source-control adapter: git first | For teams that want their own history and review |
| 6 | Sign-in per person on the agent gateway; draft-writing tools | The personal-device path, done properly |

## Decided later

- **Editing in the app.** Browse only for now. Cloud will likely want in-app
  editing; it fits once drafts and publishing exist, because an edit can only
  ever land in a draft.
- **Locking.** Two people editing the same draft on a share. Last save wins
  until someone needs more.
