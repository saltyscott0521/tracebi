// The data-model diagram's shape, built from what a model DECLARES.
//
// A star schema states its joins on the fact (`add_fact(..., foreign_keys=
// {"dim_fund": "fund_id"})`), not as `add_relationship` calls, so a diagram
// drawn from relationships alone was empty for the recommended way to write a
// model. Here the declared facts and dimensions give each table its role and
// each fact its many-to-one edges; explicit relationships are added on top.
//
// Pure functions of the /api/models/{name} payload, so the layout can be read
// and checked without a browser.

import { humanise, inSentence } from '../ask'

export const MAX_COLUMNS = 10          // a wide table shows its keys and measures first
export const ROW_H = 22
export const HEAD_H = 62
const NODE_W = 300
const COL_GAP = 120       // room for a join's label between two columns
const GAP = 44

const tableOf = (data, name) => (data.tables || []).find(t => t.name === name)

export function buildModelGraph(data) {
  const tables = data.tables || []
  const facts = data.facts || []
  const dims = data.dimensions || []
  const relationships = data.relationships || []

  const dimByName = Object.fromEntries(dims.map(d => [d.name, d]))
  const factTables = new Set(facts.map(f => f.table))
  const dimTables = new Set(dims.map(d => d.table))

  // ── edges ───────────────────────────────────────────────────────────────
  const edges = []
  const seen = new Set()
  const add = e => {
    const id = `${e.from}.${e.fromKey}>${e.to}.${e.toKey}`
    if (seen.has(id)) return
    seen.add(id)
    edges.push({ id, ...e })
  }
  facts.forEach(f => {
    Object.entries(f.foreign_keys || {}).forEach(([dimName, fromKey]) => {
      const dim = dimByName[dimName]
      if (!dim) return
      add({ from: f.table, fromKey, to: dim.table, toKey: dim.key, cardinality: 'many-to-one', declared: true })
    })
  })
  relationships.forEach(r => add({
    from: r.left_table, fromKey: r.left_key, to: r.right_table, toKey: r.right_key,
    cardinality: null, declared: false, how: r.how,
  }))

  // ── roles: declared first, then what the joins imply ────────────────────
  const referenced = new Set(edges.map(e => e.to))
  const references = new Set(edges.map(e => e.from))
  const roleOf = name => {
    if (factTables.has(name) && dimTables.has(name)) return 'bridge'
    if (factTables.has(name)) return 'fact'
    if (dimTables.has(name)) return 'dimension'
    if (referenced.has(name) && references.has(name)) return 'bridge'
    if (references.has(name)) return 'fact'
    if (referenced.has(name)) return 'dimension'
    return 'table'
  }

  // ── nodes: columns flagged as key / foreign key / measure ───────────────
  const nodes = tables.map(t => {
    const role = roleOf(t.name)
    const pk = new Set(edges.filter(e => e.to === t.name).map(e => e.toKey))
    dims.filter(d => d.table === t.name).forEach(d => pk.add(d.key))
    const fk = new Set(edges.filter(e => e.from === t.name).map(e => e.fromKey))
    const measure = new Set(facts.filter(f => f.table === t.name).flatMap(f => f.measures || []))

    const flag = c => (pk.has(c) ? 'PK' : fk.has(c) ? 'FK' : measure.has(c) ? 'Σ' : '')
    const rank = c => ({ PK: 0, FK: 1, 'Σ': 2, '': 3 })[flag(c)]
    const all = (t.columns || []).map(c => ({ name: c.name, dtype: c.dtype, flag: flag(c.name) }))
    // Keys and measures first, the rest in table order: a wide table's
    // interesting columns are never the ones cut off.
    const ordered = all.length
      ? [...all].sort((a, b) => rank(a.name) - rank(b.name))
      : [...pk, ...fk, ...measure].map(n => ({ name: n, dtype: '', flag: flag(n) }))
    const shown = ordered.slice(0, MAX_COLUMNS)
    return {
      name: t.name, role, connector: t.connector, source: t.source,
      columns: shown, hidden: ordered.length - shown.length,
      height: HEAD_H + ROW_H * (shown.length || 1) + (ordered.length > shown.length ? ROW_H : 0) + 12,
    }
  })

  const laid = layout(nodes)
  return { nodes: laid.nodes, edges, height: laid.height }
}

// Dimensions left, facts right (a bridge, both at once, in the middle), each
// column stacked and centred on the tallest. Returns the tallest column's
// height so the frame can size itself to the content.
function layout(nodes) {
  const hasBridge = nodes.some(n => n.role === 'bridge')
  const step = NODE_W + COL_GAP
  const colX = { dimension: 0, bridge: step, fact: hasBridge ? 2 * step : step, table: hasBridge ? 2 * step : step }
  const cols = {}
  nodes.forEach(n => { (cols[colX[n.role]] ||= []).push(n) })
  const heightOf = list => list.reduce((h, n) => h + n.height + GAP, -GAP)
  const tallest = Math.max(0, ...Object.values(cols).map(heightOf))
  Object.entries(cols).forEach(([x, list]) => {
    let y = (tallest - heightOf(list)) / 2
    list.forEach(n => {
      n.position = { x: Number(x), y }
      y += n.height + GAP
    })
  })
  return { nodes, height: tallest }
}

// One line saying what a measure is, in words, from what the API states about
// it: "sum of fair value", "rank by fair value, largest first", "fair value ÷
// the total". Every kind the model declares says something; an identifier reads
// as its words (`fair_value` → "fair value"), the way a report labels it.
const AGG_WORDS = {
  sum: 'sum of', count: 'count of', mean: 'average of', avg: 'average of', min: 'minimum of',
  max: 'maximum of', nunique: 'distinct count of', median: 'median of', stddev: 'standard deviation of',
}
const words = id => inSentence(humanise(id))
const exprWords = expr => String(expr)
  .replace(/[A-Za-z_][A-Za-z0-9_]*/g, w => words(w))
  .replace(/\*/g, '×').replace(/\//g, '÷').replace(/ - /g, ' − ')
const aggOf = (agg, what) => (AGG_WORDS[agg] ? `${AGG_WORDS[agg]} ${what}`
  : /^p\d+$/.test(agg || '') ? `${agg.slice(1)}th percentile of ${what}` : `${agg || 'aggregate'} of ${what}`)
const listOf = items => (items.length < 2 ? items.join('')
  : `${items.slice(0, -1).join(', ')} and ${items[items.length - 1]}`)
const units = (n, unit) => `${n} ${unit}${Number(n) === 1 ? '' : 's'}`

// A measure's own filters ({column: value | [values] | {op: value}}), as a clause.
const OP_WORDS = { eq: '=', ne: '≠', lt: '<', lte: '≤', le: '≤', gt: '>', gte: '≥', ge: '≥', in: 'is one of', not_in: 'is not one of' }
function filterWords(filters) {
  const one = (col, v) => {
    if (Array.isArray(v)) return `${words(col)} is one of ${v.join(', ')}`
    if (v && typeof v === 'object') {
      return Object.entries(v).map(([op, x]) => `${words(col)} ${OP_WORDS[op] || op} ${Array.isArray(x) ? x.join(', ') : x}`).join(' and ')
    }
    return `${words(col)} = ${v}`
  }
  const parts = Object.entries(filters || {}).map(([col, v]) => one(col, v))
  return parts.length ? `, only where ${parts.join(' and ')}` : ''
}

export function measureDefinition(m) {
  const within = (m.partition_by || []).length ? `, within each ${listOf(m.partition_by.map(words))}` : ''
  if (m.ratio) return `${words(m.ratio[0])} ÷ ${words(m.ratio[1])}`
  if (m.share) return `${words(m.share)} ÷ the total`
  if (m.kind === 'rank') return `rank by ${m.rank ? words(m.rank) : 'its measure'}, largest first${within}`
  if (m.kind === 'running') return `running total of ${m.running ? words(m.running) : 'its measure'}, largest first${within}`
  if (m.measure_expr) return exprWords(m.measure_expr)
  if (m.period_end) return `${words(m.period_end[0])} on the last ${words(m.period_end[1])} of each period`
  if (m.offset) return `${words(m.offset[0])} ${units(m.offset[2], m.offset[1])} earlier`
  if (m.growth) return `change in ${words(m.growth[0])} since ${units(m.growth[2], m.growth[1])} earlier, as a share of it`
  if (m.to_date) return `${words(m.to_date[0])}, ${m.to_date[1]} to date`
  if (m.expr) return `${aggOf(m.agg, `(${exprWords(m.expr)})`)}${filterWords(m.filters)}`
  if (m.column) return `${aggOf(m.agg, words(m.column))}${filterWords(m.filters)}`
  return ''
}

export const MEASURE_KINDS = {
  simple: 'Aggregate', expression: 'Expression', ratio: 'Ratio of totals',
  share: 'Share of total', rank: 'Rank', running: 'Running total',
  period_end: 'Period end', offset: 'Prior period', growth: 'Growth',
  to_date: 'To date',
}

export { tableOf }
