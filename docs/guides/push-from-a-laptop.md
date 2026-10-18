# Push from a laptop

**Build and preview on your own machine, then send the files to the server:
`tracebi push`. Reports and declarative models land in your drafts. Python
goes to an admin, who reads the diff and approves it before it runs.**

This is for analysts who work in a local project (often with an agent such as
Claude Code), and for the admin who approves code on the server. Sign in first
([[sign-in]]).

---

## What goes where

What a file can do on the server decides where it lands:

| You push | It becomes | Who decides |
| --- | --- | --- |
| A report package (`reports/<model>/<name>/`) | Your draft of that report | You publish it in the app, as any draft |
| `models/<name>.yaml` or `.json` | Your draft of that model | You publish it; the impact check runs as usual |
| `transforms/*.py` or `.ipynb`, `pipelines/*`, `models/<name>.py`, `connections/*.yaml`, a package's `report.py` | One **code request** | An admin approves or declines it |

Data never goes. The server runs the transform with its own secrets and builds
its own warehouse; the sink contract checks what landed there. A path outside
the table above (`inputs/orders.csv`, `data/warehouse.duckdb`) is refused.

Connections count as code because they decide which of the server's secrets a
transform reads.

## Push

```bash
tracebi push reports/sales_model/weekly models/sales_model.yaml --server https://bi.example.com
tracebi push transforms/sales_transform.py --server https://bi.example.com \
    --note "Drop test accounts before the sink"
```

Paths are files, package folders, or folders of them, inside the project you
are in. A code request needs `--note`: the admin reads it beside the diff.
Nothing is sent when a path is refused or the note is missing.

The command prints each draft's page and the request's id. A draft that already
held a file you did not push says so; delete it in the app if it should go.

## Approve code (admin)

**Review** lists a pending code request under **Needs attention**. **Review** on its row shows every file with
its diff against what is published (a new file says so). Then:

- **Approve and run** copies the files in, keeps what they replace under
  `.tracebi/history/code/<version>/`, and runs once every pipeline the request
  touches: the pipelines it holds, and each `pipelines/*.yaml` whose
  `transform` it changes. The run uses the server's secrets, the sink contract
  checks what landed, and the request records the run and its outcome.
- **Decline** needs a reason; the person who asked sees it.

Only `admin` approves. An analyst sees their own requests, an admin everyone's.
Over the hosted MCP connector, Python is refused: a chat cannot send code.

The API is `POST /api/code-requests` (`{files: {path: text}, note}`),
`GET /api/code-requests[/<id>]`, and `POST /api/code-requests/<id>/approve`
or `/reject` (`{note}`). Each request is stored under
`.tracebi/requests/<id>/` with a row in the run store.

## Or: a git checkout and a webhook

When changes reach the library by pull request, review happens there. Make the
project (or a library folder) a git checkout on the server, set
`TRACEBI_LIBRARY_SYNC_SECRET`, and point the repository's push webhook at
`POST /api/library/sync`:

- GitHub: content type `application/json`, the secret as the webhook secret
  (the server checks `X-Hub-Signature-256`).
- Anything else: send the secret itself in `X-TraceBi-Sync-Token`.

The endpoint fast-forwards each checkout (`git pull --ff-only`), registers new
reports, models and pipelines, and reloads any pipeline file that changed. It
sits outside the app's sign-in because a webhook has none; without the secret
set it does not exist.

## If it does not work

| You see | Likely cause |
| --- | --- |
| `not signed in to …` | Run `tracebi login --server <url>` first. |
| `… is not something a server takes` | A data file, or a path outside the folders above. |
| `→ 403` on push | Your role is `viewer`; pushing needs `analyst`. |
| A request approved, its run `failed` | The transform failed on the server's data or secrets. The run's log is on the model's **Runs** page. |
| Sync answers `401` | The signature or token does not match `TRACEBI_LIBRARY_SYNC_SECRET`. |

## Related

- [[sign-in]] — `tracebi login`, and the roles
- [[connect-chatgpt-and-claude]] — drafting from a chat instead
