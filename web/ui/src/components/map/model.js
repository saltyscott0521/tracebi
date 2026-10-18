import { reportBelongsToModel } from '../../nav'
import { bus, byTone, clamp, heightOf, nameLines, reportLabel, widest, MONO_W, NAME_LINE } from './geometry'
import { pipelineFor } from './project'
import { reportState, transformState } from './states'

// One model, opened up:
//
//   Transform → Warehouse tables → Model (a card holding a pill per measure) → Reports
//
// Picking a measure or a report lights the whole path through the model:
// transform → the fact table that runs it → the measure → the reports that use it.

const CARD_TOP = 44
const CARD_HEAD = 78       // the card's own heading, above its first measure
const CARD_FOOT = 22
const PILL_H = 28
const PILL_GAP = 8
const TABLE_GAP = 22
const SIDE = 24
const RUN = 44             // the run of an arrow between two columns
const FAN = 48             // from the card to its reports

const byName = (a, b) => a.name.localeCompare(b.name)

/** `measure:fair_value` -> { type, id }; anything else -> null. */
export function parseSel(value) {
  const m = /^(measure|report):(.+)$/.exec(value || '')
  return m ? { type: m[1], id: m[2] } : null
}

/**
 * What the model, its reports and its facts say to each other: which
 * measures a report asks for, which reports use a measure, which fact runs it.
 * A report's measures are the declared ones its bindings name.
 */
export function analyze(info, reports, model) {
  const declared = (info?.measures || []).map(m => m.name)
  const known = new Set(declared)
  const placed = reports.filter(r => reportBelongsToModel(r, model)).sort(byName)
  const asks = Object.fromEntries(placed.map(r => [r.name, (r.measures || []).filter(m => known.has(m))]))
  return {
    declared, placed, asks,
    usedBy: m => placed.filter(r => asks[r.name].includes(m)).map(r => r.name),
    factsFor: m => (info?.facts || []).filter(f => (f.runnable_measures || []).includes(m)),
  }
}

/** What a selection lights: measures, reports, and the fact tables that run them. */
export function lightOf(sel, a) {
  const lit = { measures: new Set(), reports: new Set(), tables: new Set() }
  if (sel?.type === 'measure' && a.declared.includes(sel.id)) {
    lit.measures.add(sel.id)
    a.usedBy(sel.id).forEach(r => lit.reports.add(r))
  } else if (sel?.type === 'report' && a.asks[sel.id]) {
    lit.reports.add(sel.id)
    a.asks[sel.id].forEach(m => lit.measures.add(m))
  }
  lit.measures.forEach(m => a.factsFor(m).forEach(f => lit.tables.add(f.table)))
  return lit
}

/** The selection, kept only if it names something this model has. */
export function validSel(sel, a) {
  if (sel?.type === 'measure') return a.declared.includes(sel.id) ? sel : null
  if (sel?.type === 'report') return a.asks[sel.id] ? sel : null
  return null
}

export function modelLayout({ name, info, a, pipelines, builds, sel }) {
  const pipeline = pipelineFor(pipelines, name)
  const tState = pipeline && transformState(pipeline)
  const lit = lightOf(sel, a)
  const anyLit = lit.measures.size > 0
  const unused = m => a.usedBy(m).length === 0

  const transformName = pipeline && (pipeline.transform || pipeline.pipeline)
  const tables = (info?.tables || []).map(t => ({
    key: t.name, connector: t.connector,
    // The pill names the physical table: that is what the warehouse holds.
    source: /^[\w.]+$/.test(t.source || '') ? t.source : t.name,
  }))

  const tW = clamp(Math.ceil(widest(transformName ? [transformName] : []) + 28), 184, 260)
  const bW = clamp(Math.ceil(widest(tables.map(t => t.source)) + 28), 150, 220)
  const mW = clamp(Math.ceil(Math.max(0, ...a.declared.map(m => m.length * MONO_W + 34 + (unused(m) ? 56 : 0)))), 212, 320)
  const rW = clamp(Math.ceil(widest(a.placed.map(r => reportLabel(r.name, name))) + 28), 210, 280)
  const xT = SIDE
  const xB = xT + tW + RUN
  const xC = xB + bW + RUN
  const cardW = mW + 32
  const xM = xC + 16
  const xR = xC + cardW + FAN
  const width = xR + rW + SIDE

  const transform = pipeline && {
    id: 'transform', role: 'transform', shape: 'card', x: xT, w: tW, name: transformName,
    label: tState?.label || (pipeline.transform ? '' : 'pipeline'),
    tone: tState?.tone || (anyLit ? 'hot' : 'quiet'),
  }
  if (transform) transform.h = heightOf({ ...transform, min: 52 })

  const tableNodes = tables.map(t => ({
    id: `table:${t.key}`, role: 'table', shape: 'pill', x: xB, w: bW, name: t.source, key: t.key,
    connector: t.connector, source: t.source, lit: lit.tables.has(t.key),
  }))
  tableNodes.forEach(t => { t.h = heightOf({ ...t, min: 48, reserve: true, border: 1.5 }) })

  const measures = a.declared.map(m => {
    const note = unused(m) ? 'unused' : ''
    const hot = lit.measures.has(m)
    return {
      id: `measure:${m}`, role: 'measure', shape: 'pill', x: xM, w: mW, name: m, note,
      tone: hot ? 'hot' : note ? 'unused' : 'quiet', action: { select: `measure:${m}` },
      pressed: sel?.type === 'measure' && sel.id === m,
      h: Math.max(PILL_H, 9 + nameLines(m, mW - 28 - (note ? 56 : 0)) * NAME_LINE),
    }
  })

  const cards = a.placed.map(r => {
    const state = reportState(builds[r.name], r)
    return {
      id: `report:${r.name}`, role: 'report', shape: 'card', x: xR, w: rW, name: reportLabel(r.name, name), key: r.name,
      label: state?.label || '', tone: lit.reports.has(r.name) ? 'hot' : state?.tone || 'quiet',
      action: { select: `report:${r.name}` }, pressed: sel?.type === 'report' && sel.id === r.name,
    }
  })
  cards.forEach(c => { c.h = heightOf({ ...c, min: 56 }) })

  const stack = (list, gap) => list.reduce((s, n) => s + n.h, 0) + gap * Math.max(0, list.length - 1)
  const measuresH = stack(measures, PILL_GAP)
  const slot = Math.max(0, ...cards.map(c => c.h)) + 14
  // The card hugs its measures. The reports spread at least as tall as they are,
  // and when there are more reports than room, that column (not the card) is the
  // tall one: everything shares one centre line.
  const bodyH = Math.max(measuresH, 120)
  const cardH = CARD_HEAD + bodyH + CARD_FOOT
  const span = Math.max(bodyH, cards.length * slot)
  const tall = Math.max(span, stack(tableNodes, TABLE_GAP), transform?.h || 0)
  const toCentre = CARD_HEAD + bodyH / 2
  const cardTop = CARD_TOP + Math.max(0, tall / 2 - toCentre)
  const cy = cardTop + toCentre

  const place = (list, gap, total) => {
    let y = cy - total / 2
    list.forEach(n => { n.y = y; y += n.h + gap })
  }
  if (transform) transform.y = cy - transform.h / 2
  place(tableNodes, TABLE_GAP, stack(tableNodes, TABLE_GAP))
  place(measures, PILL_GAP, measuresH)
  cards.forEach((c, i) => { c.y = cy - span / 2 + (span / cards.length) * (i + 0.5) - c.h / 2 })

  const mid = n => ({ x: n.x, y: n.y + n.h / 2 })
  const right = n => ({ x: n.x + n.w, y: n.y + n.h / 2 })
  const edges = []
  const tableTrunk = xT + tW + RUN / 2
  if (transform && tableNodes.length) {
    edges.push(bus({ from: [right(transform)], to: tableNodes.map(mid), trunk: tableTrunk, tone: tState ? 'warn' : 'quiet' }))
  }
  tableNodes.forEach(t => {
    edges.push(bus({ from: [right(t)], to: [{ x: xC, y: right(t).y }], trunk: right(t).x + 10 }))
  })
  const litTables = tableNodes.filter(t => t.lit)
  const litMeasures = measures.filter(m => lit.measures.has(m.name))
  const litCards = cards.filter(c => lit.reports.has(c.key))
  if (transform && litTables.length) {
    edges.push(bus({ from: [right(transform)], to: litTables.map(mid), trunk: tableTrunk, tone: 'hot', width: 3 }))
  }
  if (litTables.length && litMeasures.length) {
    edges.push(bus({ from: litTables.map(right), to: litMeasures.map(mid), trunk: xC - RUN / 2, tone: 'hot', width: 3 }))
  }
  if (litMeasures.length && litCards.length) {
    edges.push(bus({ from: litMeasures.map(right), to: litCards.map(mid), trunk: xC + cardW + FAN / 2, tone: 'hot', width: 3 }))
  }

  return {
    level: 'model', width, height: Math.max(cardTop + cardH, cy + tall / 2) + 24,
    headers: [
      { x: xT, y: 16, label: 'Transform', n: 1 },
      { x: xB, y: 16, label: 'Warehouse tables' },
      { x: xR, y: 16, label: 'Reports', n: 3 },
    ],
    card: { x: xC, y: cardTop, w: cardW, h: cardH, name, empty: measures.length ? '' : 'No measures declared.' },
    nodes: [transform, ...tableNodes, ...measures, ...cards].filter(Boolean),
    edges: byTone(edges),
    empty: {
      transform: !pipeline && { x: xT, y: cy - 26, w: tW, text: 'No pipeline refreshes this model.' },
      tables: !tableNodes.length && { x: xB, y: cy - 26, w: bW, text: 'The model declares no tables.' },
      reports: !cards.length && { x: xR, y: cy - 26, w: rW, text: 'No reports read this model yet.' },
    },
  }
}
