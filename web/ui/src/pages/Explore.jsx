import { useState } from 'react'
import {
  BarChart, Bar, LineChart, Line, AreaChart, Area,
  XAxis, YAxis, CartesianGrid, Tooltip,
  Legend, ResponsiveContainer,
} from 'recharts'

import { useModels, useModel, useTablePreview, useRunQuery } from '../api'
import { LineageGraph } from '../components/Lineage'
import {
  PageTitle, PageSub, Card, CardTitle, Badge, Spinner,
  Empty, Btn, ErrorDetail, SkeletonCard,
} from '../components/Shared'

const AGG_FUNCS = ['sum', 'count', 'mean', 'min', 'max', 'nunique']
const MEASURE_COLORS = ['#2563eb', '#7c3aed', '#059669', '#d97706', '#db2777', '#0891b2']

// ── Builder controls ─────────────────────────────────────────────────────────

function SectionLabel({ children }) {
  return (
    <div style={{
      fontSize: 10.5, fontWeight: 700, textTransform: 'uppercase', letterSpacing: .8,
      color: 'var(--muted)', margin: '18px 0 8px',
    }}>{children}</div>
  )
}

function CheckRow({ checked, onToggle, label, right }) {
  return (
    <label style={{
      display: 'flex', alignItems: 'center', gap: 9, padding: '6px 10px',
      borderRadius: 6, cursor: 'pointer', fontSize: 13,
      background: checked ? 'var(--blue-lt)' : 'transparent',
      border: `1px solid ${checked ? 'var(--blue-br)' : 'transparent'}`,
      transition: 'background var(--t)',
    }}>
      <input type="checkbox" checked={checked} onChange={onToggle} style={{ accentColor: '#3b82f6' }} />
      <span style={{ color: checked ? 'var(--text)' : 'var(--text-2)', fontFamily: 'Cascadia Code, Fira Code, monospace', fontSize: 12 }}>
        {label}
      </span>
      {right && <span style={{ marginLeft: 'auto' }}>{right}</span>}
    </label>
  )
}

const selectStyle = {
  background: 'var(--surface)', color: 'var(--accent-text)', border: '1px solid var(--border)',
  borderRadius: 5, fontSize: 11, padding: '3px 6px', cursor: 'pointer',
}

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
          <span style={{ color: 'var(--muted)', fontSize: 12 }}>=</span>
          <input
            value={val}
            onChange={e => setFilters({ ...filters, [col]: e.target.value })}
            placeholder="value"
            style={{
              flex: 1, minWidth: 60, background: 'var(--surface)', color: 'var(--text)',
              border: '1px solid var(--border)', borderRadius: 5, fontSize: 12, padding: '4px 8px',
            }}
          />
          <button onClick={() => {
            const next = { ...filters }; delete next[col]; setFilters(next)
          }} style={{
            background: 'none', border: 'none', color: 'var(--muted)', cursor: 'pointer', fontSize: 14,
          }}>×</button>
        </div>
      ))}
      <button onClick={addFilter} disabled={entries.length >= columns.length} style={{
        background: 'none', border: '1px dashed var(--border)', color: 'var(--muted)',
        borderRadius: 6, padding: '5px 12px', fontSize: 12, cursor: 'pointer', width: '100%',
      }}>+ Add filter</button>
    </div>
  )
}

// ── Result chart (Recharts) ──────────────────────────────────────────────────

const fmtTick = v => v >= 1e6 ? `${(v / 1e6).toFixed(1)}M` : v >= 1e3 ? `${(v / 1e3).toFixed(0)}K` : String(v)

const tooltipStyle = {
  background: 'var(--card)', border: '1px solid var(--border)',
  borderRadius: 8, fontSize: 12, color: 'var(--text)',
}

const fmtValue = (v, name) => [
  typeof v === 'number' ? v.toLocaleString(undefined, { maximumFractionDigits: 2 }) : v,
  name,
]

function ChartTypeToggle({ type, onChange }) {
  const types = [
    { id: 'bar',  label: '▥', title: 'Bar chart' },
    { id: 'line', label: '∿', title: 'Line chart' },
    { id: 'area', label: '◮', title: 'Area chart' },
  ]
  return (
    <div style={{
      display: 'inline-flex', gap: 2, padding: 2,
      background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 7,
    }}>
      {types.map(t => (
        <button key={t.id} onClick={() => onChange(t.id)} title={t.title} style={{
          border: 'none', borderRadius: 5, cursor: 'pointer',
          padding: '3px 10px', fontSize: 13, lineHeight: 1.4,
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

function ResultChart({ data, dimCol, measureCols, type = 'bar' }) {
  if (!data.length || !dimCol || !measureCols.length) return null

  // Trim long dimension labels for the axis
  const trimmed = data.map(row => ({
    ...row,
    _label: String(row[dimCol]).slice(0, 20),
  }))

  const grid = <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" horizontal={type !== 'bar'} vertical={type === 'bar'} />
  const tooltip = <Tooltip contentStyle={tooltipStyle} formatter={fmtValue} labelFormatter={() => ''} />
  const legend = measureCols.length > 1
    ? <Legend wrapperStyle={{ fontSize: 11, color: 'var(--muted)', paddingTop: 8 }} />
    : null

  const height = type === 'bar'
    ? Math.max(220, Math.min(400, data.length * 42))
    : 300

  let chart
  if (type === 'bar') {
    chart = (
      <BarChart data={trimmed} margin={{ top: 4, right: 16, left: 0, bottom: 4 }}
        layout="vertical" barCategoryGap="28%">
        {grid}
        <XAxis type="number" tick={{ fontSize: 11, fill: 'var(--muted)' }}
          tickFormatter={fmtTick} axisLine={false} tickLine={false} />
        <YAxis type="category" dataKey="_label" width={110}
          tick={{ fontSize: 11, fill: 'var(--text-2)' }} axisLine={false} tickLine={false} />
        {tooltip}{legend}
        {measureCols.map((col, ci) => (
          <Bar key={col} dataKey={col} fill={MEASURE_COLORS[ci % MEASURE_COLORS.length]}
            radius={[0, 4, 4, 0]} maxBarSize={28} />
        ))}
      </BarChart>
    )
  } else {
    const axes = (
      <>
        <XAxis dataKey="_label" tick={{ fontSize: 11, fill: 'var(--text-2)' }}
          axisLine={false} tickLine={false} interval="preserveStartEnd" />
        <YAxis tick={{ fontSize: 11, fill: 'var(--muted)' }}
          tickFormatter={fmtTick} axisLine={false} tickLine={false} width={52} />
      </>
    )
    chart = type === 'line' ? (
      <LineChart data={trimmed} margin={{ top: 8, right: 16, left: 0, bottom: 4 }}>
        {grid}{axes}{tooltip}{legend}
        {measureCols.map((col, ci) => (
          <Line key={col} dataKey={col} stroke={MEASURE_COLORS[ci % MEASURE_COLORS.length]}
            strokeWidth={2.2} dot={{ r: 3 }} activeDot={{ r: 5 }} />
        ))}
      </LineChart>
    ) : (
      <AreaChart data={trimmed} margin={{ top: 8, right: 16, left: 0, bottom: 4 }}>
        {grid}{axes}{tooltip}{legend}
        {measureCols.map((col, ci) => {
          const c = MEASURE_COLORS[ci % MEASURE_COLORS.length]
          return <Area key={col} dataKey={col} stroke={c} fill={c} fillOpacity={0.18} strokeWidth={2} />
        })}
      </AreaChart>
    )
  }

  return (
    <div style={{ marginTop: 8, marginBottom: 4 }}>
      <ResponsiveContainer width="100%" height={height}>
        {chart}
      </ResponsiveContainer>
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

export default function Explore() {
  const { data: models, isLoading: loadingModels } = useModels()
  const modelNames = (models || []).map(m => m.name)
  const [modelName, setModelName] = useState(null)
  const activeModel = modelName || modelNames[0]
  const { data: model, isLoading: loadingModel } = useModel(activeModel)

  const facts = model?.facts || []
  const dims = model?.dimensions || []
  const [factName, setFactName] = useState(null)
  const fact = facts.find(f => f.name === factName) || facts[0]

  const [measures, setMeasures] = useState({})        // {col: agg}
  const [dimAttrs, setDimAttrs] = useState([])        // ["dim.attr"]
  const [filters, setFilters] = useState({})          // {col: "value"}
  const [chartType, setChartType] = useState('bar')   // bar | line | area

  // Fact table columns (for filters) come from a 1-row preview.
  const { data: factPreview } = useTablePreview(activeModel, fact?.table)
  const factColumns = factPreview?.columns || []

  const { mutate: run, data: result, isPending, error, reset } = useRunQuery()

  const toggleMeasure = col => {
    const next = { ...measures }
    if (col in next) delete next[col]
    else next[col] = 'sum'
    setMeasures(next)
  }
  const toggleDimAttr = ref =>
    setDimAttrs(dimAttrs.includes(ref) ? dimAttrs.filter(d => d !== ref) : [...dimAttrs, ref])

  const selectFact = name => {
    setFactName(name)
    setMeasures({})
    setDimAttrs([])
    setFilters({})
    reset()
  }

  const canRun = fact && Object.keys(measures).length > 0

  const handleRun = () => {
    // Coerce numeric-looking filter values so equality matches typed columns.
    const typedFilters = {}
    for (const [k, v] of Object.entries(filters)) {
      if (v === '') continue
      const n = Number(v)
      typedFilters[k] = Number.isFinite(n) && v.trim() !== '' ? n : v
    }
    run({
      model: activeModel,
      body: {
        fact: fact.name,
        measures,
        dimensions: dimAttrs,
        filters: Object.keys(typedFilters).length ? typedFilters : null,
      },
    })
  }

  const measureCols = result ? result.columns.filter(c => c in measures) : []
  const chartDim = result && dimAttrs.length === 1 ? dimAttrs[0] : null

  if (loadingModels) return <><PageTitle>Explore</PageTitle><SkeletonCard /></>

  return (
    <>
      <PageTitle>Explore</PageTitle>
      <PageSub>
        Build a star-schema query — pick measures and dimensions, run it, and see
        the result with the full lineage of how it was computed.
      </PageSub>

      {facts.length === 0 && !loadingModel ? (
        <Empty
          icon="◬"
          message="No facts defined on this model. Tag tables with model.add_fact() / model.add_dimension() to enable Explore."
        />
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(280px, 340px) 1fr', gap: 20, alignItems: 'start' }}>
          {/* ── Builder ── */}
          <Card>
            <CardTitle>Query Builder</CardTitle>

            {modelNames.length > 1 && (
              <>
                <SectionLabel>Model</SectionLabel>
                <select value={activeModel} onChange={e => { setModelName(e.target.value); selectFact(null) }}
                  style={{ ...selectStyle, width: '100%', padding: '6px 8px', fontSize: 12 }}>
                  {modelNames.map(n => <option key={n} value={n}>{n}</option>)}
                </select>
              </>
            )}

            <SectionLabel>Fact</SectionLabel>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              {facts.map(f => (
                <button key={f.name} onClick={() => selectFact(f.name)} style={{
                  padding: '6px 12px', borderRadius: 7, fontSize: 12, fontWeight: 600, cursor: 'pointer',
                  background: fact?.name === f.name ? 'var(--blue-lt)' : 'var(--surface-2)',
                  color: fact?.name === f.name ? 'var(--accent-text)' : 'var(--muted)',
                  border: `1px solid ${fact?.name === f.name ? 'var(--blue-br)' : 'var(--border)'}`,
                }}>{f.name}</button>
              ))}
            </div>

            {fact && (
              <>
                <SectionLabel>Measures</SectionLabel>
                {fact.measures.map(col => (
                  <CheckRow
                    key={col}
                    checked={col in measures}
                    onToggle={() => toggleMeasure(col)}
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

                <SectionLabel>Group by</SectionLabel>
                {dims.length === 0 && (
                  <p style={{ fontSize: 12, color: 'var(--muted)' }}>No dimensions defined.</p>
                )}
                {dims.map(d => (
                  <div key={d.name} style={{ marginBottom: 6 }}>
                    <div style={{ fontSize: 11, color: 'var(--text-2)', margin: '4px 0 2px', fontWeight: 600 }}>
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

                <div style={{ marginTop: 20 }}>
                  <Btn onClick={handleRun} disabled={!canRun || isPending} style={{ width: '100%', justifyContent: 'center' }}>
                    {isPending ? <><Spinner size={14} /> Running…</> : '▶ Run query'}
                  </Btn>
                  {!canRun && (
                    <p style={{ fontSize: 11, color: 'var(--muted)', marginTop: 8, textAlign: 'center' }}>
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
                  icon="◭"
                  message="Results appear here. Every query you build is executed with full lineage tracking — you'll see exactly how the numbers were produced."
                />
              </Card>
            )}

            {result && (
              <div className="fade-in">
                <Card>
                  <CardTitle action={
                    <button onClick={() => downloadCsv(result)} className="dl-link"
                      style={{ background: 'var(--blue-lt)' }}>↓ CSV</button>
                  }>
                    Result
                  </CardTitle>
                  <div style={{ display: 'flex', gap: 8, marginBottom: 14, flexWrap: 'wrap' }}>
                    <Badge variant="gray">{result.rows} row{result.rows !== 1 ? 's' : ''}</Badge>
                    {result.engine && <Badge variant={result.engine === 'duckdb' ? 'green' : 'blue'}>engine: {result.engine}</Badge>}
                    <Badge variant="gray">{result.elapsed_ms} ms</Badge>
                  </div>

                  {chartDim && measureCols.length > 0 && (
                    <>
                      <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                        <ChartTypeToggle type={chartType} onChange={setChartType} />
                      </div>
                      <ResultChart data={result.data} dimCol={chartDim} measureCols={measureCols} type={chartType} />
                    </>
                  )}

                  <div style={{ overflowX: 'auto', borderRadius: 6, border: '1px solid var(--border)', marginTop: chartDim ? 14 : 0 }}>
                    <table>
                      <thead><tr>{result.columns.map(c => <th key={c}>{c}</th>)}</tr></thead>
                      <tbody>
                        {result.data.map((row, i) => (
                          <tr key={i}>
                            {result.columns.map(c => (
                              <td key={c} style={typeof row[c] === 'number' ? { fontVariantNumeric: 'tabular-nums' } : undefined}>
                                {row[c] == null
                                  ? <span style={{ color: 'var(--muted)', fontStyle: 'italic' }}>null</span>
                                  : typeof row[c] === 'number'
                                    ? row[c].toLocaleString(undefined, { maximumFractionDigits: 2 })
                                    : String(row[c])}
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
                  <p style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 12 }}>
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
