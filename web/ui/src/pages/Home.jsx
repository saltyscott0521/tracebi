import { useState, useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import { useConnectors, useModels, useReports, usePipelines } from '../api'
import { StatTile, CodeBlock, Btn } from '../components/Shared'

// ── Demo Player ───────────────────────────────────────────────────────────────

const DEMO_STEPS = [
  {
    icon: '⇌',
    label: 'Connect',
    title: 'Connect to any data source',
    desc: 'Wrap SQL, CSV, BigQuery, Snowflake, or in-memory DataFrames. All connectors share the same interface.',
    code:
`from tracebi import DataModel, SQLConnector, CSVConnector

db  = SQLConnector("sales_db", url="sqlite:///data/sales.db")
csv = CSVConnector("lookups",  directory="data/")

model = DataModel("SalesModel")
model.add_connector(db)
model.add_connector(csv)
model.add_table("orders",    connector="sales_db", source="orders")
model.add_table("customers", connector="sales_db", source="customers")
model.connect()`,
    output: [
      { text: 'Connected to sales_db (SQLite)',         ok: true },
      { text: 'Connected to lookups (CSV, data/)',      ok: true },
      { text: 'Registered 2 tables: orders, customers', ok: true },
    ],
  },
  {
    icon: '⊶',
    label: 'Transform',
    title: 'Load and transform — lineage is automatic',
    desc: 'Every DataSet method returns a new immutable DataSet. The full audit trail is built without any extra tracking code.',
    code:
`orders = model.load("orders")

result = (
  orders
  .filter("status == 'shipped'",
          description="Shipped orders only")
  .transform(
    lambda df: df.assign(margin=df["revenue"] - df["cost"]),
    description="margin = revenue - cost",
  )
  .sort("margin", ascending=False)
)

result.print_lineage()`,
    output: [
      { text: '[LOAD]       Loaded \'orders\' from sales_db',  color: '#60a5fa' },
      { text: '[FILTER]     Shipped orders  (250 → 198 rows)', color: '#60a5fa' },
      { text: '[TRANSFORM]  margin = revenue − cost',          color: '#60a5fa' },
      { text: '[SORT]       Sorted by margin desc',             color: '#60a5fa' },
    ],
  },
  {
    icon: '⬡',
    label: 'Pipeline',
    title: 'Structure as Landing → Manipulation → Final',
    desc: 'Three layers, each reading the previous sink and writing the next. Declare schedules and dependencies — PipelineRunner handles the rest.',
    code:
`runner = PipelineRunner(db_url="sqlite:///data/tracebi.db")

runner.register(landing, name="orders_bronze",
                schedule="0 * * * *")
runner.register(manip,   name="orders_silver",
                schedule="15 * * * *",
                depends_on="orders_bronze")
runner.register(final,   name="revenue_gold",
                schedule="30 6 * * *",
                depends_on="orders_silver")

runner.start()`,
    output: [
      { text: '3 layers registered',             ok: true },
      { text: 'Scheduler started (APScheduler)', ok: true },
      { text: 'Next: orders_bronze in 00:42',    color: '#fbbf24' },
    ],
  },
  {
    icon: '▤',
    label: 'Report',
    outputType: 'report',
    title: 'Compose and render a report',
    desc: 'Assemble reports from typed sections. Render to Excel or HTML — a lineage manifest is written alongside every output.',
    code:
`report = (
  Report("Q2 Revenue Analysis")
  .author("Data Team")
  .add(TextSection("Summary", content=exec_summary))
  .add(ChartSection("Revenue by Region",
        dataset=gold_ds, chart_type="bar",
        x="dim_customer.region", y="revenue"))
  .add(TableSection("Detail",
        dataset=gold_ds,
        columns=["region", "revenue", "margin"],
        totals=["revenue", "margin"]))
)

HTMLRenderer().render(report, "output/q2.html")`,
    output: [],
  },
  {
    icon: '◫',
    label: 'Web UI',
    title: 'Expose everything via the web layer',
    desc: 'Register in your app module — connectors, models, pipelines, and reports are surfaced with run buttons, ERD diagrams, the Explore query builder, and lineage views.',
    code:
`# web/demo_app/registry.py
registry.add_connector(db)
registry.add_model(model)
registry.add_pipeline("sales", runner)

@registry.report("q2_revenue")
def q2_revenue():
    gold = model.query(
        fact="fact_orders",
        measures={"revenue": "sum"},
        dimensions=["dim_customer.region"])
    return build_report(gold)

# python web/run.py`,
    output: [
      { text: 'GET  /api/models/SalesModel',       color: '#60a5fa' },
      { text: 'POST /api/models/SalesModel/query', color: '#60a5fa' },
      { text: 'POST /api/reports/q2_revenue/run',  color: '#60a5fa' },
      { text: 'Serving on http://localhost:8000',  ok: true },
    ],
  },
]

const CHARS_PER_TICK = 6
const TICK_MS = 22
const OUTPUT_DELAY_MS = 420
const STEP_PAUSE_MS = 3000

// ── Report preview (shown when Report step finishes typing) ───────────────────

const REPORT_DATA = [
  { region: 'North', revenue: 284210, margin: 62340 },
  { region: 'West',  revenue: 198450, margin: 43760 },
  { region: 'South', revenue: 156780, margin: 33450 },
  { region: 'East',  revenue: 142110, margin: 30560 },
]
const REPORT_MAX = 284210

function ReportPreview() {
  return (
    <div style={{ padding: '16px 22px', height: '100%', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 14 }}>

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', paddingBottom: 12, borderBottom: '1px solid rgba(255,255,255,.07)' }}>
        <div>
          <div style={{ fontSize: 15, fontWeight: 800, color: '#d1ddf5', marginBottom: 3 }}>Q2 Revenue Analysis</div>
          <div style={{ fontSize: 10.5, color: '#3d5278' }}>Data Team · Q2 2024 · 198 rows · 3 sections</div>
        </div>
        <div style={{ display: 'flex', gap: 7, flexShrink: 0 }}>
          <span style={{ fontSize: 10, color: '#4ade80', fontWeight: 700, padding: '3px 9px', borderRadius: 20, background: 'rgba(34,197,94,.1)', border: '1px solid rgba(34,197,94,.2)' }}>✓ q2.html</span>
          <span style={{ fontSize: 10, color: '#60a5fa', fontWeight: 600, padding: '3px 9px', borderRadius: 20, background: 'rgba(59,130,246,.1)', border: '1px solid rgba(59,130,246,.2)' }}>⊶ lineage</span>
        </div>
      </div>

      {/* Bar chart */}
      <div>
        <div style={{ fontSize: 9.5, fontWeight: 700, color: '#3d5278', textTransform: 'uppercase', letterSpacing: .7, marginBottom: 9 }}>Revenue by Region</div>
        {REPORT_DATA.map(d => (
          <div key={d.region} style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
            <div style={{ width: 36, fontSize: 10.5, color: '#64748b', textAlign: 'right', flexShrink: 0 }}>{d.region}</div>
            <div style={{ flex: 1, height: 20, background: 'rgba(255,255,255,.04)', borderRadius: 4, overflow: 'hidden' }}>
              <div style={{
                width: `${(d.revenue / REPORT_MAX) * 100}%`, height: '100%',
                background: 'linear-gradient(90deg, rgba(37,99,235,.7), rgba(124,58,237,.7))',
                borderRadius: 4, display: 'flex', alignItems: 'center', paddingLeft: 8,
              }}>
                <span style={{ fontSize: 10, fontWeight: 700, color: 'rgba(255,255,255,.8)', fontFamily: 'Cascadia Code, Fira Code, monospace', whiteSpace: 'nowrap' }}>
                  ${(d.revenue / 1000).toFixed(0)}K
                </span>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Table */}
      <div>
        <div style={{ fontSize: 9.5, fontWeight: 700, color: '#3d5278', textTransform: 'uppercase', letterSpacing: .7, marginBottom: 7 }}>Detail</div>
        <div style={{ border: '1px solid rgba(255,255,255,.07)', borderRadius: 6, overflow: 'hidden' }}>
          <table style={{ width: '100%', fontSize: 11, borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ background: 'rgba(0,0,0,.25)' }}>
                {['Region','Revenue','Margin','Margin %'].map(h => (
                  <th key={h} style={{ padding: '5px 10px', textAlign: h === 'Region' ? 'left' : 'right', color: '#3d5278', fontWeight: 700, fontSize: 9, textTransform: 'uppercase', letterSpacing: .5 }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {REPORT_DATA.map(d => (
                <tr key={d.region} style={{ borderTop: '1px solid rgba(255,255,255,.04)' }}>
                  <td style={{ padding: '5px 10px', color: '#94a3b8' }}>{d.region}</td>
                  <td style={{ padding: '5px 10px', color: '#e2e8f0', textAlign: 'right', fontFamily: 'monospace' }}>${d.revenue.toLocaleString()}</td>
                  <td style={{ padding: '5px 10px', color: '#4ade80', textAlign: 'right', fontFamily: 'monospace' }}>${d.margin.toLocaleString()}</td>
                  <td style={{ padding: '5px 10px', color: '#94a3b8', textAlign: 'right', fontFamily: 'monospace' }}>{((d.margin / d.revenue) * 100).toFixed(1)}%</td>
                </tr>
              ))}
              <tr style={{ borderTop: '1px solid rgba(255,255,255,.1)', background: 'rgba(59,130,246,.06)' }}>
                <td style={{ padding: '5px 10px', color: '#64748b', fontWeight: 700, fontSize: 10.5 }}>Total</td>
                <td style={{ padding: '5px 10px', color: '#93c5fd', textAlign: 'right', fontFamily: 'monospace', fontWeight: 700 }}>$781,550</td>
                <td style={{ padding: '5px 10px', color: '#4ade80', textAlign: 'right', fontFamily: 'monospace', fontWeight: 700 }}>$170,110</td>
                <td style={{ padding: '5px 10px', color: '#94a3b8', textAlign: 'right', fontFamily: 'monospace', fontWeight: 700 }}>21.8%</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

// ── Code view ─────────────────────────────────────────────────────────────────

function CodeView({ code, chars }) {
  const visible = code.slice(0, chars)
  const done = chars >= code.length
  const lines = visible.split('\n')
  return (
    <pre style={{
      fontFamily: "'Cascadia Code', 'Fira Code', Consolas, monospace",
      fontSize: 12.5, lineHeight: 1.75, margin: 0, tabSize: 2,
      color: '#b8cce8', whiteSpace: 'pre-wrap', wordBreak: 'break-word',
    }}>
      {lines.map((line, i) => {
        const isComment = line.trimStart().startsWith('#')
        const isKeyword = /^(from|import|def|class|return|if|else|for|with)\b/.test(line.trimStart())
        const color = isComment ? '#4a6280' : isKeyword ? '#93c5fd' : '#b8cce8'
        const isLast = i === lines.length - 1
        return (
          <span key={i}>
            <span style={{ color, fontStyle: isComment ? 'italic' : 'normal' }}>{line}</span>
            {isLast && !done && (
              <span className="cursor-blink" style={{
                display: 'inline-block', width: 2, height: '0.9em',
                background: '#60a5fa', marginLeft: 1, verticalAlign: 'text-bottom',
              }} />
            )}
            {i < lines.length - 1 && '\n'}
          </span>
        )
      })}
    </pre>
  )
}

// ── Player ────────────────────────────────────────────────────────────────────

function DemoPlayer() {
  const [stepIdx, setStepIdx] = useState(0)
  const [chars, setChars] = useState(0)
  const [shownOutputs, setShownOutputs] = useState(0)
  const [playing, setPlaying] = useState(true)
  const tm = useRef(null)

  const step = DEMO_STEPS[stepIdx]
  const isReport = step.outputType === 'report'

  useEffect(() => {
    clearTimeout(tm.current)
    setChars(0)
    setShownOutputs(0)
  }, [stepIdx])

  useEffect(() => {
    if (!playing) { clearTimeout(tm.current); return }
    clearTimeout(tm.current)
    const codeLen = step.code.length
    const outLen  = step.output.length

    if (chars < codeLen) {
      tm.current = setTimeout(() => setChars(c => Math.min(c + CHARS_PER_TICK, codeLen)), TICK_MS)
    } else if (isReport && shownOutputs === 0) {
      // show report preview after a brief pause
      tm.current = setTimeout(() => setShownOutputs(1), 700)
    } else if (!isReport && shownOutputs < outLen) {
      tm.current = setTimeout(() => setShownOutputs(s => s + 1), OUTPUT_DELAY_MS)
    } else {
      tm.current = setTimeout(() => setStepIdx(i => (i + 1) % DEMO_STEPS.length), STEP_PAUSE_MS)
    }
    return () => clearTimeout(tm.current)
  }, [chars, shownOutputs, playing, step, isReport])

  const progress = ((stepIdx + Math.min(chars / (step.code.length || 1), 1)) / DEMO_STEPS.length) * 100
  const showPreview = isReport && shownOutputs > 0
  const outputVisible = !isReport && shownOutputs > 0

  return (
    <div style={{
      background: 'var(--terminal-bg-2)',
      border: '1px solid var(--terminal-border)',
      borderRadius: 14,
      overflow: 'hidden',
      marginBottom: 32,
      boxShadow: '0 16px 44px rgba(23,37,84,.22)',
    }}>

      {/* Chrome */}
      <div style={{
        background: 'rgba(0,0,0,.35)',
        borderBottom: '1px solid rgba(255,255,255,.06)',
        padding: '11px 18px',
        display: 'flex', alignItems: 'center', gap: 12,
        userSelect: 'none',
      }}>
        <div style={{ display: 'flex', gap: 6 }}>
          {['#ef4444', '#f59e0b', '#22c55e'].map(c => (
            <div key={c} style={{ width: 11, height: 11, borderRadius: '50%', background: c, opacity: .75 }} />
          ))}
        </div>
        <div style={{ flex: 1, textAlign: 'center', fontSize: 11.5, color: '#3d5278', fontWeight: 600, letterSpacing: .3 }}>
          tracebi — interactive demo
        </div>
        <button onClick={() => setPlaying(p => !p)} title={playing ? 'Pause' : 'Play'} style={{
          background: playing ? 'rgba(34,197,94,.12)' : 'rgba(255,255,255,.06)',
          border: `1px solid ${playing ? 'rgba(34,197,94,.28)' : 'rgba(255,255,255,.08)'}`,
          borderRadius: 6, cursor: 'pointer', padding: '3px 10px',
          color: playing ? '#4ade80' : '#64748b',
          fontSize: 11, fontWeight: 700, letterSpacing: .3,
        }}>
          {playing ? '⏸ LIVE' : '▶ PLAY'}
        </button>
      </div>

      {/* Body — fixed height so window never resizes */}
      <div style={{ display: 'flex', height: 430 }}>

        {/* Step navigation */}
        <div style={{
          width: 210, flexShrink: 0, height: '100%', overflowY: 'auto',
          borderRight: '1px solid rgba(255,255,255,.06)',
          paddingTop: 6, paddingBottom: 6,
        }}>
          {DEMO_STEPS.map((s, i) => {
            const active = stepIdx === i
            const done   = stepIdx > i
            return (
              <button key={i} onClick={() => { setStepIdx(i); setPlaying(true) }} style={{
                width: '100%', padding: '11px 16px 11px 14px',
                background: active ? 'rgba(59,130,246,.1)' : 'none',
                border: 'none', borderLeft: `2px solid ${active ? '#3b82f6' : 'transparent'}`,
                cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 10,
                textAlign: 'left', transition: 'background var(--t)',
              }}>
                <div style={{
                  width: 30, height: 30, borderRadius: 8, flexShrink: 0,
                  background: active ? 'linear-gradient(135deg,#2563eb,#7c3aed)' : done ? 'rgba(34,197,94,.12)' : 'rgba(255,255,255,.05)',
                  border: active ? 'none' : done ? '1px solid rgba(34,197,94,.3)' : '1px solid rgba(255,255,255,.08)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: done && !active ? 13 : 15,
                  boxShadow: active ? '0 2px 10px rgba(124,58,237,.4)' : 'none',
                  transition: 'all var(--t)',
                }}>{done && !active ? '✓' : s.icon}</div>
                <div>
                  <div style={{ fontSize: 10, color: active ? '#60a5fa' : '#3d5278', fontWeight: 700, textTransform: 'uppercase', letterSpacing: .5, marginBottom: 1 }}>
                    Step {i + 1}
                  </div>
                  <div style={{ fontSize: 12.5, fontWeight: active ? 700 : 500, color: active ? '#e2e8f0' : '#4a6280', lineHeight: 1.2 }}>
                    {s.label}
                  </div>
                </div>
              </button>
            )
          })}
        </div>

        {/* Right panel — flex column, fills fixed height */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>

          {/* Step header */}
          <div style={{
            flexShrink: 0, padding: '14px 24px 12px',
            borderBottom: '1px solid rgba(255,255,255,.05)',
            background: 'rgba(0,0,0,.15)',
          }}>
            <div style={{ fontSize: 13.5, fontWeight: 700, color: '#d1ddf5', marginBottom: 3 }}>{step.title}</div>
            <p style={{ fontSize: 11.5, color: '#4a6280', lineHeight: 1.5, margin: 0 }}>{step.desc}</p>
          </div>

          {/* Code area — scrollable, report preview overlaid when done */}
          <div style={{ flex: 1, position: 'relative', overflow: 'hidden' }}>
            {/* Code — fades out when report preview shows */}
            <div style={{
              position: 'absolute', inset: 0, overflowY: 'auto',
              padding: '16px 24px 14px',
              opacity: showPreview ? 0 : 1,
              transition: 'opacity 0.55s ease',
            }}>
              <CodeView code={step.code} chars={chars} />
            </div>
            {/* Report preview — fades in after typing completes */}
            {isReport && (
              <div style={{
                position: 'absolute', inset: 0, overflowY: 'auto',
                opacity: showPreview ? 1 : 0,
                transition: 'opacity 0.55s ease',
                pointerEvents: showPreview ? 'auto' : 'none',
              }}>
                <ReportPreview />
              </div>
            )}
          </div>

          {/* Terminal output — slides up from bottom, hidden for report step */}
          <div style={{
            flexShrink: 0,
            height: outputVisible ? 118 : 0,
            overflow: 'hidden',
            transition: 'height 0.35s cubic-bezier(.4,0,.2,1)',
            borderTop: outputVisible ? '1px solid rgba(255,255,255,.06)' : 'none',
            background: 'rgba(0,0,0,.28)',
          }}>
            <div style={{ padding: '10px 24px 12px' }}>
              {step.output.slice(0, shownOutputs).map((line, i) => (
                <div key={i} className="fade-in" style={{
                  fontFamily: "'Cascadia Code', 'Fira Code', monospace",
                  fontSize: 12, lineHeight: 1.7,
                  color: line.ok ? '#4ade80' : (line.color || '#64748b'),
                  display: 'flex', alignItems: 'baseline', gap: 8,
                }}>
                  <span style={{ color: '#1e3050', flexShrink: 0 }}>$</span>
                  {line.ok && <span style={{ color: '#16a34a', flexShrink: 0 }}>✓</span>}
                  <span>{line.text}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Progress bar */}
      <div style={{ height: 3, background: 'rgba(255,255,255,.04)' }}>
        <div style={{
          height: '100%',
          background: 'linear-gradient(90deg, #3b82f6, #7c3aed)',
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
