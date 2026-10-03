### Added — Slack file delivery for a scheduled report

- When `TRACEBI_SLACK_BOT_TOKEN` and `TRACEBI_SLACK_CHANNEL` are both set, a successful scheduled send uploads the HTML and the manifest to that channel. The message names the report, when it was rendered, the verify verdict, and up to five headline value figures.
- `TRACEBI_SLACK_WEBHOOK` stays a text ping. An incoming webhook cannot upload a file.
- A failed upload is recorded on the run as `delivery.slack.error` and is not retried. `--no-send` records the intent and does not call Slack.
