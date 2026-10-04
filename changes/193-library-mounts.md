### Library mounts

Several report roots can make up one Library. Set
`TRACEBI_LIBRARY_MOUNTS=label:/absolute/path,...` — each label is a
top-level folder, and report names are `label/relative_path`. When unset,
`TRACEBI_REPORTS_DIR` stays the single root as before.
