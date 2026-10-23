import { reportPagePath } from '../../nav'
import { MEASURE_KINDS, measureDefinition } from '../modelGraph'
import { reportState } from './states'
import { count } from '../../format'

// The text under the map: what is selected, said in words. A person who cannot
// see the blue path reads the same thing here. Reports and the model by their labels.

const titleOf = (a, report) => a.placed.find(r => r.name === report)?.display_name || report

/** a, b and c */
const list = items => (items.length < 2 ? items.join('') : `${items.slice(0, -1).join(', ')} and ${items[items.length - 1]}`)

const sentence = text => (/[.!?]$/.test(text) ? text : `${text}.`)

export function projectReadout(summary, tinted) {
  const text = []
  if (tinted) text.push('The tinted band is the model you have selected.')
  for (const s of summary.shared) {
    text.push(s.writers.length > 1
      ? `${s.file} is shared: ${list(s.writers)} ${s.writers.length === 2 ? 'both' : 'all'} write to it, so a failure in one shows on the other's tables.`
      : `${s.file} is shared by ${list(s.models)}.`)
  }
  if (summary.unplaced) {
    text.push(`${count(summary.unplaced, 'report')} ${summary.unplaced === 1 ? 'names' : 'name'} no model and ${summary.unplaced === 1 ? 'is' : 'are'} not drawn.`)
  }
  text.push('Open a model to see its measures.')
  return {
    kind: 'Project',
    name: `${count(summary.models, 'model')} · ${count(summary.transforms, 'transform')} · ${count(summary.reports, 'report')}`,
    text: text.join(' '),
  }
}

export function modelReadout({ name, info, a, sel, builds }) {
  const label = info?.label || name
  if (sel?.type === 'measure') {
    const m = info.measures.find(x => x.name === sel.id)
    const def = measureDefinition(m)
    const facts = a.factsFor(sel.id).map(f => f.name)
    const users = a.usedBy(sel.id).map(r => titleOf(a, r))
    const what = def ? `${m.name} = ${def}` : `${m.name} (${(MEASURE_KINDS[m.kind] || m.kind || 'measure').toLowerCase()})`
    return {
      kind: 'Measure', name: m.name, mono: true,
      text: [
        sentence(`${what}${facts.length ? ` over ${list(facts)}` : ''}`),
        m.description ? sentence(m.description) : '',
        users.length ? `Used by ${users.join(', ')}.` : 'No report uses it yet.',
      ].filter(Boolean).join(' '),
    }
  }
  if (sel?.type === 'report') {
    const asked = a.asks[sel.id]
    const facts = [...new Set(asked.flatMap(m => a.factsFor(m).map(f => f.name)))]
    const state = reportState(builds[sel.id], a.placed.find(r => r.name === sel.id))
    const read = facts.length === 1 ? ` All read ${facts[0]}.` : facts.length ? ` They can run on ${list(facts)}.` : ''
    return {
      kind: 'Report', name: titleOf(a, sel.id),
      text: [
        asked.length ? `Asks ${label} for ${asked.join(', ')}.${read}` : `Asks ${label} for no declared measure.`,
        state ? (state.detail || (state.tone === 'ghost' ? 'It has not been built yet.' : '')) : '',
      ].filter(Boolean).join(' '),
      open: reportPagePath(sel.id),
    }
  }
  const unused = a.declared.filter(m => a.usedBy(m).length === 0).length
  return {
    kind: 'Model', name: label,
    text: [
      `${count(info.tables.length, 'table')}, ${count(a.declared.length, 'measure')} and ${count(a.placed.length, 'report')}.`,
      unused ? `${count(unused, 'measure')} ${unused === 1 ? 'is' : 'are'} asked for by no report.` : '',
      'Pick a measure or a report to light its path.',
    ].filter(Boolean).join(' '),
  }
}
