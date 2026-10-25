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
export const NODE_W = 248
export const MAX_COLUMNS = 12
export const ROW_H = 23
export const HEAD_H = 34
const GAP_Y = 40          // between the tables with no joins
const FACT_GAP = 80       // between two facts at a ring's centre
const RING_GAP = 56       // the least room around a table on a ring, for a join's steps and its crow's feet
const GROUP_GAP = 160     // between rings, and between two writers' facts in one ring

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
// Deterministic: each connected star is a ring. Its facts sit at the centre in
// a row (80 px apart; a writer's facts together, two writers' further apart),
// its dimensions on an ellipse around them. A dimension's place on the ring
// follows the facts it joins: one joined by the facts on the left sits on the
// left, one shared by facts on both sides sits above or below between them,
// so each join is short and none crosses another. The ellipse grows until no
// two tables overlap. Rings sit in a row (in the order their tables come, so
// the warehouse's writers keep the tree's order), then the tables with no
// joins in a row of their own. The row wraps to keep the drawing about square.

/** `{[id]: {x, y}}` for *tables* (each with `id`, `role`, `columns`, optional `group`) joined by *edges*. */
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
    : ring(ids, byId, edges, h)))
  // Rings first, in the order their tables come; then the tables with no joins.
  const order = boxes.map((_, i) => i).sort((a, b) => (boxes[a].n === 1) - (boxes[b].n === 1) || a - b)
  // A row wraps where the drawing would turn wider than it is tall, so a
  // warehouse of several rings still reads when it is fitted to the canvas.
  const limit = Math.max(Math.sqrt(boxes.reduce((s, b) => s + (b.w + GROUP_GAP) * (b.h + GROUP_GAP), 0)), ...boxes.map(b => b.w))
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

const DEG = Math.PI / 180

function ring(ids, byId, edges, h) {
  const inPart = new Set(ids)
  const own = edges.filter(e => inPart.has(e.from) && inPart.has(e.to))
  let centre = ids.filter(id => ['fact', 'bridge'].includes(byId[id].role) || own.some(e => e.from === id))
  if (!centre.length) centre = [ids[0]]
  // A writer's facts side by side; two writers' with a wider gap between them.
  const groups = [...new Set(centre.map(id => byId[id].group))]
  centre = [...centre].sort((a, b) => groups.indexOf(byId[a].group) - groups.indexOf(byId[b].group) || ids.indexOf(a) - ids.indexOf(b))
  const fx = {}
  let at = 0
  centre.forEach((id, i) => {
    if (i) at += NODE_W + (byId[id].group === byId[centre[i - 1]].group ? FACT_GAP : GROUP_GAP)
    fx[id] = at
  })
  const cx = (at + NODE_W) / 2
  const pos = {}
  centre.forEach(id => { pos[id] = { x: fx[id], y: -h[id] / 2 } })

  // Where each dimension leans: the middle of the facts it joins, from the centre.
  const sides = ids.filter(id => !(id in fx))
  const lean = Object.fromEntries(sides.map(id => {
    const xs = own.filter(e => (e.to === id && e.from in fx) || (e.from === id && e.to in fx))
      .map(e => fx[e.to === id ? e.from : e.to] + NODE_W / 2)
    return [id, xs.length ? xs.reduce((s, v) => s + v, 0) / xs.length - cx : 0]
  }))
  const byLean = [...sides].sort((a, b) => lean[a] - lean[b] || ids.indexOf(a) - ids.indexOf(b))
  const mid = byLean.filter(id => Math.abs(lean[id]) < 1)
  const top = mid.filter((_, i) => i % 2 === 0)
  const bottom = mid.filter((_, i) => i % 2 === 1).reverse()
  const right = byLean.filter(id => lean[id] >= 1)
  const left = byLean.filter(id => lean[id] <= -1).reverse()

  // Angles clockwise from the top: the shared ones centred on the top and the
  // bottom, the rest spread evenly over the side they lean to.
  const step = 360 / sides.length
  const half = n => (n ? ((n - 1) / 2) * step + step / 2 : 0)
  const angle = {}
  const around = (list, centreAt) => list.forEach((id, i) => { angle[id] = centreAt + (i - (list.length - 1) / 2) * step })
  const spread = (list, from, to) => list.forEach((id, i) => { angle[id] = from + ((to - from) * (i + 0.5)) / list.length })
  around(top, 0)
  around(bottom, 180)
  spread(right, half(top.length), 180 - half(bottom.length))
  spread(left, 180 + half(bottom.length), 360 - half(top.length))

  const factH = Math.max(...centre.map(id => h[id]))
  const sideH = Math.max(0, ...sides.map(id => h[id]))
  let rx = (at + NODE_W) / 2 + NODE_W / 2 + RING_GAP
  let ry = factH / 2 + sideH / 2 + RING_GAP
  const boxOf = id => ({ x: pos[id].x, y: pos[id].y, w: NODE_W, h: h[id] })
  const clash = (a, b) => a.x < b.x + b.w + RING_GAP && b.x < a.x + a.w + RING_GAP
    && a.y < b.y + b.h + RING_GAP && b.y < a.y + a.h + RING_GAP
  for (let tries = 0; tries < 80; tries += 1) {
    sides.forEach(id => {
      const a = angle[id] * DEG
      pos[id] = { x: cx + rx * Math.sin(a) - NODE_W / 2, y: -ry * Math.cos(a) - h[id] / 2 }
    })
    const boxes = ids.map(boxOf)
    if (!boxes.some((b, i) => boxes.some((c, j) => j > i && clash(b, c)))) break
    rx *= 1.06
    ry *= 1.06
  }
  const minX = Math.min(...ids.map(id => pos[id].x))
  const minY = Math.min(...ids.map(id => pos[id].y))
  ids.forEach(id => { pos[id] = { x: pos[id].x - minX, y: pos[id].y - minY } })
  return {
    pos, n: ids.length,
    w: Math.max(...ids.map(id => pos[id].x + NODE_W)),
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
