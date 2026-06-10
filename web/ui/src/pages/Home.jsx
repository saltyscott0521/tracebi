import { useState, useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import { useConnectors, useModels, useReports, usePipelines } from '../api'
import { StatTile, CodeBlock, Btn } from '../components/Shared'

// ── Notebook Demo ─────────────────────────────────────────────────────────────
// Animated Jupyter-notebook walkthrough of the TraceBi Python API.
// Outputs mirror the library's real _repr_html_ for DataSet / DataModel.

const MONO = "'Cascadia Code', 'Fira Code', Consolas, monospace"
const NAVY = '#1F3864'
const REPR_BORDER = '1px solid #dde4ef'

const CHARS_PER_TICK = 6
const TICK_MS = 22
const RUN_MS = 700
const CELL_PAUSE_MS = 2400
const LOOP_PAUSE_MS = 5200

const NB_CELLS = [
  {
    output: 'model',
    code:
`from tracebi import DataModel, SQLConnector

db = SQLConnector("sales_db", url="sqlite:///data/sales.db")

model = DataModel("SalesModel")
model.add_connector(db)
model.add_table("orders",    connector="sales_db", source="orders")
model.add_table("customers", connector="sales_db", source="customers")
model.connect()
model`,
  },
  {
    output: 'result',
    code:
`orders = model.load("orders")

result = (
    orders
    .filter("status == 'shipped'", description="Shipped orders only")
    .transform(lambda df: df.assign(margin=df["revenue"] - df["cost"]),
               description="margin = revenue - cost")
    .sort("margin", ascending=False)
)
result`,
  },
  {
    output: 'lineage',
    stdout: true,
    code: `result.print_lineage()`,
  },
  {
    output: 'query',
    code:
`model.add_dimension("dim_customer", table_name="customers",
                    key_col="customer_id", attributes=["region"])
model.add_fact("fact_orders", table_name="orders",
               measures=["revenue", "margin"],
               foreign_keys={"dim_customer": "customer_id"})

by_region = model.query(fact="fact_orders",
                        measures={"revenue": "sum", "margin": "sum"},
                        dimensions=["dim_customer.region"])
by_region`,
  },
  {
    output: 'report',
    stdout: true,
    code:
`from tracebi.reports import Report, ChartSection, TableSection, HTMLRenderer

report = (
    Report("Q2 Revenue Analysis")
    .author("Data Team")
    .add(ChartSection("Revenue by Region", dataset=by_region,
                      chart_type="bar", x="dim_customer.region", y="revenue"))
    .add(TableSection("Detail", dataset=by_region, totals=["revenue"]))
)

HTMLRenderer().render(report, "output/q2.html")`,
  },
]

// ── Python syntax highlighting (light theme) ──────────────────────────────────

const PY_RE = /(#[^\n]*)|("(?:[^"\\\n]|\\.)*"?|'(?:[^'\\\n]|\\.)*'?)|\b(from|import|lambda|def|return|class|if|else|for|in|with|as|True|False|None)\b|(\b\d+(?:\.\d+)?\b)/g

const TOKEN_STYLES = {
  comment: { color: '#8a97a8', fontStyle: 'italic' },
  string:  { color: '#0e7a4e' },
  keyword: { color: '#7c3aed', fontWeight: 600 },
  number:  { color: '#b45309' },
}

function highlightPy(src) {
  const out = []
  let last = 0
  let m
  PY_RE.lastIndex = 0
  while ((m = PY_RE.exec(src)) !== null) {
    if (m.index > last) out.push(src.slice(last, m.index))
    const kind = m[1] ? 'comment' : m[2] ? 'string' : m[3] ? 'keyword' : 'number'
    out.push(<span key={m.index} style={TOKEN_STYLES[kind]}>{m[0]}</span>)
    last = m.index + m[0].length
  }
  if (last < src.length) out.push(src.slice(last))
  return out
}

// ── Mock cell outputs (shaped like the real rich reprs) ───────────────────────

const DS_RESULT = {
  name: 'orders',
  shape: '198 rows × 6 cols',
  chain: ['load', 'filter', 'transform', 'sort'],
  cols: [
    { name: 'order_id', dtype: 'int64' },
    { name: 'region',   dtype: 'object' },
    { name: 'product',  dtype: 'object' },
    { name: 'revenue',  dtype: 'float64' },
    { name: 'cost',     dtype: 'float64' },
    { name: 'margin',   dtype: 'float64' },
  ],
  rows: [
    ['1042', 'North', 'Solar Panel', '12400.0', '8100.0', '4300.0'],
    ['1187', 'West',  'Inverter',    '9850.0',  '6200.0', '3650.0'],
    ['1093', 'North', 'Battery',     '8400.0',  '5300.0', '3100.0'],
    ['1216', 'South', 'Controller',  '7120.0',  '4480.0', '2640.0'],
  ],
  more: '… 194 more rows',
}

const DS_QUERY = {
  name: 'query_result',
  shape: '4 rows × 3 cols',
  chain: ['query'],
  cols: [
    { name: 'dim_customer.region', dtype: 'object' },
    { name: 'revenue',             dtype: 'float64' },
    { name: 'margin',              dtype: 'float64' },
  ],
  rows: [
    ['North', '284210.0', '62340.0'],
    ['West',  '198450.0', '43760.0'],
    ['South', '156780.0', '33450.0'],
    ['East',  '142110.0', '30560.0'],
  ],
  more: null,
}

const LINEAGE_STEPS = [
  { op: 'LOAD',      color: '#1d4ed8', desc: "Loaded 'orders' from 'sales_db'", rows: '250' },
  { op: 'FILTER',    color: '#15803d', desc: 'Shipped orders only',             rows: '250 → 198' },
  { op: 'TRANSFORM', color: '#b45309', desc: 'margin = revenue - cost',         rows: '198' },
  { op: 'SORT',      color: '#6d28d9', desc: 'Sorted by margin (descending)',   rows: '198' },
]

const REPORT_BARS = [
  { region: 'North', revenue: 284210 },
  { region: 'West',  revenue: 198450 },
  { region: 'South', revenue: 156780 },
  { region: 'East',  revenue: 142110 },
]

function ReprFrame({ children }) {
  return (
    <div style={{
      border: REPR_BORDER, borderRadius: 6, padding: '12px 14px',
      display: 'inline-block', maxWidth: '100%', overflowX: 'auto',
      background: '#fff', fontFamily: "'Segoe UI', Calibri, Arial, sans-serif",
    }}>{children}</div>
  )
}

function NbModelOut() {
  const item = { fontSize: 11, color: '#333', padding: '1px 0' }
  return (
    <ReprFrame>
      <div>
        <span style={{ fontWeight: 700, color: NAVY, fontSize: 14 }}>DataModel: SalesModel</span>
        <span style={{ color: '#666', fontSize: 11, marginLeft: 8 }}>connectors: sales_db</span>
      </div>
      <div style={{ fontWeight: 700, color: NAVY, fontSize: 12, margin: '8px 0 4px' }}>Tables</div>
      <div style={item}><b>orders</b> <span style={{ color: '#999' }}>← sales_db / orders</span></div>
      <div style={item}><b>customers</b> <span style={{ color: '#999' }}>← sales_db / customers</span></div>
    </ReprFrame>
  )
}

function NbDataSetOut({ name, shape, chain, cols, rows, more }) {
  const badge = {
    display: 'inline-block', padding: '2px 8px', borderRadius: 10,
    fontSize: 10, fontWeight: 600, background: '#DEEBF7', color: NAVY,
  }
  return (
    <ReprFrame>
      <div style={{ marginBottom: 6 }}>
        <span style={{ fontWeight: 700, color: NAVY, fontSize: 13 }}>{name}</span>
        <span style={{ color: '#666', fontSize: 11, marginLeft: 8 }}>{shape}</span>
      </div>
      <div style={{ marginBottom: 8, display: 'flex', alignItems: 'center', gap: 5, flexWrap: 'wrap' }}>
        {chain.map((op, i) => (
          <span key={op} style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
            {i > 0 && <span style={{ color: '#999', fontSize: 10 }}>→</span>}
            <span style={badge}>{op}</span>
          </span>
        ))}
      </div>
      <table style={{ borderCollapse: 'collapse', width: 'auto', fontSize: 11 }}>
        <thead>
          <tr style={{ background: 'transparent' }}>
            {cols.map(c => (
              <th key={c.name} style={{
                background: NAVY, color: '#fff', padding: '5px 10px', textAlign: 'left',
                fontSize: 11, fontWeight: 600, textTransform: 'none', letterSpacing: 0, border: 'none',
              }}>
                {c.name}
                <div style={{ fontWeight: 400, opacity: 0.7 }}>{c.dtype}</div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} style={{ border: 'none' }}>
              {r.map((v, j) => (
                <td key={j} style={{ padding: '4px 10px', borderBottom: '1px solid #dde4ef', fontSize: 11, color: '#333' }}>{v}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {more && <div style={{ fontSize: 11, color: '#999', marginTop: 4 }}>{more}</div>}
    </ReprFrame>
  )
}

function NbLineageOut() {
  const sep = '='.repeat(60)
  return (
    <pre style={{ fontFamily: MONO, fontSize: 11.5, lineHeight: 1.6, margin: 0, color: '#43536b', whiteSpace: 'pre-wrap' }}>
      {sep + '\n'}
      {"  Lineage for DataSet: 'orders'\n"}
      {'  Shape: 198 rows × 6 cols\n'}
      {sep + '\n'}
      {LINEAGE_STEPS.map((s, i) => (
        <span key={s.op}>
          {`  Step ${i + 1}: `}
          <span style={{ color: s.color, fontWeight: 700 }}>{`[${s.op}]`}</span>
          {`  ${s.desc}\n    Rows        : ${s.rows}\n`}
        </span>
      ))}
      {sep}
    </pre>
  )
}

function NbReportOut() {
  const max = REPORT_BARS[0].revenue
  return (
    <div>
      <pre style={{ fontFamily: MONO, fontSize: 11.5, margin: '0 0 10px', color: '#15803d', whiteSpace: 'pre-wrap' }}>
        ✓ Rendered → output/q2.html   (manifest.json written with full lineage)
      </pre>
      <div style={{ border: REPR_BORDER, borderRadius: 8, background: '#fff', padding: '14px 18px', maxWidth: 460 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 12, paddingBottom: 10, borderBottom: '1px solid #eef2f7' }}>
          <div>
            <div style={{ fontSize: 13.5, fontWeight: 800, color: NAVY }}>Q2 Revenue Analysis</div>
            <div style={{ fontSize: 10.5, color: '#8a97a8' }}>Data Team · 2 sections · output/q2.html</div>
          </div>
          <span style={{ fontSize: 10, color: '#15803d', fontWeight: 700, padding: '2px 8px', borderRadius: 10, background: 'rgba(22,163,74,.08)', border: '1px solid rgba(22,163,74,.25)' }}>preview</span>
        </div>
        <div style={{ fontSize: 9.5, fontWeight: 700, color: '#8a97a8', textTransform: 'uppercase', letterSpacing: .7, marginBottom: 8 }}>Revenue by Region</div>
        {REPORT_BARS.map(b => (
          <div key={b.region} style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
            <div style={{ width: 38, fontSize: 10.5, color: '#5a6e88', textAlign: 'right', flexShrink: 0 }}>{b.region}</div>
            <div style={{ flex: 1, height: 18, background: '#eef2f7', borderRadius: 4, overflow: 'hidden' }}>
              <div style={{
                width: `${(b.revenue / max) * 100}%`, height: '100%',
                background: 'linear-gradient(90deg, #091a55, #0369a1)',
                borderRadius: 4, display: 'flex', alignItems: 'center', paddingLeft: 8,
              }}>
                <span style={{ fontSize: 9.5, fontWeight: 700, color: 'rgba(255,255,255,.85)', fontFamily: MONO, whiteSpace: 'nowrap' }}>
                  ${(b.revenue / 1000).toFixed(0)}K
                </span>
              </div>
            </div>
          </div>
        ))}
        <div style={{ fontSize: 10.5, color: '#5a6e88', marginTop: 10, paddingTop: 8, borderTop: '1px solid #eef2f7', display: 'flex', justifyContent: 'space-between' }}>
          <span>Total revenue</span>
          <span style={{ fontFamily: MONO, fontWeight: 700, color: NAVY }}>$781,550</span>
        </div>
      </div>
    </div>
  )
}

function NbOutput({ type }) {
  if (type === 'model')   return <NbModelOut />
  if (type === 'result')  return <NbDataSetOut {...DS_RESULT} />
  if (type === 'lineage') return <NbLineageOut />
  if (type === 'query')   return <NbDataSetOut {...DS_QUERY} />
  return <NbReportOut />
}

// ── Notebook cell ─────────────────────────────────────────────────────────────

function NbCell({ cell, num, isCurrent, chars, stage }) {
  const showOutput = !isCurrent || stage === 'output'
  const running = isCurrent && stage === 'running'
  const typing = isCurrent && stage === 'typing'
  const visible = isCurrent ? cell.code.slice(0, chars) : cell.code
  const inPrompt = showOutput ? `In [${num}]:` : running ? 'In [*]:' : 'In [ ]:'

  return (
    <div style={{ marginBottom: 20 }}>
      <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
        <div style={{
          width: 58, flexShrink: 0, textAlign: 'right', paddingTop: 11,
          fontFamily: MONO, fontSize: 11, fontWeight: 700,
          color: running ? '#b45309' : '#307fc1',
        }}>{inPrompt}</div>
        <div style={{
          flex: 1, minWidth: 0, background: '#fff', borderRadius: 4,
          border: `1px solid ${isCurrent ? '#a8c3e8' : '#dde4ef'}`,
          borderLeft: `3px solid ${isCurrent ? '#2563eb' : '#dde4ef'}`,
          boxShadow: isCurrent ? '0 1px 6px rgba(37,99,235,.08)' : 'none',
          padding: '10px 14px', transition: 'border-color .3s, box-shadow .3s',
        }}>
          <pre style={{ fontFamily: MONO, fontSize: 12.5, lineHeight: 1.7, margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-word', color: '#1f2d45' }}>
            {highlightPy(visible)}
            {typing && (
              <span className="cursor-blink" style={{
                display: 'inline-block', width: 2, height: '0.95em',
                background: '#2563eb', marginLeft: 1, verticalAlign: 'text-bottom',
              }} />
            )}
          </pre>
        </div>
      </div>
      {showOutput && (
        <div className="fade-in" style={{ display: 'flex', gap: 10, alignItems: 'flex-start', marginTop: 8 }}>
          <div style={{
            width: 58, flexShrink: 0, textAlign: 'right', paddingTop: 4,
            fontFamily: MONO, fontSize: 11, fontWeight: 700, color: '#bf5b3d',
          }}>{cell.stdout ? '' : `Out[${num}]:`}</div>
          <div style={{ flex: 1, minWidth: 0, overflowX: 'auto' }}>
            <NbOutput type={cell.output} />
          </div>
        </div>
      )}
    </div>
  )
}

// ── Player ────────────────────────────────────────────────────────────────────

function DemoPlayer() {
  const [cellIdx, setCellIdx] = useState(0)
  const [chars, setChars] = useState(0)
  const [stage, setStage] = useState('typing')   // typing → running → output
  const [playing, setPlaying] = useState(true)
  const tm = useRef(null)
  const scrollRef = useRef(null)

  const cell = NB_CELLS[cellIdx]

  useEffect(() => {
    if (!playing) { clearTimeout(tm.current); return }
    clearTimeout(tm.current)
    if (stage === 'typing') {
      tm.current = chars < cell.code.length
        ? setTimeout(() => setChars(c => Math.min(c + CHARS_PER_TICK, cell.code.length)), TICK_MS)
        : setTimeout(() => setStage('running'), 200)
    } else if (stage === 'running') {
      tm.current = setTimeout(() => setStage('output'), RUN_MS)
    } else {
      const isLast = cellIdx === NB_CELLS.length - 1
      tm.current = setTimeout(() => {
        setCellIdx(i => (i + 1) % NB_CELLS.length)
        setChars(0)
        setStage('typing')
      }, isLast ? LOOP_PAUSE_MS : CELL_PAUSE_MS)
    }
    return () => clearTimeout(tm.current)
  }, [chars, stage, playing, cellIdx, cell])

  // Keep the newest cell in view as it types and outputs appear
  useEffect(() => {
    const el = scrollRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [chars, stage, cellIdx])

  const restart = () => { setCellIdx(0); setChars(0); setStage('typing'); setPlaying(true) }
  const progress = ((cellIdx + (stage === 'output' ? 1 : Math.min(chars / (cell.code.length || 1), 1))) / NB_CELLS.length) * 100

  const btn = {
    background: 'rgba(9,26,85,.06)', border: '1px solid rgba(9,26,85,.18)',
    borderRadius: 6, cursor: 'pointer', padding: '3px 10px',
    color: '#43536b', fontSize: 11, fontWeight: 700, letterSpacing: .3,
  }

  return (
    <div style={{
      background: '#f6f8fb',
      border: '1px solid var(--border)',
      borderRadius: 14,
      overflow: 'hidden',
      marginBottom: 32,
      boxShadow: 'var(--shadow)',
    }}>

      {/* Window chrome */}
      <div style={{
        background: '#e9eef5',
        borderBottom: '1px solid #d4dde8',
        padding: '10px 16px',
        display: 'flex', alignItems: 'center', gap: 12,
        userSelect: 'none',
      }}>
        <div style={{ display: 'flex', gap: 6 }}>
          {['#ef4444', '#f59e0b', '#22c55e'].map(c => (
            <div key={c} style={{ width: 11, height: 11, borderRadius: '50%', background: c, opacity: .8 }} />
          ))}
        </div>
        <div style={{ flex: 1, textAlign: 'center', fontSize: 12, color: '#43536b', fontWeight: 600, letterSpacing: .2 }}>
          tracebi_quickstart.ipynb
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 11, color: '#43536b', fontWeight: 600 }}>
            <span style={{
              width: 8, height: 8, borderRadius: '50%',
              background: stage === 'running' ? '#d97706' : '#16a34a',
              transition: 'background .2s',
            }} />
            Python 3 (tracebi)
          </span>
          <button onClick={restart} title="Restart" style={btn}>↺</button>
          <button onClick={() => setPlaying(p => !p)} title={playing ? 'Pause' : 'Play'} style={{
            ...btn,
            background: playing ? 'rgba(22,163,74,.1)' : 'rgba(9,26,85,.06)',
            border: `1px solid ${playing ? 'rgba(22,163,74,.3)' : 'rgba(9,26,85,.18)'}`,
            color: playing ? '#15803d' : '#43536b',
          }}>
            {playing ? '⏸' : '▶'}
          </button>
        </div>
      </div>

      {/* Cells */}
      <div ref={scrollRef} style={{ height: 480, overflowY: 'auto', padding: '20px 22px 26px' }}>

        {/* Markdown cell */}
        <div style={{ display: 'flex', gap: 10, marginBottom: 20 }}>
          <div style={{ width: 58, flexShrink: 0 }} />
          <div>
            <div style={{ fontSize: 18, fontWeight: 800, color: '#15243f', marginBottom: 4 }}>TraceBi quickstart</div>
            <p style={{ fontSize: 12.5, color: '#5a6e88', lineHeight: 1.6, margin: 0 }}>
              Connect → transform → trace → report. Every step records lineage automatically —
              run this yourself in any notebook.
            </p>
          </div>
        </div>

        {NB_CELLS.slice(0, cellIdx + 1).map((c, i) => (
          <NbCell key={i} cell={c} num={i + 1} isCurrent={i === cellIdx} chars={chars} stage={stage} />
        ))}
      </div>

      {/* Progress */}
      <div style={{ height: 3, background: '#e2e8f1' }}>
        <div style={{
          height: '100%',
          background: 'linear-gradient(90deg, #091a55, #0369a1)',
          width: `${progress}%`,
          transition: `width ${TICK_MS}ms linear`,
        }} />
      </div>
    </div>
  )
}

// ── Static content ────────────────────────────────────────────────────────────

const CONCEPTS = [
  {
    n: 1,
    title: 'DataSet — immutable by design',
    body: `The core container is DataSet — a thin wrapper around a pandas DataFrame. Every
operation returns a new DataSet. Nothing mutates the original.

Chain transformations freely — filter, transform, sort, rename, select — and each step
produces a clean, independent result. Branch two ways from the same source without copies.`,
    code: [
      { t: 'c', v: '# Every step returns a NEW DataSet' },
      { t: 'n', v: 'orders = model.load("orders")' },
      { t: 'n', v: '' },
      { t: 'n', v: 'result = (\n  orders\n  .filter("status == \'shipped\'")\n  .transform(lambda df: df.assign(\n    margin=df["revenue"] - df["cost"]\n  ))\n  .sort("margin", ascending=False)\n)' },
      { t: 'n', v: '' },
      { t: 'c', v: '# Original unchanged — still has all statuses' },
      { t: 'n', v: 'orders.shape  ' },
      { t: 'c', v: '# same as when first loaded' },
    ],
  },
  {
    n: 2,
    title: 'Lineage — every step is recorded',
    body: `Every DataSet carries a lineage list — a chain of LineageNode records. Each node
records the operation type, a human-readable description, row counts before and after, and
a timestamp.

A DataSet at the end of a chain holds the complete history of everything that produced it —
connector, filters, joins, transforms, aggregations — traceable back to the raw source.`,
    code: [
      { t: 'n', v: 'result.print_lineage()' },
      { t: 'n', v: '' },
      { t: 'c', v: '# Step 1: [LOAD]       Loaded \'orders\' from \'sales_db\'' },
      { t: 'c', v: '# Step 2: [FILTER]     Shipped orders only (250 → 198 rows)' },
      { t: 'c', v: '# Step 3: [TRANSFORM]  margin = revenue - cost' },
      { t: 'c', v: '# Step 4: [SORT]       Sorted by margin (desc)' },
      { t: 'n', v: '' },
      { t: 'c', v: '# Export as a DAG diagram' },
      { t: 'n', v: 'from tracebi.lineage.diagram import LineageDiagram\nLineageDiagram(result).to_html("lineage.html")' },
    ],
  },
  {
    n: 3,
    title: 'Landing → Manipulation → Final',
    body: `Three named layers, each with a distinct purpose. Landing / Manipulation / Final are
the canonical names; Bronze / Silver / Gold remain as aliases.

Landing — raw ingest as-is, permanent audit record.
Manipulation — declarative light cleaning (casts, nulls, deduplication).
Final — serving layer, star-schema aggregation fed to reports and dashboards.`,
    code: [
      { t: 'b', v: '# Landing — raw ingest, zero transforms' },
      { t: 'n', v: 'landing = LandingLayer(\n  connector=db, source="orders_raw",\n  sink=db, sink_table="orders_bronze",\n)' },
      { t: 'n', v: '' },
      { t: 's', v: '# Manipulation — declarative cleaning' },
      { t: 'n', v: 'manip = (\n  ManipulationLayer(source=db, source_table="orders_bronze",\n                    sink=db, sink_table="orders_silver")\n  .cast({"qty": "int64"})\n  .drop_nulls()\n  .deduplicate(subset=["order_id"])\n)' },
      { t: 'n', v: '' },
      { t: 'g', v: '# Final — aggregated via star-schema query' },
      { t: 'n', v: 'final = FinalLayer(\n  model=model, fact="fact_orders",\n  measures={"revenue": "sum"},\n  dimensions=["dim_customer.region"],\n  sink=db, sink_table="revenue_by_region",\n)' },
    ],
  },
  {
    n: 4,
    title: 'Star Schema — declarative analytics',
    body: `Tag tables with star-schema roles and TraceBi adds BI semantics to the same model
you already use for loads and joins.

Facts — transactional tables with numeric measures (revenue, qty).
Dimensions — lookup tables with categorical attributes (region, segment).

model.query() is then fully declarative: describe the result you want and TraceBi resolves
all joins, applies filters, and aggregates automatically inside DuckDB.`,
    code: [
      { t: 'n', v: 'model.add_dimension(\n  "dim_customer",\n  table_name="customers_silver",\n  key_col="customer_id",\n  attributes=["region", "segment"],\n)\nmodel.add_fact(\n  "fact_orders",\n  table_name="orders_silver",\n  measures=["revenue", "qty"],\n  foreign_keys={"dim_customer": "customer_id"},\n)' },
      { t: 'n', v: '' },
      { t: 'c', v: '# Joins resolved automatically' },
      { t: 'n', v: 'ds = model.query(\n  fact="fact_orders",\n  measures={"revenue": "sum"},\n  dimensions=["dim_customer.region"],\n  filters={"status": "shipped"},\n)' },
    ],
  },
]

const FEATURES = [
  { icon: '⇌', color: '#059669', title: 'Connectors', desc: 'CSV, SQL (any SQLAlchemy dialect), BigQuery, Snowflake, DuckDB, and in-memory DataFrames — all sharing the same connector.load() interface.' },
  { icon: '⬡', color: '#7c3aed', title: 'Data Models', desc: 'Associative model linking multiple DataSets by key. Add star-schema roles to get a fully declarative query surface over DuckDB — and browse it visually on the Explore page.' },
  { icon: '⧖', color: '#d97706', title: 'Pipelines', desc: 'Register layers with cron schedules and dependencies. Every run writes row counts and upstream IDs to SQLite — full chain provenance.' },
  { icon: '▤', color: '#db2777', title: 'Reports', desc: 'Compose from TextSection, TableSection, ChartSection. Render to Excel or HTML. A lineage manifest is written alongside every render.' },
  { icon: '◫', color: '#0891b2', title: 'Dashboards', desc: 'Interactive Dash app with associative filter panels — selecting one panel auto-filters every panel sharing that column.' },
  { icon: '⊶', color: '#2563eb', title: 'Lineage', desc: 'Every DataSet carries its full audit trail. Export to matplotlib, Mermaid, or interactive HTML. View the DAG for any report from the web UI.' },
]

const STEPS = [
  {
    label: '1. Connect',
    title: 'Connect to your data',
    desc: 'Register connectors and logical table names in a DataModel. Mix sources — orders from SQL, a customer lookup from CSV — and reference them all by name.',
    code: `from tracebi import DataModel, SQLConnector, CSVConnector

db  = SQLConnector("sales_db", url="sqlite:///data/sales.db")
csv = CSVConnector("lookups", directory="data/")

model = DataModel("SalesModel")
model.add_connector(db)
model.add_connector(csv)
model.add_table("orders",    connector="sales_db", source="orders")
model.add_table("customers", connector="sales_db", source="customers")
model.connect()`,
  },
  {
    label: '2. Transform',
    title: 'Load and transform with full lineage',
    desc: 'Every method on DataSet returns a new immutable DataSet with the step appended to its lineage chain. Call .transform() for full pandas access — no restrictions.',
    code: `orders = model.load("orders")

result = (
  orders
  .filter("status == 'shipped'", description="Shipped orders only")
  .transform(
    lambda df: df.assign(margin=df["revenue"] - df["cost"]),
    description="margin = revenue - cost",
  )
  .sort("margin", ascending=False)
  .select(["order_id", "region", "product", "revenue", "margin"])
)

result.print_lineage()
# Step 1: [LOAD]       Loaded 'orders' from 'sales_db'
# Step 2: [FILTER]     Shipped orders only  (250 → 198 rows)
# Step 3: [TRANSFORM]  margin = revenue - cost
# Step 4: [SORT]       Sorted by margin (desc)
# Step 5: [SELECT]     Selected 5 columns`,
  },
  {
    label: '3. Pipeline',
    title: 'Structure as a three-layer pipeline',
    desc: 'Landing → Manipulation → Final mirrors the medallion pattern. Each layer reads from the previous sink, applies its transformations, and writes output.',
    code: `from tracebi import LandingLayer, ManipulationLayer, FinalLayer

landing = LandingLayer(connector=db, source="orders_raw",
                       sink=db, sink_table="orders_bronze")

manip = (
  ManipulationLayer(source=db, source_table="orders_bronze",
                    sink=db, sink_table="orders_silver")
  .cast({"qty": "int64", "order_date": "datetime64[ns]"})
  .drop_nulls(subset=["order_id"])
  .deduplicate(subset=["order_id"])
)

final = FinalLayer(model=model, fact="fact_orders",
                   measures={"revenue": "sum"},
                   dimensions=["dim_customer.region"],
                   sink=db, sink_table="revenue_by_region")`,
  },
  {
    label: '4. Report',
    title: 'Build and render a report',
    desc: 'Assemble reports from section objects — text, tables, charts. Render to Excel or HTML; both renderers write a manifest.json capturing full lineage.',
    code: `from tracebi.reports.report import Report, TextSection, TableSection, ChartSection
from tracebi.reports.html_renderer import HTMLRenderer

report = (
  Report("Q2 Sales Report")
  .author("Data Team")
  .add(TextSection(title="Summary", content="...", style="heading1"))
  .add(ChartSection(title="Revenue by Region", dataset=gold_ds,
                    chart_type="bar", x="dim_customer.region", y="revenue"))
  .add(TableSection(title="Detail", dataset=gold_ds,
                    columns=["dim_customer.region", "revenue"],
                    totals=["revenue"]))
)

HTMLRenderer().render(report, "output/q2_sales.html")`,
  },
  {
    label: '5. Schedule',
    title: 'Schedule with a PipelineRunner',
    desc: 'Register all layers with a PipelineRunner. Assign cron schedules, declare dependencies. Every run is persisted to SQLite with row counts linking the full chain.',
    code: `from tracebi.pipeline.runner import PipelineRunner

runner = PipelineRunner(db_url="sqlite:///data/tracebi.db")

runner.register(landing, name="orders_bronze",     schedule="0 * * * *")
runner.register(manip,   name="orders_silver",     schedule="15 * * * *",
                depends_on="orders_bronze")
runner.register(final,   name="revenue_by_region", schedule="30 6 * * *",
                depends_on="orders_silver")

runner.run("revenue_by_region", refresh=True)  # full refresh
runner.start()  # start APScheduler (blocking)`,
  },
  {
    label: '6. Dashboard',
    title: 'Add a live dashboard',
    desc: 'Build a Dashboard from panel components — metrics, charts, tables, and filters. Filters are associative: selecting one panel updates every other panel sharing that column.',
    code: `from tracebi.dashboard import Dashboard, DashboardServer
from tracebi.dashboard import FilterPanel, MetricPanel, ChartPanel, TablePanel

dashboard = (
  Dashboard("Sales Dashboard").columns(2)
  .add_filter(FilterPanel("region-filter", label="Region",
                          column="region", table_name="orders"))
  .add_panel(MetricPanel("total-revenue", title="Total Revenue",
                         table_name="orders", column="revenue",
                         aggregation="sum", prefix="$"))
  .add_panel(ChartPanel("by-region", title="Revenue by Region",
                        table_name="orders", chart_type="bar",
                        x="region", y="revenue"))
)

DashboardServer(dashboard, model=model).run(port=8050)`,
  },
]

function ConceptCode({ lines }) {
  const colorMap = { c: '#4a6280', b: '#fbbf24', s: '#94a3b8', g: '#fde68a' }
  return (
    <pre className="code-block" style={{ fontSize: 11.5, lineHeight: 1.75 }}>
      {lines.map((l, i) => (
        l.t === 'n'
          ? <span key={i}>{l.v}</span>
          : <span key={i} style={{ color: colorMap[l.t] || '#4a6280' }}>{l.v}</span>
      )).reduce((acc, el, i) => i > 0 ? [...acc, '\n', el] : [el], [])}
    </pre>
  )
}

function SectionHeader({ title, sub }) {
  return (
    <div style={{ marginBottom: 24, marginTop: 8 }}>
      <h2 className="gradient-text" style={{ fontSize: 22, fontWeight: 800, marginBottom: 4, letterSpacing: -.2 }}>
        {title}
      </h2>
      {sub && <p style={{ fontSize: 13, color: 'var(--muted)' }}>{sub}</p>}
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function Home() {
  const { data: connectors } = useConnectors()
  const { data: models } = useModels()
  const { data: reports } = useReports()
  const { data: pipelines } = usePipelines()
  const [step, setStep] = useState(0)

  const stats = [
    { value: connectors?.length ?? '—', label: 'Connectors',  color: 'rgba(52,211,153,.18)',  icon: '⇌' },
    { value: models?.length     ?? '—', label: 'Data Models', color: 'rgba(167,139,250,.18)', icon: '⬡' },
    { value: reports?.length    ?? '—', label: 'Reports',     color: 'rgba(244,114,182,.18)', icon: '▤' },
    { value: pipelines?.length  ?? '—', label: 'Pipelines',   color: 'rgba(251,191,36,.18)',  icon: '⧖' },
  ]

  return (
    <div>

      {/* ── Hero ──────────────────────────────────────────────────────────── */}
      <div style={{
        background: 'var(--surface)',
        border: '1px solid var(--border)',
        borderRadius: 16,
        padding: '52px 52px 48px',
        marginBottom: 28,
        position: 'relative',
        overflow: 'hidden',
        boxShadow: 'var(--shadow-sm)',
        backgroundImage: `url("data:image/svg+xml,%3Csvg width='40' height='40' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M 40 0 L 0 0 0 40' fill='none' stroke='rgba(37,99,235,0.05)' stroke-width='1'/%3E%3C/svg%3E")`,
      }}>
        <div style={{
          position: 'absolute', top: -80, right: -80, width: 340, height: 340,
          background: 'radial-gradient(circle, rgba(124,58,237,.07) 0%, transparent 65%)',
          pointerEvents: 'none',
        }} />
        <div style={{
          position: 'absolute', bottom: -40, left: '30%', width: 240, height: 240,
          background: 'radial-gradient(circle, rgba(37,99,235,.06) 0%, transparent 65%)',
          pointerEvents: 'none',
        }} />

        <div style={{
          display: 'inline-flex', alignItems: 'center', gap: 7,
          padding: '4px 14px', marginBottom: 22,
          background: 'var(--blue-lt)', border: '1px solid var(--blue-br)',
          borderRadius: 20, fontSize: 11, fontWeight: 700,
          color: 'var(--accent-text)', letterSpacing: .8, textTransform: 'uppercase',
        }}>
          <span className="pulse-glow" style={{
            display: 'inline-block', width: 6, height: 6,
            borderRadius: '50%', background: 'var(--green)',
          }} />
          Code-first · Traceable · Open Source
        </div>

        <h2 style={{
          fontSize: 42, fontWeight: 900, lineHeight: 1.15, marginBottom: 16,
          background: 'var(--brand-text)',
          WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent',
          backgroundClip: 'text', maxWidth: 600, letterSpacing: -.5,
        }}>
          Build analytics pipelines that explain themselves.
        </h2>

        <p style={{ fontSize: 15, color: 'var(--text-2)', lineHeight: 1.75, maxWidth: 540, marginBottom: 32 }}>
          TraceBi is a Python BI framework where every transformation is tracked with a full
          lineage chain. DataSets, star schemas, medallion pipelines, and reports — with no
          black boxes.
        </p>

        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          <Link to="/reports" style={{
            display: 'inline-flex', alignItems: 'center', gap: 7,
            padding: '11px 24px', borderRadius: 8, fontSize: 13, fontWeight: 700,
            background: 'linear-gradient(135deg, #2563eb, #7c3aed)',
            color: '#fff', textDecoration: 'none',
            boxShadow: '0 4px 20px rgba(124,58,237,.4)',
          }}>▤ View Reports</Link>
          <Link to="/explore" style={{
            display: 'inline-flex', alignItems: 'center', gap: 7,
            padding: '11px 24px', borderRadius: 8, fontSize: 13, fontWeight: 600,
            background: 'rgba(2,132,199,.07)', color: '#0369a1',
            border: '1px solid rgba(2,132,199,.3)', textDecoration: 'none',
          }}>◬ Explore Data</Link>
          <Link to="/models" style={{
            display: 'inline-flex', alignItems: 'center', gap: 7,
            padding: '11px 24px', borderRadius: 8, fontSize: 13, fontWeight: 600,
            background: 'var(--blue-lt)', color: 'var(--accent-text)',
            border: '1px solid var(--blue-br)', textDecoration: 'none',
          }}>⬡ Models</Link>
          <Link to="/pipelines" style={{
            display: 'inline-flex', alignItems: 'center', gap: 7,
            padding: '11px 24px', borderRadius: 8, fontSize: 13, fontWeight: 600,
            background: 'var(--amber-lt)', color: 'var(--amber-text)',
            border: '1px solid var(--amber-br)', textDecoration: 'none',
          }}>⧖ Pipelines</Link>
        </div>
      </div>

      {/* ── Demo Player ───────────────────────────────────────────────────── */}
      <DemoPlayer />

      {/* ── Stats ─────────────────────────────────────────────────────────── */}
      <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginBottom: 44 }}>
        {stats.map(s => (
          <StatTile key={s.label} value={s.value} label={s.label} color={s.color} icon={s.icon} />
        ))}
      </div>

      {/* ── Core Concepts ─────────────────────────────────────────────────── */}
      <SectionHeader title="Core concepts" sub="Four ideas that everything else is built on." />

      {CONCEPTS.map(c => (
        <div key={c.n} className="card-accent" style={{
          background: 'var(--card)',
          backdropFilter: 'blur(8px)', WebkitBackdropFilter: 'blur(8px)',
          border: '1px solid var(--border)',
          borderRadius: 12, padding: '22px 26px', marginBottom: 16,
        }}>
          <div className="concept-grid">
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 14 }}>
                <div style={{
                  width: 34, height: 34, borderRadius: 9, flexShrink: 0,
                  background: 'linear-gradient(135deg, rgba(59,130,246,.25), rgba(124,58,237,.25))',
                  border: '1px solid rgba(124,58,237,.3)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 14, fontWeight: 800, color: '#a78bfa',
                }}>{c.n}</div>
                <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--text)' }}>{c.title}</div>
              </div>
              {c.body.split('\n\n').map((para, i) => (
                <p key={i} style={{ fontSize: 13, color: 'var(--muted)', lineHeight: 1.75, marginBottom: 10 }}>
                  {para.trim()}
                </p>
              ))}
            </div>
            <ConceptCode lines={c.code} />
          </div>
        </div>
      ))}

      {/* ── What's included ───────────────────────────────────────────────── */}
      <SectionHeader title="What TraceBi includes" sub="Six building blocks — each independent, all composable." />

      <div className="grid-3" style={{ marginBottom: 44 }}>
        {FEATURES.map(f => (
          <div key={f.title} className="card-hover" style={{
            background: 'var(--card)', border: '1px solid var(--border)',
            borderRadius: 12, padding: '22px 24px',
            position: 'relative', overflow: 'hidden',
          }}>
            <div style={{
              position: 'absolute', top: 0, right: 0, width: 100, height: 100,
              background: `radial-gradient(circle at top right, ${f.color}18 0%, transparent 65%)`,
              pointerEvents: 'none',
            }} />
            <div style={{
              display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
              width: 42, height: 42, borderRadius: 11,
              background: `${f.color}14`, border: `1px solid ${f.color}2e`,
              fontSize: 20, marginBottom: 16, flexShrink: 0,
            }}>{f.icon}</div>
            <div style={{ fontWeight: 700, fontSize: 14, color: 'var(--text)', marginBottom: 8 }}>{f.title}</div>
            <p style={{ fontSize: 13, color: 'var(--muted)', lineHeight: 1.65 }}>{f.desc}</p>
          </div>
        ))}
      </div>

      {/* ── Walkthrough ───────────────────────────────────────────────────── */}
      <SectionHeader title="End-to-end walkthrough" sub="A complete pipeline from raw data to scheduled report." />

      <div style={{ marginBottom: 44 }}>
        <div style={{
          display: 'flex', flexWrap: 'wrap', gap: 4,
          padding: '6px 6px 0',
          background: 'var(--surface-2)',
          border: '1px solid var(--border)', borderBottom: 'none',
          borderRadius: '10px 10px 0 0',
        }}>
          {STEPS.map((s, i) => (
            <button key={i} onClick={() => setStep(i)} style={{
              padding: '7px 16px', border: 'none',
              background: step === i ? 'var(--blue-lt)' : 'none',
              fontSize: 12.5, fontWeight: 600, cursor: 'pointer',
              color: step === i ? 'var(--accent-text)' : 'var(--muted)',
              borderRadius: '6px 6px 0 0',
              borderBottom: `2px solid ${step === i ? 'var(--blue)' : 'transparent'}`,
              transition: 'color var(--t), background var(--t)',
            }}>{s.label}</button>
          ))}
        </div>
        <div style={{
          background: 'var(--card)',
          backdropFilter: 'blur(8px)', WebkitBackdropFilter: 'blur(8px)',
          border: '1px solid var(--border)', borderTop: 'none',
          borderRadius: '0 0 10px 10px', padding: '22px 26px',
        }}>
          <div style={{ fontWeight: 700, fontSize: 14, color: 'var(--text)', marginBottom: 8 }}>
            {STEPS[step].title}
          </div>
          <p style={{ fontSize: 13, color: 'var(--muted)', lineHeight: 1.65, marginBottom: 16 }}>
            {STEPS[step].desc}
          </p>
          <CodeBlock>{STEPS[step].code}</CodeBlock>
        </div>
      </div>

      {/* ── How to use it ─────────────────────────────────────────────────── */}
      <SectionHeader title="Two ways to use TraceBi" />

      <div className="grid-2" style={{ marginBottom: 36 }}>
        <div className="card-hover" style={{
          background: 'var(--card)', border: '1px solid var(--border)',
          borderRadius: 12, padding: '22px 26px',
        }}>
          <div style={{
            display: 'inline-block', padding: '4px 12px', borderRadius: 20, fontSize: 11,
            fontWeight: 700, textTransform: 'uppercase', letterSpacing: .6,
            background: 'var(--blue-lt)', color: 'var(--accent-text)',
            border: '1px solid var(--blue-br)', marginBottom: 14,
          }}>Python library</div>
          <p style={{ fontSize: 13, color: 'var(--muted)', lineHeight: 1.7, marginBottom: 14 }}>
            Install TraceBi and use from a notebook or script. Build connectors, layers,
            star-schema queries, and render reports to HTML, Excel, or PDF.
          </p>
          <CodeBlock>{'pip install -e ".[reports,pipeline,lineage,sql]"'}</CodeBlock>
          <p style={{ fontSize: 12, color: 'var(--muted)', margin: '12px 0 6px' }}>Run the examples:</p>
          <CodeBlock>{'python examples/phase25_example.py'}</CodeBlock>
        </div>
        <div className="card-hover" style={{
          background: 'var(--card)', border: '1px solid var(--border)',
          borderRadius: 12, padding: '22px 26px',
        }}>
          <div style={{
            display: 'inline-block', padding: '4px 12px', borderRadius: 20, fontSize: 11,
            fontWeight: 700, textTransform: 'uppercase', letterSpacing: .6,
            background: 'var(--purple-lt)', color: '#6d28d9',
            border: '1px solid rgba(124,58,237,.25)', marginBottom: 14,
          }}>Web UI (this app)</div>
          <p style={{ fontSize: 13, color: 'var(--muted)', lineHeight: 1.7, marginBottom: 14 }}>
            Register connectors, models, reports, and pipelines in your app module.
            The web server surfaces them with run buttons, lineage diagrams, and a REST API.
          </p>
          <CodeBlock>{'# web/demo_app/registry.py\nregistry.add_connector(my_connector)\nregistry.add_model(my_model)\nregistry.add_pipeline("sales", runner)\n\n@registry.report("my_report")\ndef my_report(): ...'}</CodeBlock>
        </div>
      </div>

      {/* ── Bottom row ────────────────────────────────────────────────────── */}
      <div className="grid-2" style={{ marginBottom: 8 }}>
        <div className="card-hover" style={{
          background: 'linear-gradient(135deg, rgba(124,58,237,.05), var(--surface))',
          border: '1px solid rgba(124,58,237,.25)',
          borderRadius: 12, padding: '22px 26px',
          position: 'relative', overflow: 'hidden',
        }}>
          <div style={{
            position: 'absolute', top: -20, right: -20, width: 140, height: 140,
            background: 'radial-gradient(circle, rgba(124,58,237,.08) 0%, transparent 65%)',
            pointerEvents: 'none',
          }} />
          <div style={{ fontSize: 26, marginBottom: 12 }}>⊶</div>
          <div style={{ fontWeight: 700, fontSize: 14, color: 'var(--text)', marginBottom: 8 }}>Full lineage, always</div>
          <p style={{ fontSize: 13, color: 'var(--muted)', lineHeight: 1.65, marginBottom: 16 }}>
            Every DataSet carries a chain of LineageNode records — connector, transformation,
            row counts, and timestamp. Run any report to visualise the full DAG.
          </p>
          <Link to="/reports" style={{
            display: 'inline-flex', padding: '6px 14px', fontSize: 12, fontWeight: 600,
            borderRadius: 6, background: 'var(--purple-lt)',
            color: '#6d28d9', border: '1px solid rgba(124,58,237,.3)', textDecoration: 'none',
          }}>Explore lineage →</Link>
        </div>

        <div className="card-hover" style={{
          background: 'linear-gradient(135deg, rgba(37,99,235,.05), var(--surface))',
          border: '1px solid rgba(37,99,235,.25)',
          borderRadius: 12, padding: '22px 26px',
          position: 'relative', overflow: 'hidden',
        }}>
          <div style={{
            position: 'absolute', top: -20, right: -20, width: 140, height: 140,
            background: 'radial-gradient(circle, rgba(37,99,235,.07) 0%, transparent 65%)',
            pointerEvents: 'none',
          }} />
          <div style={{ fontSize: 26, marginBottom: 12 }}>⬡</div>
          <div style={{ fontWeight: 700, fontSize: 14, color: 'var(--text)', marginBottom: 8 }}>REST API included</div>
          <p style={{ fontSize: 13, color: 'var(--muted)', lineHeight: 1.65, marginBottom: 16 }}>
            Every UI feature is backed by a documented REST API. Trigger report runs, kick
            pipeline layers, and pull lineage data programmatically.
          </p>
          <div style={{ display: 'flex', gap: 10 }}>
            <a href="/docs" target="_blank" rel="noopener noreferrer" style={{
              display: 'inline-flex', padding: '6px 14px', fontSize: 12, fontWeight: 600,
              borderRadius: 6, background: 'linear-gradient(135deg,#2563eb,#1d4ed8)',
              color: '#fff', textDecoration: 'none', boxShadow: '0 2px 10px rgba(59,130,246,.3)',
            }}>Swagger UI</a>
            <a href="/redoc" target="_blank" rel="noopener noreferrer" style={{
              display: 'inline-flex', padding: '6px 14px', fontSize: 12, fontWeight: 600,
              borderRadius: 6, background: 'transparent', color: 'var(--accent-text)',
              border: '1px solid var(--blue-br)', textDecoration: 'none',
            }}>ReDoc</a>
          </div>
        </div>
      </div>
    </div>
  )
}
