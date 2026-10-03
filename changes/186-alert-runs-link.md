### Added — Owner schedule alerts link to the Runs page

- When `TRACEBI_PUBLIC_URL` is set (no trailing slash), an owner alert
  includes `See the run:` with a link to that report on the Runs page.
  Unset, the alert text is unchanged.
- When `TRACEBI_SLACK_WEBHOOK` is set, the same alert text is posted
  there. A failed ping is `alert.slack_error` and does not change the
  run status, or whether the email was sent.
