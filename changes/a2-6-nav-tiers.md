### Changed — the sidebar shows what the role uses (A2-6)

- **Places by role.** `web/ui/src/nav.js` gives each entry of `PAGES` a
  `minRole` (viewer | analyst | admin), and `placesFor(role)` is the one list
  the sidebar, the phone's drawer, the report page's rail and the ⌘K palette
  draw:

  | Role | Places |
  | --- | --- |
  | viewer | Reports · Ask |
  | analyst | Reports · Ask · Review |
  | admin | Reports · Ask · Data · Review |
  | no sign-in (`/api/me` says admin) | Reports · Ask · Data · Review |
  | while `/api/me` loads | Reports · Ask |

  The role comes from `useRole()` (`api.js`, over `useMe()`): admin when the
  server names none, viewer when it cannot be read or names an unknown role.
  Help stays in the footer for everyone. ⌘K lists the same places and the
  pages inside them; a model opens Ask, not Data, for a role without Data,
  and pipelines are listed only with Data.
- **An address above the role** (a viewer at `/data` or `/review`, an analyst
  at `/data/<m>`) shows a plain page in the app's frame: "This part of the
  app is for admins." (or analysts) "You can read reports and ask questions."
  and Go to the reports (`/`). While the role loads it draws a skeleton, not
  the page. The API enforces the roles as before; this is what the app shows.
- **Review is four tabs**, each at its own address in Review's frame:
  Attention (`/review`, the Needs attention list), Drafts (`/review/drafts`;
  `/drafts` and `/review#drafts` land there), History (`/runs`) and Verify
  (`/verify`). History and Verify keep their `PAGES` entries, marked
  `parent: 'review'`, so `whereAmI` names the tab and the sidebar marks
  Review. The "All history →" link and the small Verify entry (and its
  `entry` mode in `VerifyZone`) are gone: each is a tab.
- **Get started** says who sees each place, one sentence each, and that with
  no sign-in everyone sees all four. README, `docs/reference/api-routes.md`,
  the sign-in and plain-English guides, the demo script, `ui-quality.md` and
  `ui-backlog.md` say the same.
- **Tests.** `tests/test_ui_smoke.py` follows `/drafts` to `/review/drafts`
  and gains a proxy-mode journey: a viewer sees Reports and Ask (sidebar,
  rail, ⌘K), `/data` and `/review` show the plain pages; an analyst sees
  Review's four tabs with History current at `/runs`, and `/data/<m>` is for
  admins. `scripts/ui_audit.py` seeds `/review/drafts`.
