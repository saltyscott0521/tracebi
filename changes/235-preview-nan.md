### Fixed — previewing a table with an empty number

A table whose first rows held an empty number (or infinity) failed to preview with
"Out of range float values are not JSON compliant". The empty cell now comes back as
`null`, the same as in an Explore result.
