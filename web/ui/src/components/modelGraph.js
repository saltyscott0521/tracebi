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

// The browser's node: a fixed width, a header band, then one row per column.
// A wide table shows its keys and measures first and the rest behind "+N more".
export const NODE_W = 260
export const MAX_COLUMNS = 12
export const ROW_H = 24
export const HEAD_H = 36
const GAP_X = 120         // room between columns for a join's steps and its crow's feet
const GAP_Y = 40
const GROUP_GAP = 160     // between the separate stars of the warehouse

const tableOf = (data, name) => (data.tables || []).find(t => t.name === name)

/** A column's kind, from its engine type: number, text, date, bool or other. */
export function typeKind(type) {
  const t = String(type || '').toUpperCase()
  if (/INT|DOUBLE|FLOAT|DECIMAL|NUMERIC|REAL/.test(t)) return 'number'
  if (/DATE|TIME/.test(t)) return 'date'
  if (/BOOL/.test(t)) return 'bool'
  if (/CHAR|TEXT|STRING|UUID/.test(t)) return 'text'
  return 'other'
}

/** A node's drawn height, for the layout: its band, its shown rows, "+N more". */
export const nodeHeight = n => {
  const shown = Math.min(n.columns.length, MAX_COLUMNS) || 1
  return HEAD_H + ROW_H * shown + (n.columns.length > MAX_COLUMNS ? ROW_H : 0) + 8
}

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
    const pk = new Set(edges.filter(e => e.to === t.name).map(e => e.toKey))
    dims.filter(d => d.table === t.name).forEach(d => pk.add(d.key))
    const fk = new Set(edges.filter(e => e.from === t.name).map(e => e.fromKey))
    const measure = new Set(facts.filter(f => f.table === t.name).flatMap(f => f.measures || []))
    const flag = c => (pk.has(c) ? 'PK' : fk.has(c) ? 'FK' : measure.has(c) ? 'Σ' : '')
    const all = (t.columns || []).map(c => ({ name: c.name, type: c.dtype || c.type || '' }))
    return {
      name: t.name, role: roleOf(t.name), connector: t.connector, source: t.source,
      columns: orderColumns(all.length ? all : [...pk, ...fk, ...measure].map(n => ({ name: n, type: '' })), flag),
    }
  })
  return { nodes, edges }
}

// Keys first, then foreign keys, then measures, the rest in table order: a
// wide table's interesting columns are never the ones behind "+N more".
function orderColumns(columns, flag) {
  const rank = f => ({ PK: 0, FK: 1, 'Σ': 2, '': 3 })[f]
  return columns.map((c, i) => [{ ...c, flag: flag(c.name) }, i])
    .sort((a, b) => rank(a[0].flag) - rank(b[0].flag) || a[1] - b[1]).map(([c]) => c)
}

// ── The browser's scope: one model, or a whole warehouse ───────────────────
//
// Both pages hand DataBrowser the same shape: tables ({id, name, role,
// connector, source, columns, group}), edges between ids, and the tree's
// groups ({id, label, tables}). Numbers (rows, checks) are read per table from
// the table API or the warehouse listing; nothing here counts anything.

/** A model's tables, grouped Facts (a bridge among them), Dimensions, Other. */
export function modelSchema(data) {
  const g = buildModelGraph(data)
  const group = role => (role === 'fact' || role === 'bridge' ? 'facts' : role === 'dimension' ? 'dimensions' : 'other')
  const tables = g.nodes.map(n => ({ ...n, id: n.name, group: group(n.role) }))
  const groups = [['facts', 'Facts'], ['dimensions', 'Dimensions'], ['other', 'Other']]
    .map(([id, label]) => ({ id, label, tables: tables.filter(t => t.group === id).map(t => t.id) }))
    .filter(gr => gr.tables.length)
  return { tables, edges: g.edges, groups }
}

/**
 * Every table of *warehouses* (/api/warehouse's list), grouped by the
 * transform that wrote it (Not written by a transform last), with the joins
 * every model in *models* (/api/models/{name} payloads) declares over them,
 * by the tables' stored names. *extra* holds `{"<warehouse>.<table>":
 * [{name, type}]}` for a table no model reads (from the table API). *only*
 * keeps the tables that one model reads.
 */
export function warehouseSchema(warehouses, models, extra = {}, only = '') {
  const many = warehouses.length > 1
  const idOf = (w, t) => (many ? `${w}.${t}` : t)
  const roles = {}
  const known = {}
  const edges = []
  models.forEach(m => {
    const g = buildModelGraph(m)
    const stored = Object.fromEntries(g.nodes.map(n => [n.name, n]))
    g.nodes.forEach(n => {
      const id = idOf(n.connector, n.source)
      ;(roles[id] ||= new Set()).add(n.role)
      if (!known[id] && n.columns.some(c => c.type)) known[id] = n.columns
    })
    g.edges.forEach(e => {
      const a = stored[e.from]
      const b = stored[e.to]
      if (!a || !b) return
      const from = idOf(a.connector, a.source)
      const to = idOf(b.connector, b.source)
      const id = `${from}.${e.fromKey}>${to}.${e.toKey}`
      const hit = edges.find(x => x.id === id)
      if (hit) { if (!hit.models.includes(m.name)) hit.models.push(m.name) } else edges.push({ ...e, id, from, to, models: [m.name] })
    })
  })
  const roleOf = id => {
    const r = roles[id]
    if (!r) return 'table'
    if (r.has('bridge') || (r.has('fact') && r.has('dimension'))) return 'bridge'
    return r.has('fact') ? 'fact' : r.has('dimension') ? 'dimension' : 'table'
  }
  const tables = []
  const groups = []
  warehouses.forEach(w => {
    const shown = (w.tables || []).filter(t => !only || (t.read_by || []).includes(only))
    const groupOf = t => `${w.name}:${t.written_by?.contract || ''}`
    shown.forEach(t => {
      const id = idOf(w.name, t.name)
      const cols = known[id] || (extra[`${w.name}.${t.name}`] || []).map(c => ({ name: c.name, type: c.type }))
      const mine = edges.filter(e => e.from === id || e.to === id)
      const flag = c => (mine.some(e => e.to === id && e.toKey === c) ? 'PK'
        : mine.some(e => e.from === id && e.fromKey === c) ? 'FK'
          : (known[id] || []).find(x => x.name === c)?.flag || '')
      tables.push({
        id, name: t.name, role: roleOf(id), connector: w.name, source: t.name,
        columns: orderColumns(cols.map(c => ({ name: c.name, type: c.type })), flag),
        listed: t, group: groupOf(t),
      })
    })
    ;(w.writers || []).forEach(wr => {
      const own = shown.filter(t => t.written_by?.contract === wr.contract).map(t => idOf(w.name, t.name))
      if (own.length) groups.push({ id: `${w.name}:${wr.contract}`, label: wr.transform || wr.contract, writer: wr, warehouse: w, tables: own })
    })
    const loose = shown.filter(t => !t.written_by?.contract).map(t => idOf(w.name, t.name))
    if (loose.length) groups.push({ id: `${w.name}:`, label: 'Not written by a transform', warehouse: w, tables: loose })
  })
  const ids = new Set(tables.map(t => t.id))
  return { tables, edges: edges.filter(e => ids.has(e.from) && ids.has(e.to)), groups }
}

// ── Layout ──────────────────────────────────────────────────────────────────
//
// Deterministic and layered: each connected star is laid out on its own, its
// facts in one column and its dimensions beside them, each as near as it can
// sit to the middle of the facts it joins (so one shared by two facts sits
// between them). Up to four dimensions sit on the left of the facts; more are
// shared out left and right by degree. Stars, then the tables with no joins,
// are packed in rows. Every column is stacked with a 40 px gutter, so nothing
// overlaps.

/** `{[id]: {x, y}}` for *tables* (each with `id`, `role`, `columns`) joined by *edges*. */
export function layoutSchema(tables, edges) {
  const byId = Object.fromEntries(tables.map(t => [t.id, t]))
  const h = Object.fromEntries(tables.map(t => [t.id, nodeHeight(t)]))
  const parent = Object.fromEntries(tables.map(t => [t.id, t.id]))
  const find = x => (parent[x] === x ? x : (parent[x] = find(parent[x])))
  edges.forEach(e => { if (byId[e.from] && byId[e.to]) parent[find(e.from)] = find(e.to) })
  const parts = []
  const partOf = {}
  tables.forEach(t => {
    const root = find(t.id)
    if (!(root in partOf)) { partOf[root] = parts.length; parts.push([]) }
    parts[partOf[root]].push(t.id)
  })
  const boxes = parts.map(ids => (ids.length === 1
    ? { pos: { [ids[0]]: { x: 0, y: 0 } }, w: NODE_W, h: h[ids[0]], n: 1 }
    : star(ids, byId, edges, h)))
  // Stars first, the largest first; then the tables with no joins, in order.
  const order = boxes.map((_, i) => i).sort((a, b) => boxes[b].n - boxes[a].n || a - b)
  const limit = Math.max(1400, ...boxes.map(b => b.w))
  const pos = {}
  let x = 0
  let y = 0
  let rowH = 0
  let lone = false
  order.forEach(i => {
    const b = boxes[i]
    // The tables with no joins start a row of their own.
    if (x > 0 && (x + b.w > limit || (b.n === 1 && !lone))) { x = 0; y += rowH + GROUP_GAP; rowH = 0 }
    lone = b.n === 1
    Object.entries(b.pos).forEach(([id, p]) => { pos[id] = { x: x + p.x, y: y + p.y } })
    x += b.w + (lone ? GAP_Y : GROUP_GAP)
    rowH = Math.max(rowH, b.h)
  })
  return pos
}

function star(ids, byId, edges, h) {
  const inPart = new Set(ids)
  const own = edges.filter(e => inPart.has(e.from) && inPart.has(e.to))
  const centre = ids.filter(id => ['fact', 'bridge'].includes(byId[id].role) || own.some(e => e.from === id))
  const sides = ids.filter(id => !centre.includes(id))
  let at = 0
  const fy = {}
  centre.forEach(id => { fy[id] = at; at += h[id] + GAP_Y })
  const degree = id => own.filter(e => e.to === id || e.from === id).length
  const target = id => {
    const fs = own.filter(e => e.to === id && e.from in fy).map(e => fy[e.from] + h[e.from] / 2)
    return fs.length ? fs.reduce((s, v) => s + v, 0) / fs.length : 0
  }
  const left = []
  const right = []
  if (sides.length <= 4) left.push(...sides)
  else {
    let lh = 0
    let rh = 0
    ;[...sides].sort((a, b) => degree(b) - degree(a) || ids.indexOf(a) - ids.indexOf(b)).forEach(id => {
      if (lh <= rh) { left.push(id); lh += h[id] + GAP_Y } else { right.push(id); rh += h[id] + GAP_Y }
    })
  }
  const cx = left.length ? NODE_W + GAP_X : 0
  const pos = {}
  const place = (list, x) => {
    let floor = -Infinity
    ;[...list].sort((a, b) => target(a) - target(b) || ids.indexOf(a) - ids.indexOf(b)).forEach(id => {
      const y = Math.max(floor, target(id) - h[id] / 2)
      pos[id] = { x, y }
      floor = y + h[id] + GAP_Y
    })
  }
  place(left, 0)
  centre.forEach(id => { pos[id] = { x: cx, y: fy[id] } })
  place(right, cx + NODE_W + GAP_X)
  const top = Math.min(...Object.values(pos).map(p => p.y))
  Object.values(pos).forEach(p => { p.y -= top })
  const cols = 1 + (left.length ? 1 : 0) + (right.length ? 1 : 0)
  return {
    pos, w: cols * NODE_W + (cols - 1) * GAP_X, n: ids.length,
    h: Math.max(...ids.map(id => pos[id].y + h[id])),
  }
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

export { tableOf }
