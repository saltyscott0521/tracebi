import { stamp } from './when'

// One trust vocabulary. Every page that says whether a report's numbers still
// hold derives it here, so the library row, the report header, History and
// the counts cannot disagree. The words are the artifact's chip (tracebi.js
// _VERDICTS): Reproduces (green), Needs a look (amber: the source or the data
// changed since the build, or its checks are stale), Does not reproduce (red),
// Not checked (neutral); plus Draft and Never built where the app needs them,
// and Local: the reader's selection, recomputed in the page itself (the
// report's own chip says the same).
// Only a re-check that came back `reproduces` is ever green.

export const VERDICT_LABEL = {
  reproduces: 'Reproduces',
  'needs-a-look': 'Needs a look',
  'does-not-reproduce': 'Does not reproduce',
  'not-checked': 'Not checked',
  draft: 'Draft',
  'never-built': 'Never built',
  local: 'Local',
}

/** What the page's own Local chip says (tracebi.js _VERDICTS.local). */
export const LOCAL_DETAIL = 'Recomputed on this page from the embedded data'


// What GET /api/desk's re-check (tracebi/verify.py) said of a build. A verdict
// this page does not know needs a look: the bias is toward loud.
const CHECKED = {
  reproduces: ['reproduces', 'Re-running every query gave the numbers this build carries.'],
  source_drift: ['needs-a-look', 'The data changed since it was built. Rebuild to refresh it.'],
  not_reproduced: ['does-not-reproduce', 'Re-running its queries gave different numbers, for a reason not yet known.'],
  unverifiable: ['not-checked', 'Its numbers come from report.py, so they cannot be re-run.'],
  nothing_to_verify: ['not-checked', 'Its last build recorded no numbers to check.'],
  refused_newer_schema: ['not-checked', 'Built by a newer TraceBi than this server runs, so it was not re-run.'],
  error: ['needs-a-look', 'The re-check could not run.'],
}


/**
 * A re-check's verdict string (a desk build, a scheduled run) as `{ state,
 * detail }`. *said* is what the check itself reported (`detail` on a desk
 * row): it explains an error or a verdict this page does not know.
 */
export function checkedVerdict(verdict, said) {
  if (verdict === 'error' && said) return { state: 'needs-a-look', detail: `The re-check could not run: ${said}` }
  const [state, words] = CHECKED[verdict] || ['needs-a-look', said || 'Its last build needs a look.']
  return { state, detail: words }
}

// The report's files (report.json, template.html, app.jsx, or its spec) were
// saved after the build. The build time is whole seconds, so a save in the
// second it was written is not "after".
function sourceChangedSince(report, build) {
  const changed = Date.parse(report?.last_change)
  const built = Date.parse(build?.built_at)
  return changed > built + 1000
}

/**
 * The verdict on a report's last build. *build* is its row in GET /api/desk
 * `builds` (none: never built); *report* its row in GET /api/reports (for
 * `last_change`); *contracts* its receipt's `transform_contracts`, when the
 * build is open. Call it only once the desk has answered: before that nothing
 * is claimed. Returns `{ state, detail }`.
 *
 *   never built                                  → never-built
 *   re-check did not reproduce                   → does-not-reproduce
 *   files saved since the build                  → needs-a-look ("Source changed …")
 *   data changed, re-check could not run, or a
 *   verdict this page does not know              → needs-a-look
 *   a table it reads is past its sink checks     → needs-a-look ("Checks stale")
 *   python-derived, nothing recorded, newer build → not-checked
 *   re-check reproduces                          → reproduces
 */
export function verdictOf({ report, build, contracts, checkedAt }) {
  if (!build) return { state: 'never-built', detail: 'It has not been built yet.' }
  const v = checkedVerdict(build.verdict, build.detail)
  if (v.state === 'does-not-reproduce') return v
  if (sourceChangedSince(report, build)) {
    return { state: 'needs-a-look', detail: `Source changed since this build: its files were saved ${stamp(report.last_change)}, the build is from ${stamp(build.built_at)}.` }
  }
  if (v.state !== 'reproduces') return v
  const stale = Object.entries(contracts || {}).filter(([, c]) => c?.status === 'stale').map(([t]) => t)
  if (stale.length) {
    return { state: 'needs-a-look', detail: `Checks stale: ${stale.join(', ')} changed since the sink last satisfied its contract.` }
  }
  return checkedAt ? { ...v, detail: `${v.detail} Checked ${stamp(checkedAt)}.` } : v
}

/** The verdicts that ask a person to act. */
export const needsAction = v => v?.state === 'needs-a-look' || v?.state === 'does-not-reproduce'
