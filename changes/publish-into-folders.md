### Added — publish a draft into a folder, or ask to

- A report draft publishes to a chosen `folder` (a library path, created if
  needed; `folder` in the publish body and the `publish_draft` tool). With
  Publish there it is published as before, and the history
  (`.tracebi/history/reports/<path>/publishes.jsonl`) now records who published
  and when.
- With only Build on the folder, publishing is a **request**
  (`status: requested`, HTTP 202), stored as a file under
  `drafts/_requests/` with a snapshot of the draft. Someone with Publish
  there approves it (`POST /api/publish-requests/{id}/approve`, or the MCP tool
  `decide_publish_request`) or rejects it with a note; the history records who
  asked, who approved and when. Permission is checked when they decide, so a
  requester cannot approve their own. `GET /api/publish-requests` and
  `list_publish_requests` list them. The gateway now has 22 tools.
- `_folder.yaml` takes `accepts: labelled` (default) or `accepts: checkable`;
  the latter refuses, at publish and at request, a report with a `report.py` or
  a figure no query can re-run. An unknown value is a malformed file.
- With no `_folder.yaml` anywhere, nothing changes.
