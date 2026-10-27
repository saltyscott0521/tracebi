import { Link } from 'react-router-dom'

import { useDownstream, useModel } from '../api'
import { humanise } from '../ask'
import { count } from '../format'
import { measureDefinition } from './modelGraph'
import { StateChip } from './Passport'
import { ErrorDetail, Spinner } from './Shared'

// Depends on this: every report figure downstream of one warehouse table,
// source table or measure, grouped by report, each with the number its built
// page prints and its report's verdict (GET /api/graph/downstream, from the
// builds' manifests). It is information for the person deciding whether to
// refresh, never a trigger (design/control-tower.md, A3): its only actions are
// links to the report and to the figure, whose trace the report page opens.

/** The pieces the panel answers for: a graph node's kind. A model offers its measures. */
export const DEPENDS_KINDS = new Set(['table', 'source_table', 'model'])

// More figures than this and only the first report starts open.
const OPEN_ALL = 12

function Figures({ data }) {
  const { reports = [], not_built: unbuilt = [], summary = {} } = data
  const openAll = (summary.figures || 0) <= OPEN_ALL
  return (
    <>
      <p className="deps__sum">
        {summary.figures
          ? `${count(summary.figures, 'figure')} in ${count(summary.reports, 'report')}`
          : 'No built figure reads it.'}
      </p>
      {reports.map((r, i) => (
        <details key={r.id} className="deps__rep" open={openAll || i === 0} data-report={r.name}>
          <summary>
            <span className="deps__rname">{r.label}</span>
            <span className="deps__n">{count(r.figures.length, 'figure')}</span>
          </summary>
          <ul className="deps__figs">
            {/* What the page prints a number for leads; the rest keep the page's order. */}
            {[...r.figures.filter(f => f.text), ...r.figures.filter(f => !f.text)].map(f => (
              <li key={f.id} data-figure={f.id}>
                <Link to={f.open} title={`Open ${r.label} at this figure, its trace beside it`}>{f.label}</Link>
                {f.text && <> · <b className="deps__num">{f.text}</b></>}
                {' · '}<StateChip state={r.trust} />
              </li>
            ))}
          </ul>
          <Link className="deps__open" to={r.open}>Open {r.label}</Link>
        </details>
      ))}
      {unbuilt.length > 0 && (
        <p className="deps__unbuilt">
          Not built here yet, so no figure to list: {unbuilt.map((r, i) => (
            <span key={r.id}>{i > 0 && ', '}<Link to={r.open}>{r.label}</Link></span>
          ))}
        </p>
      )}
    </>
  )
}

// A model's measures, each a link that asks what depends on it.
function MeasurePicker({ model, onMeasure }) {
  const { data } = useModel(model)
  const measures = data?.measures || []
  if (!measures.length) return null
  return (
    <>
      <p className="deps__sum">Pick a measure: the figures that read it.</p>
      <ul className="deps__measures">
        {measures.map(m => (
          <li key={m.name}>
            <a href={`?measure=${encodeURIComponent(`${model}:${m.name}`)}`} className="mchip"
               onClick={e => { e.preventDefault(); onMeasure(m.name) }}>{m.label || humanise(m.name)}</a>
          </li>
        ))}
      </ul>
    </>
  )
}

/**
 * The panel. *node* a graph node (a table, source table or model); *measure*
 * a measure's name when one of *node*'s (a model's) is picked; *onMeasure(name)*
 * picks one (null goes back to the model).
 */
export default function DependsOn({ node, measure, onMeasure }) {
  const model = node?.kind === 'model' ? node.name : null
  const id = model ? (measure ? `measure:${model}:${measure}` : '') : DEPENDS_KINDS.has(node?.kind) ? node.id : ''
  const { data, error, isLoading } = useDownstream(id)
  if (!node || !DEPENDS_KINDS.has(node.kind)) return null
  const definition = data?.measure ? measureDefinition(data.measure) : ''
  return (
    <section className="deps" aria-labelledby="deps-h" data-depends={id || node.id}>
      <h3 id="deps-h" className="deps__h">
        Depends on this{measure && <span className="deps__what"> · {data?.measure?.label || humanise(measure)}</span>}
      </h3>
      {model && measure && (
        <p className="deps__def">
          {definition && <>Defined as <code>{definition}</code>. </>}
          <a href="?" onClick={e => { e.preventDefault(); onMeasure(null) }}>Another measure</a>
        </p>
      )}
      {model && !measure ? <MeasurePicker model={model} onMeasure={onMeasure} />
        : error ? <ErrorDetail error={error} />
        : isLoading || !data ? <p className="deps__sum"><Spinner /> Reading the builds…</p>
        : <Figures data={data} />}
    </section>
  )
}
