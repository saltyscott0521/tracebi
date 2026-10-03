### Added — Alerts when a scheduled report fails, is refused, or is empty

- A `schedule` block can name one `"owner"` email. When a run ends `failed`,
  `refused`, or `empty`, that address gets a plain-text email and the
  people in `to` do not get the report.
- A run is `empty` when a binding a figure uses came back with no rows.
  The record names those bindings. A binding no figure uses does not count.
- An alert that cannot be sent is written on the run as `alert.error`.
  The run's status stays what it was. `--no-send` records the alert and
  does not email it. With no `owner`, nothing is alerted.
