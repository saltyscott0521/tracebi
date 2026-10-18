### Changed — Review is one page: what needs attention, drafts, then checking a file

- `/review` has three sections, in the order a person acts on them:
  1. **Needs attention**, newest first, one row each: its chip (the verdict,
     or Refresh failed / Failed / Error / Refused / Empty / Publish request /
     Waiting), what, why, when, and what to do. It lists a refresh whose steps
     failed (one row per pipeline, with the error the run store recorded), the
     newest run of any other report or pipeline when it did not succeed,
     builds that need a look or do not reproduce (source changed, data drift,
     stale checks; the same `verdictOf` rule as everywhere), review notes and
     sink checks as before, publish requests the person may decide (Decide
     opens Approve and publish / Decline with a reason in place), their own
     requests ("Waiting on <folder>'s approvers"), and pending code requests
     (an admin reviews the files in place; the one who pushed sees "Waiting on
     an admin"). "All history →" leads to History. Empty: "Nothing needs
     attention."
  2. **Drafts**: the person's own first; an admin who is signed in may switch
     between Mine and Everyone's (with no sign-in, every draft is shown). Each
     row: the Draft chip, the draft's path, Report or Model, by whom, whether it
     differs from the published one, when it changed, Open. The empty state is
     written for a person, with `start_draft`, `write_draft_file` and
     `tracebi push` under "For your agent". Requests already decided are
     folded under "Requests". A viewer is told drafts need the analyst role.
  3. **Verify a file**: "Check a report file you were sent" and a small drop
     zone that opens into the Verify page's zone when pointed at, clicked or
     dragged over, with the same result. On a phone it is a button that opens
     the file picker. `/verify` keeps its full page.
- `/drafts` lands on `/review#drafts`. A draft's page keeps its address and
  says Review › Drafts above its name; deleting a draft returns to Review.
- The Drafts page's separate "Publish requests" and "Code requests" cards and
  the Review links strip above it are gone: what waits is under Needs
  attention, what was decided under Requests.
