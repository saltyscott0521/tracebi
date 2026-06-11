import { useState, useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import { useConnectors, useModels, useReports, usePipelines } from '../api'
import { StatTile, CodeBlock } from '../components/Shared'

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


// ── Page ──────────────────────────────────────────────────────────────────────

const QUICK = [
  { n: 1, label: 'Install',        cmd: 'pip install "tracebi[analyst]"',                    color: '#2563eb' },
  { n: 2, label: 'Write a report', cmd: 'tracebi new-request "revenue by region"',            color: '#7c3aed' },
  { n: 3, label: 'Run it',         cmd: 'tracebi run requests/revenue_by_region.py',          color: '#059669' },
]

export default function Home() {
  const { data: connectors } = useConnectors()
  const { data: models } = useModels()
  const { data: reports } = useReports()
  const { data: pipelines } = usePipelines()

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
          <Link to="/getting-started" style={{
            display: 'inline-flex', alignItems: 'center', gap: 7,
            padding: '11px 24px', borderRadius: 8, fontSize: 13, fontWeight: 600,
            background: 'var(--blue-lt)', color: 'var(--accent-text)',
            border: '1px solid var(--blue-br)', textDecoration: 'none',
          }}>→ Get started</Link>
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

      {/* ── 3-step quick start ────────────────────────────────────────────── */}
      <div style={{ marginBottom: 8 }}>
        <div style={{
          display: 'flex', alignItems: 'baseline', justifyContent: 'space-between',
          marginBottom: 16,
        }}>
          <h2 className="gradient-text" style={{ fontSize: 18, fontWeight: 800, letterSpacing: -.2 }}>
            Start in 3 steps
          </h2>
          <Link to="/getting-started" style={{
            fontSize: 12, fontWeight: 600, color: 'var(--accent-text)', textDecoration: 'none',
          }}>Full guide →</Link>
        </div>
        <div className="grid-3">
          {QUICK.map(s => (
            <div key={s.n} className="card-hover" style={{
              background: 'var(--card)', border: '1px solid var(--border)',
              borderRadius: 12, padding: '18px 20px',
            }}>
              <div style={{
                width: 28, height: 28, borderRadius: 7, marginBottom: 12,
                background: `${s.color}14`, border: `1px solid ${s.color}28`,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 12, fontWeight: 800, color: s.color,
              }}>{s.n}</div>
              <div style={{ fontWeight: 700, fontSize: 13, color: 'var(--text)', marginBottom: 10 }}>{s.label}</div>
              <CodeBlock>{s.cmd}</CodeBlock>
            </div>
          ))}
        </div>
      </div>

    </div>
  )
}
