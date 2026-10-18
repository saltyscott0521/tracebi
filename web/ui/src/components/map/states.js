import { VERDICT_LABEL, needsAction, verdictOf } from '../../verdict'

// What a node says when it is not fine. A state is `{ tone, label }`: the label
// leads with a glyph so the state never rests on colour alone. Green is not a
// state here: a fine node says nothing.
//
//   ✕  bad   (red)     it failed, or its numbers do not reproduce
//   △  warn  (amber)   it needs a look
//   ○  ghost (dashed)  it has not been built

export const NEVER = { tone: 'ghost', label: '○ Never built' }

/** "2 min ago", "3 h ago", "2 d ago", else "on Oct 3"; null when unreadable. */
export function ago(iso, now = Date.now()) {
  const t = Date.parse(iso)
  if (!iso || Number.isNaN(t)) return null
  const seconds = Math.max(0, Math.floor((now - t) / 1000))
  const minutes = Math.floor(seconds / 60)
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes} min ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours} h ago`
  const days = Math.floor(hours / 24)
  if (days < 7) return `${days} d ago`
  return `on ${new Date(t).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}`
}

/**
 * A report: never built, or the verdict on its last build (verdict.js, so the
 * words are the Reports page's). Reproduces and Not checked are quiet. *report*
 * (its GET /api/reports row) lets files changed since the build need a look.
 * `verdict` is the state its node shows as the verdict chip.
 */
export function reportState(build, report) {
  if (!build) return { ...NEVER, verdict: 'never-built' }
  const v = verdictOf({ report, build })
  if (!needsAction(v)) return null
  const bad = v.state === 'does-not-reproduce'
  return { tone: bad ? 'bad' : 'warn', label: `${bad ? '✕' : '△'} ${VERDICT_LABEL[v.state]}`, detail: v.detail, verdict: v.state }
}

/**
 * A pipeline's transform: failed when its last run did. A pipeline with no
 * step named `transform` (a hand-built one) fails when any of its layers did.
 */
export function transformState(pipeline) {
  const layers = pipeline?.layers || []
  const own = layers.find(l => l.name === 'transform')
  const failed = (own ? [own] : layers).find(l => l.last_status === 'failed')
  if (!failed) return null
  const when = ago(failed.last_run)
  return { tone: 'bad', label: when ? `✕ Failed ${when}` : '✕ Failed' }
}

// What the sink said about a table. `satisfied` is fine and says nothing.
const CONTRACT = {
  stale: { tone: 'warn', label: '△ Changed since checked', detail: 'It changed after its checks last passed.' },
  no_contract: { tone: 'warn', label: '△ No checks', detail: 'No checks cover it.' },
}

/** A warehouse file: the worst of its tables (stale, then none), else fine. */
export function warehouseState(data) {
  if (!data?.supported || data.error) return null
  if (!data.exists) return NEVER
  const status = (data.tables || []).map(t => t.contract?.status || 'no_contract')
  return CONTRACT[status.includes('stale') ? 'stale' : status.includes('no_contract') ? 'no_contract' : ''] || null
}

/** One table of a warehouse, by its physical name: its rows and its state. */
export function tableLive(data, source) {
  if (!data?.supported || data.error) return {}
  if (!data.exists) return { state: NEVER }
  const table = (data.tables || []).find(t => t.name === source)
  if (!table) return { state: NEVER }
  return { rows: table.rows, state: CONTRACT[table.contract?.status || 'no_contract'] || null }
}

/** `✕ Failed 2 min ago` -> the glyph and the words, so the glyph can be hidden from a reader. */
export function splitGlyph(label) {
  const m = /^([✕△○])\s+(.*)$/.exec(label || '')
  return m ? { glyph: m[1], words: m[2] } : { glyph: '', words: label || '' }
}
