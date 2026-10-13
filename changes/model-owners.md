### Added — model owners

- A model may declare `owners`, a list of sign-in names, in its YAML/JSON file
  (or `DataModel(name, owners=[...])`). Only an owner or an admin may publish a
  change to it; anyone else is refused (HTTP 403, MCP `ok: false`) with the
  owners named, and can still draft it and read the impact check.
- The owners that count are the published model's, so a draft cannot grant
  itself ownership. A model with no owners, or a brand-new one, publishes as
  before. Names only: the session carries no group membership to match.
- The owners show on the model's page and in `info()` / `get_context`.
