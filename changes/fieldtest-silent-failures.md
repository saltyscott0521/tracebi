### Changed

- `preview_draft` refuses a report whose `report.json` declares a figure the template never places with `{{ figure("id") }}`, the same refusal `publish_draft` makes. Before, the preview returned `ok` and the publish then failed.
- A report spec's chart sections reject `show_values` and `ylabel`. The compiled page had no equivalent, so the values validated and then did nothing. Remove them and restyle in `style.css` / `script.js`.
- The spec validator's error for a query_model-style measure (`{"name": {"expr": ..., "agg": ...}}`) now says a spec takes `{"column": "agg"}`, for example `{"amount": "sum"}`.
- The warning for a filter on a column the model does not declare now says it is applied to the physical table and checked at execution. It no longer reads as a defect on a filter that runs.
- The agent guides' worked example shows `{{ figure("id") }}` placement in `report.json` and `template.html`.
