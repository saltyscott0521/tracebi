# Push a report from your laptop

Build and preview on your own machine, then send the files to the server with
`tracebi push`. Reports and YAML models become your drafts. Python goes to an
admin, who reads the diff and approves it before it runs.

## Before you begin

- A local TraceBi workspace (you may work in it with an agent such as Claude
  Code)
- A server with sign-in turned on, and `tracebi login` done ([[sign-in]])
- The `analyst` role or higher

## What goes where

| You push | It becomes | Who decides |
| --- | --- | --- |
| A report package (`reports/<model>/<name>/`) | Your draft of that report | You publish it in the app |
| `models/<name>.yaml` or `.json` | Your draft of that model | You publish it; the impact check runs as usual |
| `transforms/*.sql` (with its `.contract.yaml`), `.py` or `.ipynb`, `pipelines/*`, `models/<name>.py`, `connections/*.yaml`, a package's `report.py` | One code request | An admin approves or declines it |

Data never goes. The server runs the transform with its own secrets and
builds its own warehouse, and the sink contract checks what landed. Any other
path, such as `inputs/orders.csv` or `data/warehouse.duckdb`, is refused.
Connections count as code because they decide which of the server's secrets a
transform reads.

## For users: push

1. Push reports and models:

   ```bash
   tracebi push reports/sales_model/weekly models/sales_model.yaml --server https://bi.example.com
   ```

2. Push code with a note. The admin reads the note beside the diff:

   ```bash
   tracebi push transforms/sales_transform.py --server https://bi.example.com \
       --note "Drop test accounts before the sink"
   ```

3. Open the links the command prints: one per draft, and the code request's
   id.

Paths are files, package folders, or folders of them, inside the current
workspace. Nothing is sent if a path is refused or a code request has no note.
If a draft already held a file you did not push, the command says so; delete
the file in the app if it should go.

## For admins: approve code

1. Open **Review**. A pending code request is under **Needs attention**.
2. Click **Review** on its row. Each file shows its diff against what is
   published; a new file says so.
3. Click **Approve and run**, or **Decline** with a reason the requester sees.

Approving copies the files in, keeps what they replace under
`.tracebi/history/code/<version>/`, and runs once every pipeline the request
touches: the pipelines it contains, and each `pipelines/*.yaml` whose
`transform` it changes. The run uses the server's secrets, the sink contract
checks what landed, and the request records the run and its result.

**Approval commits to git.** When the workspace is inside a git work tree
and the files the request writes have no uncommitted changes, approving makes
one commit of exactly those files: `transforms: <name> — <the request's
note>` (a line per file when there are several), the requester as author
(`<name> <name@tracebi.local>` when the sign-in name is not an email), you as
committer, and a `TraceBi-Request: <id>` trailer. It never pushes. With no
git, no repository, or those files changed by hand, approval goes ahead and
the request says why it made no commit.

**A transform an agent proposed** (`propose_transform`) arrives with a dry
run: it ran once, when proposed, against a throwaway copy of the warehouse,
and nothing real was written. The row shows its verdict ("Dry run: 3 tables,
checks 4 of 4 passed"), each table it made as a small grid, each check, and
any error with its statement. A proposal whose dry run failed shows the
failure first, and **Approve and run** stays off: the agent proposes again,
and the newer request is the one to approve.

Only `admin` approves. An analyst sees their own requests; an admin sees all
of them. The hosted MCP connector refuses Python: a chat cannot send code.

The API: `POST /api/code-requests` (`{files: {path: text}, note}`),
`GET /api/code-requests[/<id>]`, and `POST /api/code-requests/<id>/approve`
or `/reject` (`{note}`). Each request is stored under
`.tracebi/requests/<id>/` with a row in the run store.

## Or sync from git with a webhook

When changes reach the library by pull request, review them there instead.

1. Make the workspace, or a library folder, a git checkout on the server.
2. Set `TRACEBI_LIBRARY_SYNC_SECRET`.
3. Point the repository's push webhook at `POST /api/library/sync`. On GitHub,
   use content type `application/json` and the secret as the webhook secret
   (the server checks `X-Hub-Signature-256`). Other senders put the secret in
   `X-TraceBi-Sync-Token`.

The endpoint runs `git pull --ff-only` on each checkout, registers new
reports, models and pipelines, and reloads any pipeline file that changed. It
sits outside the app's sign-in because a webhook cannot sign in. Without the
secret set, the endpoint does not exist.

## If it does not work

| You see | Likely cause |
| --- | --- |
| `not signed in to …` | Run `tracebi login --server <url>` first. |
| `… is not something a server takes` | A data file, or a path outside the folders above. |
| `→ 403` on push | Your role is `viewer`. Pushing needs `analyst`. |
| A request approved, its run `failed` | The transform failed on the server's data or secrets. The run's log is on the model's **Runs** page. |
| Sync answers `401` | The signature or token does not match `TRACEBI_LIBRARY_SYNC_SECRET`. |

## Next

- Draft from a chat instead: [[connect-chatgpt-and-claude]]
- Control who may publish where: [[folder-yaml]]
