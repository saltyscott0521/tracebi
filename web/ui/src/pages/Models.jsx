import { useEffect, useMemo, useRef } from 'react'
import { Link, Navigate, useSearchParams } from 'react-router-dom'

import { StorageLine, sourceKind } from '../components/Storage'
import { measureDefinition, modelSchema } from '../components/modelGraph'
import { dimensionLabel, encodeQuery, humanise, inSentence } from '../ask'
import {
  useModels, useModel, useDesk, useReports, usePipelines, useWarehouses,
} from '../api'
import { PageHeader } from '../components/Scope'
import CodeView from '../components/CodeView'
import DataBrowser, { InspectorSection } from '../components/DataBrowser'
import { count } from '../format'
import { askPath, dataPath, pipelineBelongsToModel, reportBelongsToModel } from '../nav'
import {
  Card, Badge, BtnLink, Chip, Empty, SkeletonList, SkeletonCard,
} from '../components/Shared'

// ── Measures ──────────────────────────────────────────────────────────────────

// A format as what it does to a number (the artifact's own named formats,
// tracebi.js applyNamedFormat), its token in the title. Anything else is shown
// as written.
const FORMAT_SAMPLES = {
  currency: '$1,234.00', currency0: '$1,234', currency_compact: '$1.2K', compact: '1.2K',
  comma: '1,234', decimal: '1,234.00', percent: '12.3%',
}

const askMeasure = (model, name) =>
  `${askPath(model)}&q=${encodeURIComponent(encodeQuery({ measures: [name], dimensions: [], filters: {} }))}`

// The model's named measures are its semantic contract: every report and
// query asks for them by name, so they are defined once, here. A row the
// address names (?measure=, as ⌘K links one) is scrolled to and marked.
function MeasuresTable({ model, measures, target }) {
  const targetRow = useRef(null)
  useEffect(() => { targetRow.current?.scrollIntoView({ block: 'center' }) }, [target])
  if (!measures.length) return <Empty message="This model declares no named measures." />
  return (
    <table className="tb-list mlist">
      <thead><tr><th>Measure</th><th>Defined as</th><th>Shown as</th><th><span className="sr-only">Ask</span></th></tr></thead>
      <tbody>
        {measures.map(m => {
          const label = m.label || m.description || humanise(m.name)
          const here = m.name === target
          return (
            <tr key={m.name} ref={here ? targetRow : undefined} className={here ? 'mlist__target' : undefined}
                data-measure={m.name}>
              <td>
                <span className="mlist__label">{label}</span>
                <code className="mlist__id">{m.name}</code>
                <span className="mlist__def-inline">{measureDefinition(m)}</span>
              </td>
              <td className="mlist__def">{measureDefinition(m)}</td>
              <td className="mlist__fmt" title={m.format || undefined}>
                {m.format && (FORMAT_SAMPLES[m.format] || <code>{m.format}</code>)}
              </td>
              <td><Link to={askMeasure(model, m.name)} aria-label={`Ask about ${label}`}>Ask</Link></td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}

// ── Model Detail ──────────────────────────────────────────────────────────────

// A model's tables point at connectors; a connector says where the data is.
// The model file (Python) only declares meaning: which table is a fact, what
// joins to what, what a measure is. Nothing is stored in it.
// TraceBi's own tables (the state store's) are never listed as data, even
// when a model names one; the server leaves them out and counts them.
function FrameworkHidden({ n }) {
  if (!(n > 0)) return null
  return (
    <p className="wb-meta" title="TraceBi's own tables (tracebi_*, alembic_version) are not shown as data.">
      {n} framework {n === 1 ? 'table' : 'tables'} hidden
    </p>
  )
}

function ModelStorage({ details, tables, hidden }) {
  if (!details.length) return <Empty message="This model declares no connector, so its tables have no data behind them." />
  return (
    <div>
      <p style={{ fontSize: 'var(--text-caption)', color: 'var(--text-2)', lineHeight: 1.6, margin: '0 0 14px', maxWidth: '72ch' }}>
        The model file only says what the data <em>means</em>. Each table below reads from a
        connector, and the connector says where the data is kept.
      </p>
      <div style={{ display: 'grid', gap: 12 }}>
        {details.map(c => {
          const served = tables.filter(t => t.connector === c.name)
          return (
            <div key={c.name} style={{ border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)', padding: '12px 14px', background: 'var(--surface)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 8 }}>
                <strong style={{ fontSize: 'var(--text-caption)' }}>{c.name}</strong>
                <Badge variant="gray" style={{ textTransform: 'none' }} title={c.type}>{sourceKind(c)}</Badge>
              </div>
              <div style={{ marginBottom: 10 }}><StorageLine storage={c.storage} /></div>
              <div style={{ fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: .5, marginBottom: 6 }}>
                Tables it serves ({served.length})
              </div>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                {served.map(t => (
                  <Badge key={t.name} variant="gray" title={t.source !== t.name ? `reads ${t.source}` : undefined}>
                    {t.name}{t.source !== t.name ? ` ← ${t.source}` : ''}
                  </Badge>
                ))}
              </div>
            </div>
          )
        })}
      </div>
      <FrameworkHidden n={hidden} />
    </div>
  )
}

// What the desk says of a warehouse table, in plain words.
const SINK_WORDS = { stale: 'changed since its checks last passed', no_contract: 'no checks declared' }

// The summary's folds, in the address as ?view= (one open at a time), so a
// reload keeps the one you are on and the model page's older addresses
// (?view=measures, relationships, storage, code) still open what they named.
// ?view=diagram and ?view=tables are the browser itself.
const FOLDS = [['measures', 'Measures'], ['relationships', 'Joins'], ['storage', 'Storage'], ['code', 'Code']]

const shapeWords = e => (e.cardinality === 'many-to-one' ? 'Many to one'
  : e.how ? `${e.how[0].toUpperCase()}${e.how.slice(1)} join` : 'Join')

function JoinsTable({ edges }) {
  if (!edges.length) return <Empty message="No joins declared. Give a fact its foreign_keys:, or list one under relationships:." />
  return (
    <table className="tb-list dbx-list">
      <thead><tr><th>From</th><th>To</th><th>Shape</th></tr></thead>
      <tbody>
        {edges.map(e => (
          <tr key={e.id}>
            <td><code>{e.from}.{e.fromKey}</code></td>
            <td><code>{e.to}.{e.toKey}</code></td>
            <td title={e.declared ? 'Declared as foreign_keys: on the fact' : 'Declared under relationships:'}><Chip>{shapeWords(e)}</Chip></td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

// The inspector with nothing selected: what the model is, in a few lines, its
// two actions, and its measures, joins, storage and code folded under them.
function ModelSummary({ name, data, schema, desk, action, view, setView }) {
  const grainRefs = (data.dimensions || []).flatMap(d => (d.attributes || []).map(attr => `${d.name}.${attr}`))
  const grain = grainRefs.map(ref => inSentence(dimensionLabel(data, ref))).join(' · ')
  const sinks = desk?.sinks || []
  const where = (data.connector_details || []).filter(c => c.storage?.where).map(c => c.storage.where)
  const fold = (key, body) => {
    const [, title] = FOLDS.find(([k]) => k === key)
    return (
      <InspectorSection key={key} id={key} title={title} open={view === key}
                        onToggle={() => setView(view === key ? null : key)}>
        {body}
      </InspectorSection>
    )
  }
  return (
    <div className="dbx-insp__summary">
      <header className="dbx-insp__head">
        <div className="dbx-insp__title"><h2 className="dbx-insp__name dbx-insp__name--sans">{data.label || name}</h2></div>
        {grain && <p className="dbx-insp__sub" title={grainRefs.join(', ')}>Grain: {grain}</p>}
        <p className="dbx-insp__sub">
          {count(schema.tables.length, 'table')} · {count(schema.edges.length, 'join')} · {count((data.measures || []).length, 'measure')}
        </p>
        {where.length > 0 && <p className="dbx-insp__sub">Reads {where.map((w, i) => <span key={w}>{i > 0 && ', '}<code>{w}</code></span>)}</p>}
        {desk?.warehouse && sinks.length === 0 && <p className="dbx-insp__sub">Its tables satisfied their checks when they were last written.</p>}
        {sinks.length > 0 && <p className="dbx-insp__sub">{sinks.map(s => `${s.table}: ${SINK_WORDS[s.status] || s.status}`).join(' · ')}</p>}
        {(data.owners || []).length > 0 && (
          <p className="dbx-insp__sub">Owners: {data.owners.join(', ')} (only they or an admin publish changes to it)</p>
        )}
        <div className="dbx-insp__acts">
          {action}
          <BtnLink size="sm" to={askPath(name)}>Ask this model</BtnLink>
        </div>
      </header>
      {fold('measures', <MeasuresTable model={name} measures={data.measures || []} target={null} />)}
      {fold('relationships', <JoinsTable edges={schema.edges} />)}
      {fold('storage', <ModelStorage details={data.connector_details || []} tables={data.tables} hidden={data.hidden_framework_tables} />)}
      {fold('code', <CodeView kind="models" name={name} />)}
      <FrameworkHidden n={data.hidden_framework_tables} />
    </div>
  )
}

// A fact's measures in the inspector: every measure the engine runs on it,
// what it is in words, how it is shown, and Ask with it picked.
function FactMeasures({ model, data, table, target }) {
  const facts = (data.facts || []).filter(f => f.table === table)
  const runs = new Set(facts.flatMap(f => f.runnable_measures || []))
  const measures = (data.measures || []).filter(m => runs.has(m.name))
  const here = useRef(null)
  useEffect(() => { here.current?.scrollIntoView({ block: 'center' }) }, [target])
  if (!facts.length) return null
  return (
    <InspectorSection id="measures" title="Measures on this fact" aside={count(measures.length, 'measure')}>
      {measures.length === 0 ? <p className="dbx-quiet">No named measure runs on this fact.</p> : (
        <ul className="dbx-measures">
          {measures.map(m => {
            const label = m.label || m.description || humanise(m.name)
            const on = m.name === target
            return (
              <li key={m.name} data-measure={m.name} ref={on ? here : undefined} className={on ? 'is-on' : undefined}>
                <span className="dbx-measures__top">
                  <Link to={askMeasure(model, m.name)} title={`Ask about ${label}`}>{label}</Link>
                  <code>{m.name}</code>
                  <Chip title="The engine runs this measure on this fact">Runs</Chip>
                </span>
                <span className="dbx-measures__def">
                  {measureDefinition(m)}
                  {m.format && <span title={m.format}> · {FORMAT_SAMPLES[m.format] || m.format}</span>}
                </span>
              </li>
            )
          })}
        </ul>
      )}
    </InspectorSection>
  )
}

/** *action*: the model's Edit as a draft, in the summary beside Ask this model. */
export function ModelDetail({ name, action }) {
  const { data, isLoading } = useModel(name)
  const { data: desk } = useDesk()
  // The selected table, the open fold and the named measure are the
  // address's (?table=, ?view=, ?measure=): each change is a step Back undoes.
  const [params, setParams] = useSearchParams()
  const view = FOLDS.some(([v]) => v === params.get('view')) ? params.get('view') : null
  const measure = params.get('measure')
  const schema = useMemo(() => (data ? modelSchema(data) : null), [data])
  // The tree's counts and checks: from the warehouse listing (one read) when
  // every table is in a warehouse; otherwise DataBrowser reads each table.
  const { data: wh, isLoading: whLoading } = useWarehouses()
  const infoOf = useMemo(() => {
    if (!schema) return undefined
    if (whLoading) return () => null
    const listed = t => (wh?.warehouses || []).find(w => w.name === t.connector)?.tables.find(x => x.name === t.source)
    if (!schema.tables.every(listed)) return undefined
    return t => { const x = t && listed(t); return x ? { rows: x.rows, exact: true, contract: x.contract, view: x.kind === 'view' } : null }
  }, [schema, wh, whLoading])
  // A named measure (⌘K links one) selects the fact it runs on.
  useEffect(() => {
    if (!data || !measure || params.get('table')) return
    const fact = (data.facts || []).find(f => (f.runnable_measures || []).includes(measure))
    if (fact) setParams(p => { const n = new URLSearchParams(p); n.set('table', fact.table); return n }, { replace: true })
  }, [data, measure]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!name) return (
    <Card>
      <Empty message="Select a model to read its file, grain, measures, tables, and connectors." />
    </Card>
  )
  if (isLoading) return <SkeletonCard />
  if (!data) return null
  const setView = v => setParams(p => {
    const n = new URLSearchParams(p)
    if (v) n.set('view', v); else n.delete('view')
    return n
  })

  return (
    <DataBrowser
      schema={schema} storeKey={`model-${name}`} label={`${data.label || name}: tables, joins and measures`}
      summary={<ModelSummary name={name} data={data} schema={schema} desk={desk} action={action} view={view} setView={setView} />}
      summaryOpen={!!view} infoOf={infoOf}
      measuresOf={t => <FactMeasures model={name} data={data} table={t.id} target={measure} />}
      emptyNote={<>This model declares no relationships. Give a fact its <code>foreign_keys:</code>, or list one under <code>relationships:</code>.</>}
    />
  )
}

// ── All models: pick one ─────────────────────────────────────────────────────

/**
 * The models, each opening *pageKey* for itself: Ask with it picked ('ask'),
 * or its page on Data ('data'; Data's own list is pages/Data.jsx).
 */
export default function Models({ pageKey = 'data' }) {
  const { data, isLoading } = useModels()
  const { data: reports } = useReports()
  const { data: pipelines } = usePipelines()
  const [params] = useSearchParams()
  const open = pageKey === 'ask' ? askPath : dataPath
  // Old links: /models?m=<model>, /explore?model=<model>.
  const legacy = params.get('m') || params.get('model')
  if (legacy) return <Navigate to={open(legacy)} replace />

  const models = data || []
  const reportCount = name => (reports || []).filter(r => reportBelongsToModel(r, name)).length
  const refreshes = name => (pipelines || []).some(p => pipelineBelongsToModel(p, name))

  return (
    <>
      <PageHeader pageKey={pageKey} model=""
        sub={pageKey === 'ask' ? 'Ask asks one model at a time. Pick one.' : undefined} />
      {isLoading ? <SkeletonList /> : models.length === 0 ? (
        <Empty message="No models yet. Create one with tracebi new-model, in models/." />
      ) : (
        <div className="model-cards">
          {models.map((m, i) => {
            const n = reportCount(m.name)
            return (
              <Link key={m.name} to={open(m.name)} className="model-card rise" style={{ '--i': i }}>
                <span className="model-card__name">{m.label || m.name}</span>
                <span className="model-card__shape">
                  {m.facts
                    ? `${m.facts.length} fact${m.facts.length !== 1 ? 's' : ''} · ${m.dimensions.length} dimension${m.dimensions.length !== 1 ? 's' : ''} · ${m.measures.length} measures`
                    : `${m.tables.length} tables`}
                </span>
                <span className="model-card__facts">
                  <span>{n} report{n !== 1 ? 's' : ''}</span>
                  <span>{refreshes(m.name) ? 'Has a refresh pipeline' : 'No refresh pipeline'}</span>
                </span>
              </Link>
            )
          })}
        </div>
      )}
    </>
  )
}
