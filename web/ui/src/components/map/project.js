import { pipelineBelongsToModel, reportBelongsToModel } from '../../nav'
import { bus, byTone, clamp, fileName, heightOf, reportLabel, widest } from './geometry'
import { reportState, transformState } from './states'

// The whole project: one band per model, each reading left to right,
//
//   Transform  →  Warehouse  →  Model  →  Reports
//
// A card is something the user writes (a transform, a model, a report). A pill
// is what gets handed on (the warehouse file). Everything is computed from the
// lists the API already serves. The column of input files is not drawn: no
// endpoint says what a transform reads, and reading the Python to find out is
// not this page's job.

const TOP = 30            // under the column headings
const BAND_GAP = 22
const BAND_MIN = 176
const REPORT_GAP = 4
const PILL_GAP = 8
const ARROW = 48          // the run of an arrow between two columns
const FAN = 96            // the run of the fan from a model to its reports
const SIDE = 20

/** The pipeline that refreshes a model: the one made for it, else any that touches it. */
export const pipelineFor = (pipelines, model) =>
  pipelines.find(p => p.model === model) || pipelines.find(p => pipelineBelongsToModel(p, model))

const byName = (a, b) => a.name.localeCompare(b.name)

/** What a warehouse pill is called, and whom it is shared with. */
function warehouseOf(connector, model, connectors) {
  const c = connectors[connector]
  const where = c?.storage?.where
  const file = where && ['file', 'directory'].includes(c.storage.kind)
    ? fileName(where, c.storage.kind)
    : connector
  const others = (c?.used_by || []).filter(m => m !== model)
  return { connector, file, others, missing: c?.storage?.exists === false }
}

export function projectLayout({ models, connectors, pipelines, reports, builds, tinted }) {
  const sorted = [...models].sort(byName)
  const placed = sorted.map(m => {
    const pipeline = pipelineFor(pipelines, m.name)
    return {
      model: m.name,
      pipeline,
      transform: pipeline ? pipeline.transform || pipeline.pipeline : null,
      warehouses: (m.connectors || []).map(c => warehouseOf(c, m.name, connectors)),
      reports: reports.filter(r => reportBelongsToModel(r, m.name)).sort(byName),
    }
  })

  // Column widths follow the longest name in each, within bounds.
  const all = f => placed.flatMap(f)
  const tW = clamp(Math.ceil(widest(all(b => (b.transform ? [b.transform] : []))) + 28), 184, 280)
  const wW = clamp(Math.ceil(widest(all(b => b.warehouses.map(w => w.file))) + 28), 168, 240)
  const mW = clamp(Math.ceil(widest(placed.map(b => b.model)) + 28), 168, 280)
  const rW = clamp(Math.ceil(widest(all(b => b.reports.map(r => reportLabel(r.name, b.model)))) + 28), 216, 320)
  const xT = SIDE
  const xW = xT + tW + ARROW
  const xM = xW + wW + ARROW
  const xR = xM + mW + FAN
  const width = xR + rW + SIDE

  const nodes = []
  const edges = []
  const bands = []
  const headers = [
    { x: xT, label: 'Transform', n: 1 },
    { x: xW, label: 'Warehouse' },
    { x: xM, label: 'Model', n: 2 },
    { x: xR, label: 'Reports', n: 3 },
  ]

  let top = TOP
  for (const b of placed) {
    const act = { zoom: b.model }
    const id = part => `${b.model}:${part}`

    const tState = b.pipeline && transformState(b.pipeline)
    const transform = b.transform && {
      id: id('transform'), role: 'transform', shape: 'card', x: xT, w: tW, name: b.transform,
      label: tState?.label || (b.pipeline.transform ? '' : 'pipeline'), tone: tState?.tone || 'quiet', action: act,
    }
    const warehouses = b.warehouses.map(w => ({
      id: id(`warehouse:${w.connector}`), role: 'warehouse', shape: 'pill', x: xW, w: wW, name: w.file,
      connector: w.connector, others: w.others, missing: w.missing, action: act,
    }))
    const model = { id: id('model'), role: 'model', shape: 'card', x: xM, w: mW, name: b.model, tone: 'quiet', action: act }
    const cards = b.reports.map(r => {
      const state = reportState(builds[r.name])
      return {
        id: id(`report:${r.name}`), role: 'report', shape: 'card', x: xR, w: rW, name: reportLabel(r.name, b.model),
        label: state?.label || '', tone: state?.tone || 'quiet', action: { zoom: b.model, sel: `report:${r.name}` },
      }
    })

    // Heights: from what each says. A pill leaves room for a status that arrives later.
    if (transform) transform.h = heightOf({ ...transform, min: 52 })
    model.h = heightOf({ ...model, min: 52 })
    warehouses.forEach(w => {
      w.label = w.missing ? '' : w.others.length ? `shared with ${w.others.join(', ')}` : ''
      w.h = heightOf({ ...w, min: 48, reserve: true, border: 1.5 })
    })
    cards.forEach(c => { c.h = heightOf({ ...c, min: 52 }) })

    const stack = (list, gap) => list.reduce((s, n) => s + n.h, 0) + gap * Math.max(0, list.length - 1)
    const reportsH = stack(cards, REPORT_GAP)
    const pillsH = stack(warehouses, PILL_GAP)
    const content = Math.max(reportsH, pillsH, transform?.h || 0, model.h, 52)
    const height = Math.max(BAND_MIN, 34 + content + 14)
    const cy = top + Math.max(98, 34 + content / 2)

    const place = (list, gap, total) => {
      let y = cy - total / 2
      list.forEach(n => { n.y = y; y += n.h + gap })
    }
    if (transform) { transform.y = cy - transform.h / 2 }
    model.y = cy - model.h / 2
    place(warehouses, PILL_GAP, pillsH)
    place(cards, REPORT_GAP, reportsH)

    const mid = n => ({ x: n.x, y: n.y + n.h / 2 })
    const right = n => ({ x: n.x + n.w, y: n.y + n.h / 2 })
    const flow = []
    if (transform && warehouses.length) {
      flow.push(bus({ from: [right(transform)], to: warehouses.map(mid), trunk: xT + tW + ARROW / 2, tone: tState ? 'warn' : 'quiet' }))
    } else if (transform) {
      flow.push(bus({ from: [right(transform)], to: [mid(model)], trunk: xT + tW + ARROW / 2 }))
    }
    if (warehouses.length) {
      flow.push(bus({ from: warehouses.map(right), to: [mid(model)], trunk: xW + wW + ARROW / 2 }))
    }
    if (cards.length) {
      flow.push(bus({ from: [right(model)], to: cards.map(mid), trunk: xM + mW + FAN / 2 }))
    }
    edges.push(...flow)

    nodes.push(...[transform, ...warehouses, model, ...cards].filter(Boolean).map(n => ({ ...n, band: b.model })))
    bands.push({
      model: b.model, x: 12, y: top, w: width - 24, h: height, tinted: b.model === tinted,
      empty: {
        transform: !b.transform && { x: xT, y: cy - 26, w: tW, text: 'No pipeline refreshes this model.' },
        reports: !cards.length && { x: xR, y: cy - 26, w: rW, text: 'No reports read this model yet.' },
      },
    })
    top += height + BAND_GAP
  }

  const drawn = new Set(placed.flatMap(b => b.reports.map(r => r.name)))
  return {
    level: 'project', width, height: top - BAND_GAP + 18, headers, bands, nodes, edges: byTone(edges),
    // For the text panel: what is drawn, and which warehouse files two models share.
    summary: {
      models: placed.length,
      transforms: new Set(placed.map(b => b.transform).filter(Boolean)).size,
      reports: drawn.size,
      unplaced: reports.filter(r => !drawn.has(r.name)).length,
      shared: sharedFiles(placed),
    },
  }
}

/** Warehouse files more than one model reads: who reads them, and which transforms write them. */
function sharedFiles(placed) {
  const found = new Map()
  for (const b of placed) {
    for (const w of b.warehouses) {
      if (!w.others.length) continue
      const entry = found.get(w.connector) || { file: w.file, models: [], writers: new Set() }
      entry.models.push(b.model)
      if (b.transform) entry.writers.add(b.transform)
      found.set(w.connector, entry)
    }
  }
  return [...found.values()].map(e => ({ file: e.file, models: e.models, writers: [...e.writers] }))
}
