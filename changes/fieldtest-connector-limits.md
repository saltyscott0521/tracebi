### Changed — remote drafts say what they can hold, and why

- `list_models` and `describe_model` report `draftable` per model, with a
  `draft_note` when false. It is the decision `start_draft` makes, so the
  listing and the refusal cannot disagree. A Python model is not draftable.
- `start_draft(models, …)` refuses a Python model of that name, with or without
  `from_published`, since such a draft could never publish.
- A disallowed draft file names the reason: code would run on the server with
  its secrets, so code comes only through a laptop and review. The agent guides
  and the vocabulary say the same.
