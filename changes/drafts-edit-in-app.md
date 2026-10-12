### Added — start and edit a draft in the app

- `POST /api/drafts` starts the signed-in person's own draft of a published
  report or declarative model (`{kind, path, from_published}`): `201` for a
  new one, `200` with the one they already have, `422` with the reason when it
  cannot be drafted (a Python model says to edit it from a laptop).
  `PUT /api/drafts/{owner}/{kind}/{path}/files/{file}` writes one draft file and
  returns the draft's new version. Both need `analyst`; the PUT is for the
  draft's owner or an admin.
- The Draft page's Files tab is editable for an analyst or admin: **Edit** opens
  a file in a monospace text box (Tab inserts two spaces, Cmd or Ctrl+S saves),
  **Save** writes it and the live preview follows, **Discard** drops the change.
  Unsaved text is marked, and Publish warns that it publishes what is saved.
- `EditAsDraft` (`web/ui/src/components/EditAsDraft.jsx`): the button that
  starts or opens a draft and goes to its page. Hidden from viewers.
