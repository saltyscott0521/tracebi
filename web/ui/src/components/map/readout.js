import { reportPagePath } from '../../nav'
import { MEASURE_KINDS, measureDefinition } from '../modelGraph'
import { reportLabel } from './geometry'
import { reportState } from './states'

// The text under the map: what is selected, said in words. A person who cannot
// see the blue path reads the same thing here.

const plural = (n, one, many = `${one}s`) => `${n} ${n === 1 ? one : many}`

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
    text.push(`${plural(summary.unplaced, 'report')} ${summary.unplaced === 1 ? 'names' : 'name'} no model and ${summary.unplaced === 1 ? 'is' : 'are'} not drawn.`)
  }
  text.push('Open a model to see its measures.')
  return {
    kind: 'Project',
    name: `${plural(summary.models, 'model')} · ${plural(summary.transforms, 'transform')} · ${plural(summary.reports, 'report')}`,
    text: text.join(' '),
  }
}

export function modelReadout({ name, info, a, sel, builds }) {
  if (sel?.type === 'measure') {
    const m = info.measures.find(x => x.name === sel.id)
    const def = measureDefinition(m)
    const facts = a.factsFor(sel.id).map(f => f.name)
    const users = a.usedBy(sel.id).map(r => reportLabel(r, name))
    const what = def ? `${m.name} = ${def}` : `${m.name} (${(MEASURE_KINDS[m.kind] || m.kind || 'measure').toLowerCase()})`
    return {
      kind: 'Measure', name: m.name,
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
      kind: 'Report', name: reportLabel(sel.id, name),
      text: [
        asked.length ? `Asks ${name} for ${asked.join(', ')}.${read}` : `Asks ${name} for no declared measure.`,
        state ? (state.detail || (state.tone === 'ghost' ? 'It has not been built yet.' : '')) : '',
      ].filter(Boolean).join(' '),
      open: reportPagePath(sel.id, [name]),
    }
  }
  const unused = a.declared.filter(m => a.usedBy(m).length === 0).length
  return {
    kind: 'Model', name,
    text: [
      `${plural(info.tables.length, 'table')}, ${plural(a.declared.length, 'measure')} and ${plural(a.placed.length, 'report')}.`,
      unused ? `${plural(unused, 'measure')} ${unused === 1 ? 'is' : 'are'} asked for by no report.` : '',
      'Pick a measure or a report to light its path.',
    ].filter(Boolean).join(' '),
  }
}
