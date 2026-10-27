import { useLayoutEffect, useRef, useState } from 'react'
import { area, line, max, min, scalePoint, scaleLinear } from 'd3'

import { useModel, useTablePreview } from '../api'
import AnswerChart from '../components/AnswerChart'
import { LineageGraph } from '../components/Lineage'
import { count } from '../format'
import {
  Card, CardTitle, Badge, Spinner,
  Empty, Btn, ErrorDetail, ExportCsv, SkeletonCard,
} from '../components/Shared'

const AGG_FUNCS = ['sum', 'count', 'mean', 'min', 'max', 'nunique']
// Series identity, not meaning: ink first, then a restrained set. Tokens, so each
// has a dark value (--chart-1..6 in global.css).
const MEASURE_COLORS = ['var(--chart-1)', 'var(--chart-2)', 'var(--chart-3)', 'var(--chart-4)', 'var(--chart-5)', 'var(--chart-6)']

// ── Builder controls ─────────────────────────────────────────────────────────

function SectionLabel({ children }) {
  return (
    <div style={{
      fontSize: 'var(--text-eyebrow)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: .8,
      color: 'var(--muted)', margin: '18px 0 8px',
    }}>{children}</div>
  )
}

function CheckRow({ checked, onToggle, label, sub, right, disabled }) {
  return (
    <label title={sub || undefined} style={{
      display: 'flex', alignItems: 'center', gap: 9, padding: sub ? '3px 10px' : '6px 10px',
      borderRadius: 'var(--radius)', cursor: disabled ? 'default' : 'pointer', fontSize: 'var(--text-caption)',
      background: checked ? 'var(--blue-lt)' : 'transparent',
      border: `1px solid ${checked ? 'var(--blue-br)' : 'transparent'}`,
      transition: 'background var(--t)',
    }}>
      <input type="checkbox" checked={checked} onChange={onToggle} disabled={disabled}
        style={{ accentColor: 'var(--ink)' }} />
      <span style={{ display: 'flex', flexDirection: 'column', minWidth: 0, lineHeight: 1.3 }}>
        <span style={{ color: checked ? 'var(--text)' : 'var(--text-2)', fontFamily: 'var(--font-mono)', fontSize: 'var(--text-sm)' }}>
          {label}
        </span>
        {/* One line, cut with an ellipsis; the whole text is the row's tooltip. */}
        {sub && (
          <span style={{
            fontSize: 'var(--text-sm)', color: 'var(--muted)',
            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          }}>{sub}</span>
        )}
      </span>
      {right && <span style={{ marginLeft: 'auto' }}>{right}</span>}
    </label>
  )
}

const selectStyle = {
  background: 'var(--surface)', color: 'var(--accent-text)', border: '1px solid var(--border)',
  borderRadius: 'var(--radius-sm)', fontSize: 'var(--text-xs)', padding: '3px 6px', cursor: 'pointer',
}

// A filter typed as a number matches a numeric column: "12" is 12, "1." stays
// text until it is a number.
const typed = v => (/^-?\d+(\.\d+)?$/.test(v.trim()) ? Number(v) : v)

function FilterRows({ columns, filters, setFilters }) {
  const entries = Object.entries(filters)
  const addFilter = () => {
    const unused = columns.find(c => !(c in filters))
    if (unused) setFilters({ ...filters, [unused]: '' })
  }
  const setKey = (oldKey, newKey) => {
    const next = {}
    for (const [k, v] of Object.entries(filters)) next[k === oldKey ? newKey : k] = v
    setFilters(next)
  }
  return (
    <div>
      {entries.map(([col, val]) => (
        <div key={col} style={{ display: 'flex', gap: 6, marginBottom: 6, alignItems: 'center' }}>
          <select value={col} onChange={e => setKey(col, e.target.value)} style={selectStyle}>
            {columns.filter(c => c === col || !(c in filters)).map(c =>
              <option key={c} value={c}>{c}</option>)}
          </select>
          <span style={{ color: 'var(--muted)', fontSize: 'var(--text-sm)' }}>=</span>
          <input
            value={Array.isArray(val) ? val.join(', ') : String(val)}
            onChange={e => setFilters({ ...filters, [col]: typed(e.target.value) })}
            placeholder="value"
            style={{
              flex: 1, minWidth: 60, background: 'var(--surface)', color: 'var(--text)',
              border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', fontSize: 'var(--text-sm)', padding: '4px 8px',
            }}
          />
          <button onClick={() => {
            const next = { ...filters }; delete next[col]; setFilters(next)
          }} style={{
            background: 'none', border: 'none', color: 'var(--muted)', cursor: 'pointer', fontSize: 'var(--text-base)',
          }}>×</button>
        </div>
      ))}
      <button onClick={addFilter} disabled={entries.length >= columns.length} style={{
        background: 'none', border: '1px dashed var(--border)', color: 'var(--muted)',
        borderRadius: 'var(--radius)', padding: '5px 12px', fontSize: 'var(--text-sm)', cursor: 'pointer', width: '100%',
      }}>+ Add filter</button>
    </div>
  )
}

// ── Result chart ─────────────────────────────────────────────────────────────

const fmtTick = v => v >= 1e6 ? `${(v / 1e6).toFixed(1)}M` : v >= 1e3 ? `${(v / 1e3).toFixed(0)}K` : String(v)

function ChartTypeToggle({ type, onChange }) {
  const types = [
    { id: 'bar',  label: '▥', title: 'Bar chart' },
    { id: 'line', label: '∿', title: 'Line chart' },
    { id: 'area', label: '◮', title: 'Area chart' },
  ]
  return (
    <div style={{
      display: 'inline-flex', gap: 2, padding: 2,
      background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 'var(--radius)',
    }}>
      {types.map(t => (
        <button key={t.id} onClick={() => onChange(t.id)} title={t.title} style={{
          border: 'none', borderRadius: 'var(--radius-sm)', cursor: 'pointer',
          padding: '3px 10px', fontSize: 'var(--text-caption)', lineHeight: 1.4,
          background: type === t.id ? 'var(--card)' : 'transparent',
          color: type === t.id ? 'var(--accent-text)' : 'var(--muted)',
          fontWeight: type === t.id ? 700 : 400,
          boxShadow: type === t.id ? 'var(--shadow-sm)' : 'none',
          transition: 'background var(--t), color var(--t)',
        }}>{t.label}</button>
      ))}
    </div>
  )
}

// A line or an area over the categories in the order the rows came, one
// series per measure, drawn as the bar chart is: React draws the SVG, d3 gives
// the scales and the paths. Each point's title is the server's text for it.
function TrendChart({ rows, columns, area: filled }) {
  const box = useRef(null)
  const [width, setWidth] = useState(0)
  useLayoutEffect(() => {
    const ro = new ResizeObserver(([e]) => setWidth(e.contentRect.width))
    ro.observe(box.current)
    return () => ro.disconnect()
  }, [])
  const height = 300
  const m = { top: 8, right: 16, bottom: 24, left: 52 }
  const x = scalePoint().domain(rows.map((_, i) => i)).range([m.left, Math.max(m.left, width - m.right)]).padding(0.3)
  const all = columns.flatMap(c => rows.map(r => r[c])).filter(v => typeof v === 'number')
  const y = scaleLinear().domain([Math.min(0, min(all) ?? 0), Math.max(0, max(all) ?? 0) || 1]).nice(5)
    .range([height - m.bottom, m.top])
  // Label every k-th category so the names never collide.
  const every = Math.max(1, Math.ceil(rows.length / Math.max(1, Math.floor((width - m.left) / 90))))
  const defined = (r, c) => typeof r[c] === 'number'
  return (
    <div ref={box} className="trend-chart">
      {width > 0 && (
        <svg width={width} height={height} role="img"
             aria-label={`${columns.join(', ')} across ${rows.length} ${rows.length === 1 ? 'value' : 'values'}`}>
          {y.ticks(5).map(t => (
            <g key={t}>
              <line x1={m.left} x2={width - m.right} y1={y(t)} y2={y(t)}
                    className={t === 0 ? 'trend-chart__zero' : 'trend-chart__grid'} />
              <text x={m.left - 8} y={y(t)} className="trend-chart__tick" textAnchor="end">{fmtTick(t)}</text>
            </g>
          ))}
          {rows.map((r, i) => i % every === 0 && (
            <text key={i} x={x(i)} y={height - 6} className="trend-chart__tick" textAnchor="middle">{r._label}</text>
          ))}
          {columns.map((col, ci) => {
            const c = MEASURE_COLORS[ci % MEASURE_COLORS.length]
            const pts = rows.map((r, i) => [i, r]).filter(([, r]) => defined(r, col))
            const path = line().x(([i]) => x(i)).y(([, r]) => y(r[col]))(pts)
            const fill = filled && area().x(([i]) => x(i)).y0(y(0)).y1(([, r]) => y(r[col]))(pts)
            return (
              <g key={col}>
                {fill && <path d={fill} fill={c} fillOpacity={0.18} />}
                <path d={path} fill="none" stroke={c} strokeWidth={2.2} />
                {pts.map(([i, r]) => (
                  <circle key={i} cx={x(i)} cy={y(r[col])} r={3} fill={c}>
                    <title>{`${r._label}, ${col}: ${r._display[col]}`}</title>
                  </circle>
                ))}
              </g>
            )
          })}
        </svg>
      )}
    </div>
  )
}

function ResultChart({ data, display, dimCol, measureCols, type = 'bar' }) {
  if (!data.length || !dimCol || !measureCols.length) return null

  // Bars: one chart per measure, each with its own scale and its own numbers.
  if (type === 'bar') {
    return (
      <div style={{ marginTop: 8, marginBottom: 4 }}>
        {measureCols.map(col => (
          <div key={col}>
            {measureCols.length > 1 && <div className="explore-note" style={{ margin: '8px 0 4px' }}>{col}</div>}
            <AnswerChart label={col} rows={data.map((row, i) => ({
              label: row[dimCol] == null ? '(none)' : String(row[dimCol]),
              value: row[col],
              display: display[i][col],
            }))} />
          </div>
        ))}
      </div>
    )
  }

  const rows = data.map((row, i) => ({ ...row, _label: String(row[dimCol]).slice(0, 20), _display: display[i] }))
  return (
    <div style={{ marginTop: 8, marginBottom: 4 }}>
      {measureCols.length > 1 && (
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', fontSize: 'var(--text-xs)', color: 'var(--muted)', marginBottom: 6 }}>
          {measureCols.map((col, ci) => (
            <span key={col} style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
              <span style={{ width: 14, height: 3, borderRadius: 2, background: MEASURE_COLORS[ci % MEASURE_COLORS.length] }} />
              {col}
            </span>
          ))}
        </div>
      )}
      <TrendChart rows={rows} columns={measureCols} area={type === 'area'} />
    </div>
  )
}

function downloadCsv(result) {
  const esc = v => {
    const s = v == null ? '' : String(v)
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
  }
  const lines = [result.columns.join(',')]
  for (const row of result.data) lines.push(result.columns.map(c => esc(row[c])).join(','))
  const blob = new Blob([lines.join('\n')], { type: 'text/csv' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `${result.fact}_query.csv`
  a.click()
  URL.revokeObjectURL(a.href)
}

// ── Page ─────────────────────────────────────────────────────────────────────

/**
 * Ask's Advanced: the query builder over one model's star schema. It edits
 * the same question as Ask's sentence (*query*, changed through *onChange*),
 * and Run asks it (*onRun*); *ran*, *result*, *error* and *isPending* are the
 * question last asked and its answer.
 */
export default function Explore({ model: activeModel, query, onChange, onRun, ran, result, error, isPending }) {
  const { data: model, isLoading: loadingModel } = useModel(activeModel)

  const facts = model?.facts || []
  const dims = model?.dimensions || []
  const fact = facts.find(f => f.name === query.fact) || facts[0]

  // A query names the model's measures (a list) or aggregates raw columns
  // (a {col: agg} map): the API takes one form per request, so a run uses one.
  const named = Array.isArray(query.measures) ? query.measures : []          // ["fair_value", ...]
  const measures = Array.isArray(query.measures) ? {} : query.measures || {} // {col: agg} — "Other columns"
  const dimAttrs = query.dimensions || []                                    // ["dim.attr"]
  const filters = query.filters || {}                                        // {col: value}
  const set = part => onChange({ ...query, fact: fact?.name, ...part })
  const setFilters = next => set({ filters: next })
  const setMeasures = next => set({ measures: Object.keys(next).length ? next : named })
  const [chartType, setChartType] = useState('bar')   // bar | line | area

  // Fact table columns (for filters) come from a 1-row preview.
  const { data: factPreview } = useTablePreview(activeModel, fact?.table)
  const factColumns = factPreview?.columns || []

  // The model's declared measures this fact can run (the model says which), and
  // the dimensions it joins (its foreign_keys): a query can group by only those.
  const offered = (model?.measures || []).filter(m => fact?.runnable_measures?.includes(m.name))
  const joined = dims.filter(d => d.name in (fact?.foreign_keys || {}))
  const toggleNamed = name =>
    set({ measures: named.includes(name) ? named.filter(n => n !== name) : [...named, name] })
  const toggleMeasure = col => {
    const next = { ...measures }
    if (col in next) delete next[col]
    else next[col] = 'sum'
    setMeasures(next)
  }
  const toggleDimAttr = ref =>
    set({ dimensions: dimAttrs.includes(ref) ? dimAttrs.filter(d => d !== ref) : [...dimAttrs, ref] })

  const selectFact = name =>
    onChange({ fact: name, measures: [], dimensions: [], filters: {} })

  const adHoc = Object.keys(measures).length > 0
  const canRun = fact && (named.length > 0 || adHoc)
  const handleRun = onRun

  // The columns the request asked for (a ratio's inputs come back too, as table columns only).
  const asked = Array.isArray(ran?.measures) ? ran.measures : Object.keys(ran?.measures || {})
  const measureCols = result ? result.columns.filter(c => asked.includes(c)) : []
  // One axis, one unit: chart the measures that share the first one's declared
  // format (dollars with dollars); the rest are in the table.
  const unitOf = c => (model?.measures || []).find(m => m.name === c)?.format ?? null
  const chartCols = Array.isArray(ran?.measures)
    ? measureCols.filter(c => unitOf(c) === unitOf(measureCols[0]))
    : measureCols
  const chartDim = result && ran?.dimensions?.length === 1 ? ran.dimensions[0] : null

  if (loadingModel) return <SkeletonCard />

  return (
      <>
      {facts.length === 0 && !loadingModel ? (
        <Empty
          message="No facts defined on this model. Tag tables with model.add_fact() / model.add_dimension() to enable Explore."
        />
      ) : (
        <div className="explore-grid">
          {/* ── Builder ── */}
          <Card>
            <CardTitle>Query Builder</CardTitle>

            <SectionLabel>Fact</SectionLabel>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              {facts.map(f => (
                <button key={f.name} onClick={() => selectFact(f.name)} style={{
                  padding: '6px 12px', borderRadius: 'var(--radius)', fontSize: 'var(--text-sm)', fontWeight: 600, cursor: 'pointer',
                  background: fact?.name === f.name ? 'var(--blue-lt)' : 'var(--surface-2)',
                  color: fact?.name === f.name ? 'var(--accent-text)' : 'var(--muted)',
                  border: `1px solid ${fact?.name === f.name ? 'var(--blue-br)' : 'var(--border)'}`,
                }}>{f.name}</button>
              ))}
            </div>

            {fact && (
              <>
                <SectionLabel>Measures</SectionLabel>
                {offered.map(m => (
                  <CheckRow
                    key={m.name}
                    checked={named.includes(m.name)}
                    onToggle={() => toggleNamed(m.name)}
                    disabled={adHoc}
                    label={m.name}
                    sub={m.description}
                  />
                ))}
                {offered.length === 0 && (
                  <p className="explore-note">
                    {model.measures?.length ? `None of this model's measures run on ${fact.name}.` : 'This model declares no measures.'}
                  </p>
                )}
                {adHoc && offered.length > 0 && (
                  <p className="explore-note">Clear the other columns to pick measures.</p>
                )}

                <details className="explore-more" open={offered.length === 0}>
                  <summary>Other columns</summary>
                  <p className="explore-note">
                    A raw column of {fact.table}, aggregated here.
                    {offered.length > 0 && " It can't be combined with the measures above."}
                  </p>
                  {fact.measures.map(col => (
                    <CheckRow
                      key={col}
                      checked={col in measures}
                      onToggle={() => toggleMeasure(col)}
                      disabled={named.length > 0}
                      label={col}
                      right={col in measures && (
                        <select
                          value={measures[col]}
                          onClick={e => e.stopPropagation()}
                          onChange={e => setMeasures({ ...measures, [col]: e.target.value })}
                          style={selectStyle}
                        >
                          {AGG_FUNCS.map(a => <option key={a} value={a}>{a}</option>)}
                        </select>
                      )}
                    />
                  ))}
                </details>

                <SectionLabel>Group by</SectionLabel>
                {joined.length === 0 && (
                  <p style={{ fontSize: 'var(--text-sm)', color: 'var(--muted)' }}>
                    {dims.length === 0 ? 'No dimensions defined.' : `No dimension is joined to ${fact.name}.`}
                  </p>
                )}
                {joined.map(d => (
                  <div key={d.name} style={{ marginBottom: 6 }}>
                    <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-2)', margin: '4px 0 2px', fontWeight: 600 }}>
                      {d.name} <span style={{ color: 'var(--muted)', fontWeight: 400 }}>· {d.table}</span>
                    </div>
                    {d.attributes.map(attr => {
                      const ref = `${d.name}.${attr}`
                      return (
                        <CheckRow key={ref} checked={dimAttrs.includes(ref)}
                          onToggle={() => toggleDimAttr(ref)} label={attr} />
                      )
                    })}
                  </div>
                ))}

                <SectionLabel>Filters (on {fact.table})</SectionLabel>
                <FilterRows columns={factColumns} filters={filters} setFilters={setFilters} />

                <div className="explore-run">
                  <Btn onClick={handleRun} disabled={!canRun || isPending} style={{ width: '100%', justifyContent: 'center' }}>
                    {isPending ? <><Spinner size={14} /> Running…</> : '▶ Run query'}
                  </Btn>
                  {!canRun && (
                    <p style={{ fontSize: 'var(--text-xs)', color: 'var(--muted)', marginTop: 8, textAlign: 'center' }}>
                      Select at least one measure to run.
                    </p>
                  )}
                </div>
              </>
            )}
          </Card>

          {/* ── Results ── */}
          <div>
            {error && <ErrorDetail error={error} />}

            {!result && !error && (
              <Card>
                <Empty
                  message="Results appear here. Every query you build is executed with full lineage tracking — you'll see exactly how the numbers were produced."
                />
              </Card>
            )}

            {result && (
              <div className="fade-in">
                <Card>
                  <CardTitle action={
                    <ExportCsv onClick={() => downloadCsv(result)} />
                  }>
                    Result
                  </CardTitle>
                  <div style={{ display: 'flex', gap: 8, marginBottom: 14, flexWrap: 'wrap' }}>
                    <Badge variant="gray">{count(result.rows, 'row')}</Badge>
                    {result.engine && <Badge variant={result.engine === 'duckdb' ? 'green' : 'blue'}>engine: {result.engine}</Badge>}
                    <Badge variant="gray">{result.elapsed_ms} ms</Badge>
                  </div>

                  {chartDim && chartCols.length > 0 && (
                    <>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12 }}>
                        <span className="explore-note" style={{ margin: 0 }}>
                          {chartCols.length < measureCols.length &&
                            `Charting ${chartCols.join(', ')}. The other measures are in a different unit, so they are in the table only.`}
                        </span>
                        <ChartTypeToggle type={chartType} onChange={setChartType} />
                      </div>
                      <ResultChart data={result.data} display={result.display} dimCol={chartDim}
                        measureCols={chartCols} type={chartType} />
                    </>
                  )}

                  <div style={{ overflowX: 'auto', borderRadius: 'var(--radius)', border: '1px solid var(--border)', marginTop: chartDim ? 14 : 0 }}>
                    <table>
                      <thead><tr>{result.columns.map(c => <th key={c}>{c}</th>)}</tr></thead>
                      <tbody>
                        {result.data.map((row, i) => (
                          <tr key={i}>
                            {result.columns.map(c => (
                              <td key={c} style={typeof row[c] === 'number' ? { fontVariantNumeric: 'tabular-nums' } : undefined}>
                                {row[c] == null
                                  ? <span style={{ color: 'var(--muted)', fontStyle: 'italic' }}>null</span>
                                  : result.display[i][c]}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </Card>

                <Card>
                  <CardTitle>How this number was made</CardTitle>
                  <p style={{ fontSize: 'var(--text-sm)', color: 'var(--muted)', marginBottom: 12 }}>
                    Full lineage of the query you just ran — loads, joins, filters, and aggregation.
                  </p>
                  <LineageGraph graph={result.lineage_graph} height={300} />
                </Card>
              </div>
            )}
          </div>
        </div>
      )}
      </>
  )
}
