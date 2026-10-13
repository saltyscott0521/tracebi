### Added — My published, and the folders in the app

- Every signed-in person has a folder of their own, `my-published/<sign-in
  name>` (**My published** in the app), where they hold Publish: publishing
  there is direct, and the report is shareable and schedulable without the
  shared folders. Others see it only if a `_folder.yaml` inside it grants View.
  With no sign-in identity (the shared token, the command line, an app without
  sign-in) there is no personal folder and `GET /api/folders` says so.
- The Reports list is the folder tree: each folder says what you may do there
  and each report row shows its owner (last publisher), type, schedule and last
  run. People with Manage, and the owner of a personal folder, see a folder's
  permissions, read-only: editing is the `_folder.yaml` file for now.
- A draft's Publish step offers a destination (`GET
  /api/drafts/.../destinations`) and says whether it publishes directly or
  sends a request. Approvers see pending requests under Drafts and approve, or
  decline with a reason.
- New: `GET /api/folders`; `/api/reports` rows carry `folder` and `owner`;
  publish-request rows carry `can_decide`.
- With no `_folder.yaml` anywhere, publishing and access are unchanged.
