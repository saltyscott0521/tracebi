// Layout and tracing for a report's lineage flow (/api/reports/{name}/lineage).
//
// The server sends nodes tagged with a column (transform → stored tables →
// model → queries → figures); this places them and answers "what is upstream
// and downstream of this node", which is how a number is traced to its data.
// Pure functions, so they can be read and checked without a browser.

export const NODE_W = 196
export const COL_GAP = 46
const GAP = 16
const HEIGHT = { transform: 84, table: 92, model: 92, binding: 84, figures: 70, unverified: 70 }
export const LABEL_H = 34

const heightOf = n => HEIGHT[n.kind] || 80

export function layoutFlow(flow) {
  const cols = flow.columns.map(c => c.index)
  const xOf = Object.fromEntries(cols.map((c, i) => [c, i * (NODE_W + COL_GAP)]))
  const byCol = {}
  flow.nodes.forEach(n => { (byCol[n.column] ||= []).push(n) })
  const total = list => list.reduce((h, n) => h + heightOf(n) + GAP, -GAP)
  const tallest = Math.max(0, ...Object.values(byCol).map(total))
  const placed = []
  Object.entries(byCol).forEach(([col, list]) => {
    let y = LABEL_H + (tallest - total(list)) / 2
    list.forEach(n => {
      placed.push({ ...n, position: { x: xOf[col], y }, height: heightOf(n) })
      y += heightOf(n) + GAP
    })
  })
  const labels = flow.columns.map(c => ({ id: `col:${c.index}`, label: c.label, x: xOf[c.index] }))
  return { nodes: placed, labels, height: tallest + LABEL_H }
}

// What depends on what, precisely. The drawn graph routes every table through
// the model to keep it readable, but a number depends only on the tables its
// own query read, so tracing follows those: table → query, model → query.
function precise(flow) {
  const kept = flow.edges.filter(e => {
    const [from, to] = [e.source.split(':')[0], e.target.split(':')[0]]
    return !(from === 'table' && to === 'model') && !(from === 'model' && to === 'binding')
  })
  flow.nodes.filter(n => n.kind === 'binding').forEach(b => {
    ;(b.detail.tables || []).forEach(t => kept.push({ source: `table:${t}`, target: b.id }))
    if (b.detail.model) kept.push({ source: `model:${b.detail.model}`, target: b.id })
  })
  return kept
}

// Every node upstream and downstream of `id`, plus `id` itself.
export function tracePath(flow, id) {
  const edges = precise(flow)
  const out = new Set([id])
  const walk = (dir) => {
    const stack = [id]
    while (stack.length) {
      const cur = stack.pop()
      edges.forEach(e => {
        const [from, to] = dir === 'down' ? [e.source, e.target] : [e.target, e.source]
        if (from === cur && !out.has(to)) { out.add(to); stack.push(to) }
      })
    }
  }
  walk('down'); walk('up')
  return out
}
