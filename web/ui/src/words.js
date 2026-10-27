// The app's words for the facts Data repeats: when the data was refreshed,
// what its checks say, where a warehouse is kept, whether a connection is
// reachable here, and a transform's form. One function per fact, so every page
// that says it says it the same way; a sentence may add words around these,
// never replace them. Pure: no React, no fetching.

import { ago } from './when'
import { count } from './format'

/**
 * When the data was last refreshed, as `{text, kind, at, ago}`.
 *
 * *facts*: `pipeline` (false when no pipeline refreshes it), `running`,
 * `failedAt` (the last run failed, then), `ranAt` (the last run succeeded,
 * then) and `writtenAt` (when the sink certificate says the tables were
 * written). A run outside the app (run_workflow.py, `tracebi run-transform`)
 * leaves no run here, only the certificate, so that is said instead of "not
 * refreshed". *kind* is `running` · `failed` · `refreshed` · `outside` ·
 * `never` · `none`; *ago* is the age alone, for a column that prints only that.
 */
export function refreshWords({ pipeline = true, running, failedAt, ranAt, writtenAt } = {}) {
  if (running) return { text: 'Running now', kind: 'running', at: null, ago: null }
  if (failedAt) return { text: `Refresh failed ${ago(failedAt)}`, kind: 'failed', at: failedAt, ago: ago(failedAt) }
  if (ranAt) return { text: `Refreshed ${ago(ranAt)}`, kind: 'refreshed', at: ranAt, ago: ago(ranAt) }
  if (writtenAt) {
    return { text: `Written ${ago(writtenAt)} · outside the app`, kind: 'outside', at: writtenAt, ago: ago(writtenAt) }
  }
  return pipeline
    ? { text: 'Not refreshed yet', kind: 'never', at: null, ago: null }
    : { text: 'No refresh pipeline', kind: 'none', at: null, ago: null }
}

/**
 * A pipeline's refresh, from its transform step (a model pipeline's own
 * step; any other pipeline's first stands in for it) and *writtenAt*, the
 * certificate's time. No *pipeline*: what the certificate says, else none.
 */
export function pipelineRefresh(pipeline, writtenAt) {
  if (!pipeline) return refreshWords({ pipeline: false, writtenAt })
  const layers = pipeline.layers || []
  const step = layers.find(l => l.name === 'transform') || layers[0]
  return refreshWords({
    running: step?.last_status === 'running',
    failedAt: step?.last_status === 'failed' ? step.last_run : null,
    ranAt: step?.last_run,
    writtenAt,
  })
}

const CHECKS = {
  satisfied: { text: 'Checks passed', tone: '', title: 'The sink satisfied its contract, and the table is unchanged since.' },
  stale: { text: 'Changed since checked', tone: 'warn', title: 'The table changed after its checks last passed: they no longer describe this data.' },
  no_contract: { text: 'No checks', tone: 'none', title: 'No checks cover this table.' },
}

/**
 * What a sink contract's checks say, as the chip's `{text, tone, title}`:
 * `Checks passed` · `Changed since checked` · `No checks`, or `N checks
 * failed` when *contract*.failed counts the checks a run's sink failed (the
 * sink raises and records no certificate, so the run says it). Never
 * "verified", and it colours nothing else.
 */
export function checksWords(contract) {
  const failed = contract?.failed
  if (failed) {
    return { text: `${count(failed, 'check')} failed`, tone: 'bad', title: 'The last run wrote its tables, then these checks failed.' }
  }
  return CHECKS[contract?.status] || CHECKS.no_contract
}

const TIERS = { file: 'DuckDB file', object: 'Parquet on object storage', remote: 'Remote database' }

/** A warehouse's tier (tracebi.yaml `warehouse: tier:`) in words; an unknown one as written. */
export const tierWords = tier => TIERS[tier] || tier

/**
 * Whether a connection is reachable here, from its tables' answer (GET
 * /api/connectors/{name}/tables): `{connected, short, text}`. *short* is the
 * chip's word; *text* names the variable to set, else the reason.
 */
export function reachWords(reach) {
  if (reach?.connected) return { connected: true, short: 'Connected', text: 'Connected' }
  const why = reach?.variable ? `set ${reach.variable}` : reach?.reason
  return { connected: false, short: 'Not connected here', text: why ? `Not connected here · ${why}` : 'Not connected here' }
}

const MOVED = { written: 'Written', built: 'Built', changed: 'Changed', defined: 'Defined', snapshot: 'Snapshot read' }

/**
 * When a piece of the project last moved (the graph's passport `moved`:
 * `{at, how}`, how one of written · built · changed · defined · snapshot ·
 * never), as the map's Last moved row says it: "Written 2 h ago", "Built Oct
 * 23 · 11:48". *kind* is the node's: a report never built says so, anything
 * else that never moved here is "Not refreshed yet".
 */
export function movedWords(moved, kind) {
  if (!moved || moved.how === 'never') return kind === 'report' ? 'Never built' : 'Not refreshed yet'
  const word = MOVED[moved.how] || moved.how
  const when = ago(moved.at)
  return when ? `${word} ${when}` : word
}

/** A transform's form (the API's sql | python | notebook) as its chip says it. */
export const FORM_LABEL = { sql: 'SQL', python: 'Python', notebook: 'Notebook' }
