import { useEffect, useMemo, useRef } from 'react'
import { Link, Navigate, useSearchParams } from 'react-router-dom'

import { StorageLine, sourceKind } from '../components/Storage'
import { measureDefinition, modelSchema } from '../components/modelGraph'
import { dimensionLabel, encodeQuery, humanise, inSentence, questionQuery } from '../ask'
import {
  useModels, useModel, useModelContext, useDesk, useReports, usePipelines, useWarehouses,
} from '../api'
import { PageHeader } from '../components/Scope'
import CodeView from '../components/CodeView'
import DataBrowser, { InspectorSection } from '../components/DataBrowser'
import { count } from '../format'
import { pipelineFor, writtenFor } from '../chain'
import { checksWords, pipelineRefresh } from '../words'
import { askPath, modelPath, reportBelongsToModel } from '../nav'
import {
  Card, Badge, Chip, Empty, ErrorDetail, SkeletonList, SkeletonCard,
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

// A measure as it is declared, compactly, in the model file's own terms:
// sum(fair_value), spread_x_par / par_amount, rank: fair_value.
function declaredAs(m) {
  const where = m.filters ? ` where ${JSON.stringify(m.filters)}` : ''
  const per = (m.partition_by || []).length ? ` per ${m.partition_by.join(', ')}` : ''
  if (m.ratio) return `${m.ratio[0]} / ${m.ratio[1]}`
  if (m.share) return `share: ${m.share}`
  if (m.rank) return `rank: ${m.rank}${per}`
  if (m.running) return `running: ${m.running}${per}`
  if (m.measure_expr) return m.measure_expr
  if (m.period_end) return `period_end: ${m.period_end.join(', ')}`
  if (m.offset) return `offset: ${m.offset.join(', ')}`
  if (m.growth) return `growth: ${m.growth.join(', ')}`
  if (m.to_date) return `to_date: ${m.to_date.join(', ')}`
  if (m.expr) return `${m.agg}(${m.expr})${where}`
  if (m.column) return `${m.agg}(${m.column})${where}`
  return ''
}

// The model's named measures are its semantic contract: every report and
// query asks for them by name, so they are defined once, here, with the words
// people and agents use for them. A row the address names (?measure=, as ⌘K
// links one) is scrolled to and marked; *onPick* selects its fact.
function MeasuresTable({ model, measures, target, answers = {}, onPick }) {
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
          const about = m.description && m.description !== label ? m.description : null
          return (
            <tr key={m.name} ref={here ? targetRow : undefined} className={here ? 'mlist__target' : undefined}
                data-measure={m.name}>
              <td>
                {onPick
                  ? <button type="button" className="mlist__label mlist__pick" onClick={() => onPick(m.name)}
                            title="Select the fact it runs on">{label}</button>
                  : <span className="mlist__label">{label}</span>}
                <code className="mlist__id">{m.name}</code>
                <code className="mlist__expr">{declaredAs(m)}</code>
                {about && <span className="mlist__about">{about}</span>}
                {(m.synonyms || []).length > 0 && <span className="mlist__also">Also: {m.synonyms.join(', ')}</span>}
                {(answers[m.name] || []).length > 0 && (
                  <span className="mlist__also">Answers: {answers[m.name].map(q => `“${q}”`).join(' ')}</span>
                )}
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

// The summary's folds, in the address as ?view= (one open at a time), so a
// reload keeps the one you are on and the model page's older addresses
// (?view=relationships, storage, code) still open what they named.
// ?view=measures names the Semantic layer's Measures, always open; the
// address only brings it into view. ?view=agent opens What an agent sees.
const FOLDS = [['relationships', 'Joins'], ['storage', 'Storage'], ['code', 'Code'], ['agent', 'What an agent sees']]
const VIEWS = ['measures', ...FOLDS.map(([k]) => k)]

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

// The grain in one sentence: each fact and the dimensions it is measured by
// (its declared joins; the model declares no more than that).
export function grainSentence(data) {
  const facts = (data.facts || []).map(f => {
    const by = Object.keys(f.foreign_keys || {}).map(dim => {
      const d = (data.dimensions || []).find(x => x.name === dim)
      return inSentence(d?.attributes?.length ? dimensionLabel(data, `${dim}.${d.attributes[0]}`) : humanise(dim))
    })
    return `${inSentence(humanise(f.name))}${by.length ? ` by ${listWords(by)}` : ''}`
  })
  return facts.join('; ')
}
const listWords = items => (items.length < 2 ? items.join('') : `${items.slice(0, -1).join(', ')} and ${items[items.length - 1]}`)

// Each dimension with its attributes, in the words the model gives them.
function DimensionsList({ data }) {
  const dims = data.dimensions || []
  if (!dims.length) return <p className="dbx-quiet">This model declares no dimensions.</p>
  return (
    <ul className="sem-dims">
      {dims.map(d => (
        <li key={d.name} data-dimension={d.name}>
          <span className="sem-dims__top"><strong>{humanise(d.name)}</strong> <code>{d.name}</code></span>
          {d.description && <span className="sem-dims__about">{d.description}</span>}
          {(d.synonyms || []).length > 0 && <span className="mlist__also">Also: {d.synonyms.join(', ')}</span>}
          <ul className="sem-attrs">
            {[...(d.attributes || []), ...Object.keys(d.derived || {})].map(attr => {
              const about = d.attribute_info?.[attr] || {}
              const derived = d.derived?.[attr]
              return (
                <li key={attr}>
                  <code>{attr}</code>
                  {about.label && <span> {about.label}</span>}
                  {about.description && <span className="sem-dims__about"> · {about.description}</span>}
                  {derived && <span className="sem-dims__about"> · {derived.grain ? `${derived.grain} of ${derived.of}` : `bands of ${derived.of}`}</span>}
                  {(about.synonyms || []).length > 0 && <span className="mlist__also"> · also {about.synonyms.join(', ')}</span>}
                </li>
              )
            })}
          </ul>
        </li>
      ))}
    </ul>
  )
}

// What `get_context --model` hands an agent for this model, read when shown:
// the same function behind the CLI, the gateway and this route. The model
// page's Agents tab, and a fold of the Schema tab's summary.
export function AgentContext({ name }) {
  const { data, error, isLoading } = useModelContext(name)
  if (isLoading) return <SkeletonList />
  if (error) return <ErrorDetail error={error} />
  return (
    <>
      <p className="dbx-quiet">
        The <code>model</code> that <code>tracebi context --model {name}</code> and the agent&rsquo;s
        <code> get_context</code> return: curating the words above curates this.
      </p>
      <pre className="sem-agent" tabIndex={0} aria-label="What an agent sees"><code>{JSON.stringify(data, null, 2)}</code></pre>
    </>
  )
}

// The questions that answer each measure: a question answers the measure its
// words name (the match Ask makes).
function answersOf(data) {
  const answers = {}
  for (const q of data.questions || []) {
    const m = questionQuery(data, q)?.measures?.[0]
    if (m) (answers[m] = answers[m] || []).push(q)
  }
  return answers
}

/**
 * The model page's Measures tab: every named measure, in the Semantic
 * layer's words. Picking one opens the Schema tab with the fact it runs on
 * selected (?measure=, as ⌘K links one).
 */
export function ModelMeasures({ name }) {
  const { data, isLoading } = useModel(name)
  const [, setParams] = useSearchParams()
  if (isLoading) return <SkeletonList />
  if (!data) return null
  const pick = m => {
    const fact = (data.facts || []).find(f => (f.runnable_measures || []).includes(m))
    setParams(fact ? { tab: 'schema', measure: m, table: fact.table } : { tab: 'schema', measure: m })
  }
  return <MeasuresTable model={name} measures={data.measures || []} target={null} answers={answersOf(data)} onPick={pick} />
}

// The inspector with nothing selected: the Semantic layer. What the model is
// about, its grain, its measures, dimensions and example questions in the
// words people and agents use, then its joins, storage, code and the exact
// text an agent receives, folded under them.
function ModelSummary({ name, data, schema, desk, action, view, setView, onPickMeasure }) {
  const grain = grainSentence(data)
  const questions = data.questions || []
  const answers = answersOf(data)
  const measuresRef = useRef(null)
  useEffect(() => { if (view === 'measures') measuresRef.current?.scrollIntoView({ block: 'start' }) }, [view])
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
        <p className="sem-eyebrow">Semantic layer</p>
        <div className="dbx-insp__title"><h2 className="dbx-insp__name dbx-insp__name--sans">{data.label || name}</h2></div>
        {data.description && <p className="sem-lede">{data.description}</p>}
        {grain && <p className="dbx-insp__sub">Grain: {grain}</p>}
        {(data.synonyms || []).length > 0 && <p className="dbx-insp__sub">Also called {data.synonyms.join(', ')}</p>}
        <p className="dbx-insp__sub">
          {count(schema.tables.length, 'table')} · {count(schema.edges.length, 'join')} · {count((data.measures || []).length, 'measure')}
        </p>
        {where.length > 0 && <p className="dbx-insp__sub">Reads {where.map((w, i) => <span key={w}>{i > 0 && ', '}<code>{w}</code></span>)}</p>}
        {desk?.warehouse && sinks.length === 0 && (
          <p className="dbx-insp__sub">{checksWords({ status: 'satisfied' }).text} on its tables when they were last written.</p>
        )}
        {sinks.length > 0 && <p className="dbx-insp__sub">{sinks.map(s => `${s.table}: ${checksWords(s).text}`).join(' · ')}</p>}
        {(data.owners || []).length > 0 && (
          <p className="dbx-insp__sub">Owners: {data.owners.join(', ')} (only they or an admin publish changes to it)</p>
        )}
        {/* Ask this model is the page's, in its header: one per screen. */}
        {action && <div className="dbx-insp__acts">{action}</div>}
      </header>
      <div ref={measuresRef}>
        {/* Their count is said once, in the line above. */}
        <InspectorSection id="measures" title="Measures">
          <MeasuresTable model={name} measures={data.measures || []} target={null} answers={answers} onPick={onPickMeasure} />
        </InspectorSection>
      </div>
      <InspectorSection id="dimensions" title="Dimensions" aside={count((data.dimensions || []).length, 'dimension')}>
        <DimensionsList data={data} />
      </InspectorSection>
      <InspectorSection id="questions" title="Questions">
        {questions.length === 0 ? (
          <p className="dbx-quiet">No example questions. List a few under <code>questions:</code> in the model file: Ask offers them, and an agent reads them.</p>
        ) : (
          <ul className="sem-questions">
            {questions.map(q => <li key={q}><Link to={askPath(name)}>{q}</Link></li>)}
          </ul>
        )}
      </InspectorSection>
      {fold('relationships', <JoinsTable edges={schema.edges} />)}
      {fold('storage', <ModelStorage details={data.connector_details || []} tables={data.tables} hidden={data.hidden_framework_tables} />)}
      {fold('code', <CodeView kind="models" name={name} />)}
      {fold('agent', <AgentContext name={name} />)}
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
  const view = VIEWS.includes(params.get('view')) ? params.get('view') : null
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
  // A measure picked in the Semantic layer selects the fact it runs on (the
  // address's ?measure=, as ⌘K links one).
  const pickMeasure = m => {
    const fact = (data.facts || []).find(f => (f.runnable_measures || []).includes(m))
    setParams(p => {
      const n = new URLSearchParams(p)
      n.set('measure', m)
      n.delete('view')
      if (fact) n.set('table', fact.table); else n.delete('table')
      return n
    })
  }

  return (
    <DataBrowser
      schema={schema} storeKey={`model-${name}`} label={`${data.label || name}: tables, joins and measures`}
      summary={<ModelSummary name={name} data={data} schema={schema} desk={desk} action={action} view={view} setView={setView}
                             onPickMeasure={pickMeasure} />}
      summaryOpen={!!view} infoOf={infoOf} model={name}
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
  const { data: warehouses } = useWarehouses()
  const [params] = useSearchParams()
  const open = pageKey === 'ask' ? askPath : modelPath
  // Old links: /models?m=<model>, /explore?model=<model>.
  const legacy = params.get('m') || params.get('model')
  if (legacy) return <Navigate to={open(legacy)} replace />

  const models = data || []
  const reportCount = name => (reports || []).filter(r => reportBelongsToModel(r, name)).length
  // When its data was refreshed, in the words the Models folder uses.
  const refreshed = name => pipelineRefresh(pipelineFor(pipelines || [], name), writtenFor(warehouses, name)).text

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
                  <span>{refreshed(m.name)}</span>
                </span>
              </Link>
            )
          })}
        </div>
      )}
    </>
  )
}
