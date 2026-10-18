import { useEffect, useMemo, useRef, useState } from 'react'
import { Navigate, useNavigate, useSearchParams } from 'react-router-dom'
import { BarChart, Bar, XAxis, YAxis, LabelList, ResponsiveContainer } from 'recharts'

import {
  reportPath, useAppStatus, useAskAnswer, useDimensionValues, useKeepAnswer, useMe, useModel, useModels,
} from '../api'
import {
  answerColumnLabel, answerColumns, answerShape, canAsk, decodeQuery, definitionOf, dimensionLabel,
  encodeQuery, factOf, keepFiles, keepPath, measureLabel, measureNames, nextSlot, orderWords,
  requestOf, resolve, segments, sentenceOf, suggest, tidy,
} from '../ask'
import { CodeFiles } from '../components/CodeView'
import { PageHeader } from '../components/Scope'
import { Btn, ErrorDetail, SkeletonCard, Spinner, Verdict, useNarrow, useToast } from '../components/Shared'
import { askPath, rememberModel } from '../nav'
import { bindingOf, pythonOf, queryLineOf } from '../queryCode'
import Explore from './Explore'
import Models from './Models'

// Ask: a question of one model, picked here (?model=<name>). The question is a
// sentence of the model's own tokens (ask.js); the answer is the model's query
// API run on it, drawn as a chart, a table or a number, with its definitions
// in words and the verdict an ad hoc query has: Not checked. The question
// lives in the URL (?q=), so a link reproduces it. The app calls no language
// model: plain-English questions are the connected agent's job.
export default function Ask() {
  const { data, isLoading } = useModels()
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const models = data || []
  const asked = params.get('model') || ''
  const known = models.some(m => m.name === asked)
  useEffect(() => { if (known) rememberModel(asked) }, [known, asked])

  if (isLoading) return <SkeletonCard />
  if (!known && models.length === 1) return <Navigate to={askPath(models[0].name)} replace />
  if (!known) return <Models pageKey="ask" />
  return (
    <>
      <PageHeader pageKey="ask">
        {models.length > 1 && (
          <label className="ask-model">
            <span>Model</span>
            <select value={asked} onChange={e => navigate(askPath(e.target.value))}>
              {models.map(m => <option key={m.name} value={m.name}>{m.label || m.name}</option>)}
            </select>
          </label>
        )}
      </PageHeader>
      <AskModel key={asked} name={asked} label={models.find(m => m.name === asked)?.label || asked} />
    </>
  )
}

// ── The recent questions, this browser session ───────────────────────────────

const HISTORY = 5
const historyKey = name => `tracebi.ask.${name}`

function useHistory(name) {
  const [items, setItems] = useState(() => {
    try { return JSON.parse(sessionStorage.getItem(historyKey(name)) || '[]') } catch { return [] }
  })
  const add = (key, sentence) => setItems(prev => {
    const next = [{ key, sentence }, ...prev.filter(h => h.key !== key)].slice(0, HISTORY)
    try { sessionStorage.setItem(historyKey(name), JSON.stringify(next)) } catch { /* private window */ }
    return next
  })
  return [items, add]
}

// ── One model ────────────────────────────────────────────────────────────────

function AskModel({ name, label }) {
  const { data: detail, isLoading } = useModel(name)
  const [params, setParams] = useSearchParams()
  const qParam = params.get('q') || ''
  const asked = useMemo(() => decodeQuery(qParam), [qParam])
  const [draft, setDraft] = useState(() => asked || { measures: [], dimensions: [], filters: {} })
  useEffect(() => { if (asked) setDraft(asked) }, [asked])
  const [history, remember] = useHistory(name)

  const body = asked && detail ? requestOf(detail, asked) : null
  const answer = useAskAnswer(name, qParam, body)
  useEffect(() => {
    if (answer.data && asked && detail) remember(qParam, sentenceOf(detail, asked))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [answer.data])

  const fact = factOf(detail, draft)
  const refs = (detail?.dimensions || []).filter(d => d.name in (fact?.foreign_keys || {}))
    .flatMap(d => (d.attributes || []).map(a => `${d.name}.${a}`))
  const valueQueries = useDimensionValues(name, refs, !!detail)
  const values = Object.fromEntries(refs.map((ref, i) => [ref, valueQueries[i]?.data?.values || []]))

  const { data: me } = useMe()
  const canKeep = me?.role === 'analyst' || me?.role === 'admin'
  const { data: status } = useAppStatus()
  const agent = !!(status?.gateway || status?.build_mode)

  const ask = (q = draft) => {
    const next = tidy({ ...q, fact: q.fact || fact?.name })
    if (!canAsk(next)) return
    const key = encodeQuery(next)
    if (key === qParam) answer.refetch()
    else setParams({ model: name, q: key })
  }
  const change = q => setDraft(tidy(q))

  if (isLoading || !detail) return <SkeletonCard />
  if (!(detail.facts || []).length) {
    return <p className="ask-empty">This model declares no facts, so there is nothing to ask of it yet.</p>
  }
  return (
    <div className="ask">
      <Sentence detail={detail} q={draft} values={values} onChange={change}
                onAsk={() => ask()} busy={answer.isFetching} />
      {agent && <p className="ask-agent">Or ask your agent: it answers from the same definitions.</p>}

      {history.length > 0 && (
        <nav className="ask-history" aria-label="Recent questions">
          <span className="ask-history__label">Recent</span>
          {history.map(h => (
            <button key={h.key} type="button" className="ask-history__item"
                    aria-current={h.key === qParam ? 'true' : undefined}
                    onClick={() => setParams({ model: name, q: h.key })}>{h.sentence}</button>
          ))}
        </nav>
      )}

      {answer.error && <ErrorDetail error={answer.error} />}
      {!asked && <Examples detail={detail} label={label} onAsk={ask} />}
      {asked && answer.isPending && <div className="ask-answer ask-answer--wait"><Spinner size={16} /> Asking {label}…</div>}
      {asked && answer.data && (
        <Answer name={name} label={label} detail={detail} q={asked} body={body} result={answer.data}
                canKeep={canKeep} />
      )}

      <details className="ask-advanced">
        <summary>Advanced: the query builder</summary>
        <Explore model={name} query={{ ...draft, fact: draft.fact || fact?.name }} onChange={change}
                 onRun={() => ask()} ran={asked} result={answer.data} isPending={answer.isFetching} />
      </details>
    </div>
  )
}

// ── The sentence ─────────────────────────────────────────────────────────────

const SLOT_TEXT = {
  measure: 'a measure', dimension: 'a dimension', filter: 'all rows', order: 'in any order', limit: 'all of them',
}
const KIND_TEXT = { measure: 'Measure', dimension: 'Dimension', filter: 'Value', order: 'Order', limit: 'Rows' }

function Token({ kind, label, onPick, onRemove }) {
  return (
    <span className={`ask-token ask-token--${kind}`}>
      <button type="button" className="ask-token__pick" onClick={onPick}>{label}</button>
      <button type="button" className="ask-token__x" aria-label={`Remove ${label}`} onClick={onRemove}>×</button>
    </span>
  )
}

function Slot({ kind, children, onPick }) {
  return <button type="button" className="ask-slot" onClick={onPick}>{children ?? SLOT_TEXT[kind]}</button>
}

/**
 * "Show [measure] by [dimension] for [filter], [order], top [n]": each slot a
 * token the model offers. Typing finds tokens (over labels and descriptions):
 * Enter takes the highlighted one, and "fair value by sector" takes one per
 * part. Enter on an empty input asks; Backspace on it removes the last token.
 */
function Sentence({ detail, q, values, onChange, onAsk, busy }) {
  const [text, setText] = useState('')
  const [scope, setScope] = useState(null)
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(-1)
  const input = useRef(null)

  const segs = segments(text)
  const kind = scope || (!text ? nextSlot(q) : null)
  const list = !open ? [] : text
    ? suggest(detail, q, values, segs[segs.length - 1], segs.length === 1 ? scope : null)
    : kind ? suggest(detail, q, values, null, kind, 60) : []
  useEffect(() => { setActive(text ? 0 : -1) }, [text, scope])

  const focus = slot => { setScope(slot); setOpen(true); setText(''); input.current?.focus() }
  const take = chosen => {
    const r = resolve(detail, q, values, text || '', scope, chosen)
    onChange(r.q)
    setText(r.left)
    setScope(null)
    input.current?.focus()
  }
  const ms = measureNames(q)
  const removeLast = () => {
    if (q.limit) return onChange({ ...q, limit: undefined })
    if (q.order_by?.length) return onChange({ ...q, order_by: undefined })
    const f = Object.keys(q.filters || {})
    if (f.length) { const { [f[f.length - 1]]: _, ...rest } = q.filters; return onChange({ ...q, filters: rest }) }
    if (q.dimensions?.length) return onChange({ ...q, dimensions: q.dimensions.slice(0, -1) })
    if (ms.length) return onChange({ ...q, measures: Array.isArray(q.measures) ? ms.slice(0, -1) : [] })
  }
  const onKey = e => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setOpen(true); setActive(a => Math.min(a + 1, list.length - 1)) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActive(a => Math.max(a - 1, -1)) }
    else if (e.key === 'Escape') { setOpen(false); setScope(null) }
    else if (e.key === 'Backspace' && !text) removeLast()
    else if (e.key === 'Enter') {
      e.preventDefault()
      if (active >= 0 && list[active]) take(list[active])
      else if (text.trim()) take(null)
      else onAsk()
    }
  }

  const filterLabel = (ref, v) => `${dimensionLabel(detail, ref)}: ${Array.isArray(v) ? v.join(' or ') : v}`
  const [order] = q.order_by || []
  return (
    <div className="ask-q">
      <div className="ask-field">
      <div className="ask-sentence" onClick={e => { if (e.target === e.currentTarget) input.current?.focus() }}>
        <span className="ask-word">Show</span>
        {ms.map(m => (
          <Token key={m} kind="measure" label={measureLabel(detail, q, m)} onPick={() => focus('measure')}
                 onRemove={() => onChange({ ...q, measures: Array.isArray(q.measures) ? ms.filter(x => x !== m)
                   : Object.fromEntries(Object.entries(q.measures).filter(([k]) => k !== m)) })} />
        ))}
        <Slot kind="measure" onPick={() => focus('measure')}>{ms.length ? '+' : undefined}</Slot>
        <span className="ask-word">by</span>
        {(q.dimensions || []).map(d => (
          <Token key={d} kind="dimension" label={dimensionLabel(detail, d)} onPick={() => focus('dimension')}
                 onRemove={() => onChange({ ...q, dimensions: q.dimensions.filter(x => x !== d) })} />
        ))}
        {!(q.dimensions || []).length && <Slot kind="dimension" onPick={() => focus('dimension')} />}
        <span className="ask-word">for</span>
        {Object.entries(q.filters || {}).filter(([, v]) => v !== '').map(([ref, v]) => (
          <Token key={ref} kind="filter" label={filterLabel(ref, v)} onPick={() => focus('filter')}
                 onRemove={() => { const { [ref]: _, ...rest } = q.filters; onChange({ ...q, filters: rest }) }} />
        ))}
        {!Object.values(q.filters || {}).some(v => v !== '') && <Slot kind="filter" onPick={() => focus('filter')} />}
        <span className="ask-word" aria-hidden="true">·</span>
        {order
          ? <Token kind="order" label={orderWords(detail, q)} onPick={() => focus('order')}
                   onRemove={() => onChange({ ...q, order_by: undefined })} />
          : <Slot kind="order" onPick={() => focus('order')} />}
        <span className="ask-word" aria-hidden="true">·</span>
        {q.limit > 0
          ? <Token kind="limit" label={`top ${q.limit}`} onPick={() => focus('limit')}
                   onRemove={() => onChange({ ...q, limit: undefined })} />
          : <Slot kind="limit" onPick={() => focus('limit')} />}
        <input
          ref={input}
          className="ask-input"
          role="combobox"
          aria-label="Your question"
          aria-expanded={list.length > 0}
          aria-controls="ask-suggestions"
          aria-activedescendant={active >= 0 && list[active] ? `ask-opt-${active}` : undefined}
          aria-autocomplete="list"
          value={text}
          placeholder={scope ? `Find ${SLOT_TEXT[scope].replace(/^(a|all|in any|all of) /, '')}…`
            : ms.length ? 'Refine: by, for, top 5…' : 'Type a question: fair value by sector'}
          onChange={e => { setText(e.target.value); setOpen(true) }}
          onFocus={() => setOpen(true)}
          // A slot click blurs the input, then focuses it again with its scope.
          onBlur={() => setTimeout(() => {
            if (document.activeElement !== input.current) { setOpen(false); setScope(null) }
          }, 120)}
          onKeyDown={onKey}
        />
      </div>
      {list.length > 0 && (
        <ul id="ask-suggestions" role="listbox" className="ask-list" aria-label="Suggestions">
          {list.map((t, i) => (
            <li key={t.id} id={`ask-opt-${i}`} role="option" aria-selected={i === active}
                className="ask-list__item" onMouseDown={e => { e.preventDefault(); take(t) }}
                onMouseEnter={() => setActive(i)}>
              <span className="ask-list__kind">{KIND_TEXT[t.kind]}</span>
              <span className="ask-list__label">{t.label}</span>
              {t.sub && <span className="ask-list__sub">{t.sub}</span>}
            </li>
          ))}
        </ul>
      )}
      </div>
      <Btn onClick={onAsk} disabled={!canAsk(q) || busy}>
        {busy ? <><Spinner size={14} /> Asking…</> : 'Ask'}
      </Btn>
    </div>
  )
}

// ── Before a question: three the model can answer ────────────────────────────

function Examples({ detail, label, onAsk }) {
  const fact = factOf(detail, {})
  const runs = (detail.measures || []).filter(m => fact?.runnable_measures?.includes(m.name)).map(m => m.name)
  const refs = (detail.dimensions || []).filter(d => d.name in (fact?.foreign_keys || {}))
    .flatMap(d => (d.attributes || []).map(a => `${d.name}.${a}`))
  const base = { fact: fact?.name, measures: runs.slice(0, 1), dimensions: [], filters: {} }
  const examples = runs.length ? [
    base,
    refs[0] && { ...base, dimensions: [refs[refs.length - 1]], order_by: [{ column: runs[0], desc: true }] },
    refs[0] && runs[1] && { ...base, measures: runs.slice(0, 2), dimensions: [refs[0]], order_by: [{ column: runs[0], desc: true }], limit: 5 },
  ].filter(Boolean) : []
  return (
    <div className="ask-start">
      <p>
        Pick a measure and what to break it down by, or type and pick from what {label} defines.
        Every number is a query of the model&rsquo;s own definitions.
      </p>
      {examples.length > 0 && (
        <div className="ask-start__examples">
          {examples.map(q => (
            <button key={encodeQuery(q)} type="button" className="ask-history__item" onClick={() => onAsk(q)}>
              {sentenceOf(detail, q)}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

// ── The answer ───────────────────────────────────────────────────────────────

// Category labels wrap rather than cut: words onto up to three lines.
function wrapWords(text, chars) {
  const lines = []
  for (const word of String(text).split(' ')) {
    const last = lines[lines.length - 1]
    if (last && (last + ' ' + word).length <= chars) lines[lines.length - 1] = `${last} ${word}`
    else lines.push(word)
  }
  return lines
}

function AnswerBars({ result, dim, measure, label }) {
  const narrow = useNarrow()
  const axis = narrow ? 112 : 200
  const chars = Math.floor(axis / 7)
  const data = result.data.map((r, i) => ({
    name: r[dim] == null ? '(none)' : String(r[dim]),
    lines: wrapWords(r[dim] == null ? '(none)' : r[dim], chars),
    value: r[measure],
    text: result.display[i][measure],
  }))
  const tall = Math.max(...data.map(d => d.lines.length))
  const band = Math.max(34, tall * 15 + 10)
  const Tick = ({ x, y, payload, index }) => {
    const lines = data[index]?.lines || [payload.value]
    return (
      <text x={x - 8} y={y - ((lines.length - 1) * 15) / 2} textAnchor="end" dominantBaseline="middle"
            fontSize={12} fill="var(--text-2)">
        {lines.map((l, i) => <tspan key={i} x={x - 8} dy={i ? 15 : 0}>{l}</tspan>)}
      </text>
    )
  }
  return (
    <figure className="ask-bars" aria-label={label}>
      <ResponsiveContainer width="100%" height={data.length * band + 8}>
        <BarChart data={data} layout="vertical" margin={{ top: 4, right: 104, left: 0, bottom: 4 }}>
          <XAxis type="number" hide domain={[dataMin => Math.min(0, dataMin), 'auto']} />
          <YAxis type="category" dataKey="name" width={axis} tick={<Tick />} interval={0}
                 axisLine={false} tickLine={false} />
          {/* The bar is 55% of its band (the report's chart style). */}
          <Bar dataKey="value" fill="var(--chart-1)" radius={[0, 2, 2, 0]} barSize={Math.min(22, Math.round(band * 0.55))}
               isAnimationActive={false}>
            <LabelList dataKey="text" position="right" offset={8}
                       style={{ fontSize: 12, fill: 'var(--text)', fontVariantNumeric: 'tabular-nums' }} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </figure>
  )
}

function AnswerTable({ detail, q, result }) {
  const cols = answerColumns(q, result)
  const numeric = c => result.data.some(r => typeof r[c] === 'number')
  return (
    <div className="ask-table" tabIndex={0} role="region" aria-label="The answer's rows">
      <table>
        <thead>
          <tr>{cols.map(c => <th key={c} className={numeric(c) ? 'num' : undefined}>{answerColumnLabel(detail, q, c)}</th>)}</tr>
        </thead>
        <tbody>
          {result.data.map((row, i) => (
            <tr key={i}>
              {cols.map(c => (
                <td key={c} className={numeric(c) ? 'num' : undefined}>
                  {row[c] == null ? <span className="ask-null">none</span> : result.display[i][c]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function AnswerNumbers({ detail, q, result }) {
  return (
    <div className="ask-numbers">
      {measureNames(q).filter(m => result.columns.includes(m)).map((m, i) => (
        <div key={m} className={`ask-number${i ? '' : ' ask-number--lead'}`}>
          <div className="ask-number__label">{measureLabel(detail, q, m)}</div>
          <div className="ask-number__value">{result.data[0][m] == null ? 'none' : result.display[0][m]}</div>
        </div>
      ))}
    </div>
  )
}

function Answer({ name, label, detail, q, body, result, canKeep }) {
  const shape = answerShape(q, result)
  const [view, setView] = useState('chart')
  const sentence = sentenceOf(detail, q)
  const keep = useKeepAnswer()
  const navigate = useNavigate()
  const toast = useToast()
  const verdictDetail = `A live query against ${label}; built reports re-run and are checked — this answer is not.`

  const onKeep = () => keep.mutate({
    pathFor: taken => keepPath(name, q, taken),
    files: keepFiles({ model: name, modelLabel: label, detail, q, rows: result.rows }),
  }, {
    onSuccess: d => navigate(`/drafts/${encodeURIComponent(d.owner)}/${d.kind}/${reportPath(d.path)}`),
    onError: err => toast(err.message, 'error'),
  })

  return (
    <section className="ask-answer fade-in" aria-label="The answer">
      <div className="ask-answer__head">
        <h2 className="ask-answer__sentence">
          {sentence}<span className="ask-answer__rows"> — {result.rows} {result.rows === 1 ? 'row' : 'rows'}</span>
        </h2>
        <Verdict state="not-checked" detail={verdictDetail} />
      </div>

      {result.rows === 0 ? (
        <p className="ask-empty">No rows answer this question. Nothing matched its filters.</p>
      ) : shape === 'number' ? (
        <AnswerNumbers detail={detail} q={q} result={result} />
      ) : shape === 'chart' && view === 'chart' ? (
        <AnswerBars result={result} dim={q.dimensions[0]} measure={measureNames(q)[0]} label={sentence} />
      ) : (
        <AnswerTable detail={detail} q={q} result={result} />
      )}
      {shape === 'chart' && result.rows > 0 && (
        <div className="seg ask-view" role="group" aria-label="Show the answer as">
          <button type="button" aria-pressed={view === 'chart'} onClick={() => setView('chart')}>Chart</button>
          <button type="button" aria-pressed={view === 'table'} onClick={() => setView('table')}>Table</button>
        </div>
      )}

      <dl className="ask-defs">
        {measureNames(q).map(m => {
          const d = definitionOf(detail, q, m)
          const words = [d.description, d.how].filter(Boolean).join(': ')
          return (
            <div key={m} className="ask-defs__row">
              <dt>{d.label}</dt>
              <dd>{words ? `${words}.` : 'The model gives no definition in words.'}</dd>
            </div>
          )
        })}
      </dl>

      <p className="ask-check">
        <code className="ask-query">{queryLineOf(body)}</code>
        <span>{verdictDetail}</span>
      </p>
      <details className="ask-code">
        <summary>The query as code</summary>
        <CodeFiles
          hint="The same query three ways: the body sent to the model, Python, or a report's data block."
          files={[
            { path: 'POST /api/models/' + name + '/query', label: 'JSON', content: JSON.stringify(body, null, 2) + '\n' },
            { path: 'Python · DataModel.query()', label: 'Python', content: pythonOf(name, body) },
            { path: 'report.json · a data binding', label: 'report.json', content: bindingOf(name, body) },
          ]} />
      </details>

      {canKeep && (
        <div className="ask-keep">
          <Btn onClick={onKeep} disabled={keep.isPending}>{keep.isPending ? 'Keeping…' : 'Keep this'}</Btn>
          <span>Opens a draft report of this one figure. The draft holds the question, not these numbers: it runs the query when built.</span>
        </div>
      )}
    </section>
  )
}
