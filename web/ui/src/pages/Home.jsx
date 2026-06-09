import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useConnectors, useModels, useReports, usePipelines } from '../api'
import { StatTile, CodeBlock, Card, CardTitle, Btn } from '../components/Shared'

// ── Data ──────────────────────────────────────────────────────────────────────

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
      { t: 'c', v: '# Visualise as a DAG' },
      { t: 'n', v: 'from tracebi.lineage.diagram import LineageDiagram\nLineageDiagram(result).to_html("lineage.html")' },
    ],
  },
  {
    n: 3,
    title: 'Landing → Manipulation → Final',
    body: `Three named layers, each with a distinct purpose. Landing / Manipulation / Final are
the canonical names; Bronze / Silver / Gold remain as aliases — pick the vocabulary that
fits your team.

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
  { icon: '⇌', color: '#34d399', title: 'Connectors', desc: 'CSV, SQL (any SQLAlchemy dialect), BigQuery, Snowflake, DuckDB, and in-memory DataFrames — all sharing the same connector.load() interface.' },
  { icon: '⬡', color: '#a78bfa', title: 'Data Models', desc: 'Associative model linking multiple DataSets by key. Add star-schema roles to get a fully declarative query surface over DuckDB.' },
  { icon: '⧖', color: '#fbbf24', title: 'Pipelines', desc: 'Register layers with cron schedules and dependencies. Every run writes row counts and upstream IDs to SQLite — full chain provenance.' },
  { icon: '▤', color: '#f472b6', title: 'Reports', desc: 'Compose from TextSection, TableSection, ChartSection. Render to Excel or HTML. A lineage manifest is written alongside every render.' },
  { icon: '◫', color: '#22d3ee', title: 'Dashboards', desc: 'Interactive Dash app with associative filter panels — selecting one panel auto-filters every panel sharing that column.' },
  { icon: '⊶', color: '#60a5fa', title: 'Lineage', desc: 'Every DataSet carries its full audit trail. Export to matplotlib, Mermaid, or interactive HTML. View the DAG for any report from the web UI.' },
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
    desc: 'Landing → Manipulation → Final mirrors the medallion pattern. Each layer reads from the previous sink, applies its transformations, and writes output — so every run is reproducible.',
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
from tracebi.reports.excel_renderer import ExcelRenderer
from tracebi.reports.html_renderer import HTMLRenderer

report = (
  Report("Q2 Sales Report")
  .author("Data Team")
  .parameter("period", "Q2 2024")
  .add(TextSection(title="Summary", content="...", style="heading1"))
  .add(ChartSection(title="Revenue by Region", dataset=gold_ds,
                    chart_type="bar", x="dim_customer.region", y="revenue"))
  .add(TableSection(title="Detail", dataset=gold_ds,
                    columns=["dim_customer.region", "revenue"],
                    totals=["revenue"]))
)

ExcelRenderer().render(report, "output/q2_sales.xlsx")
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

# Full refresh — runs all three in dependency order
runner.run("revenue_by_region", refresh=True)

runner.start()  # Start APScheduler (blocking)`,
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

// ── Sub-components ────────────────────────────────────────────────────────────

function ConceptCode({ lines }) {
  const colorMap = { c: '#4a6080', b: '#fbbf24', s: '#94a3b8', g: '#fde68a' }
  return (
    <pre className="code-block" style={{ fontSize: 11.5, lineHeight: 1.75 }}>
      {lines.map((l, i) => (
        l.t === 'n'
          ? <span key={i}>{l.v}</span>
          : <span key={i} style={{ color: colorMap[l.t] || '#4a6080' }}>{l.v}</span>
      )).reduce((acc, el, i) => i > 0 ? [...acc, '\n', el] : [el], [])}
    </pre>
  )
}

function SectionHeader({ title, sub }) {
  return (
    <div style={{ marginBottom: 24, marginTop: 8 }}>
      <h2 className="gradient-text" style={{
        fontSize: 22, fontWeight: 800, marginBottom: 4, letterSpacing: -.2,
      }}>{title}</h2>
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
      {/* ── Hero ─────────────────────────────────────────────────────────── */}
      <div style={{
        background: 'rgba(8,14,30,0.7)',
        backdropFilter: 'blur(12px)',
        WebkitBackdropFilter: 'blur(12px)',
        border: '1px solid var(--border)',
        borderRadius: 16,
        padding: '52px 52px 48px',
        marginBottom: 28,
        position: 'relative',
        overflow: 'hidden',
        backgroundImage: `url("data:image/svg+xml,%3Csvg width='40' height='40' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M 40 0 L 0 0 0 40' fill='none' stroke='rgba(59,130,246,0.06)' stroke-width='1'/%3E%3C/svg%3E")`,
      }}>
        {/* Radial glow */}
        <div style={{
          position: 'absolute', top: -80, right: -80, width: 340, height: 340,
          background: 'radial-gradient(circle, rgba(124,58,237,.14) 0%, transparent 65%)',
          pointerEvents: 'none',
        }} />
        <div style={{
          position: 'absolute', bottom: -40, left: '30%', width: 240, height: 240,
          background: 'radial-gradient(circle, rgba(59,130,246,.1) 0%, transparent 65%)',
          pointerEvents: 'none',
        }} />

        <div style={{
          display: 'inline-flex', alignItems: 'center', gap: 7,
          padding: '4px 14px', marginBottom: 22,
          background: 'rgba(59,130,246,.1)',
          border: '1px solid rgba(59,130,246,.25)',
          borderRadius: 20, fontSize: 11, fontWeight: 700,
          color: '#93c5fd', letterSpacing: .8, textTransform: 'uppercase',
        }}>
          <span className="pulse-glow" style={{
            display: 'inline-block', width: 6, height: 6,
            borderRadius: '50%', background: '#22c55e',
          }} />
          Code-first · Traceable · Open Source
        </div>

        <h2 style={{
          fontSize: 42, fontWeight: 900, lineHeight: 1.15, marginBottom: 16,
          background: 'linear-gradient(100deg, #f1f5f9 0%, #93c5fd 55%, #c4b5fd 100%)',
          WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent',
          backgroundClip: 'text', maxWidth: 600, letterSpacing: -.5,
        }}>
          Build analytics pipelines that explain themselves.
        </h2>

        <p style={{ fontSize: 15, color: '#64748b', lineHeight: 1.75, maxWidth: 540, marginBottom: 32 }}>
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
            transition: 'filter var(--t), box-shadow var(--t), transform var(--t)',
          }}>▤ View Reports</Link>
          <Link to="/models" style={{
            display: 'inline-flex', alignItems: 'center', gap: 7,
            padding: '11px 24px', borderRadius: 8, fontSize: 13, fontWeight: 600,
            background: 'rgba(59,130,246,.08)', color: '#93c5fd',
            border: '1px solid rgba(59,130,246,.28)', textDecoration: 'none',
            transition: 'background var(--t), border-color var(--t)',
          }}>⬡ Explore Models</Link>
          <Link to="/pipelines" style={{
            display: 'inline-flex', alignItems: 'center', gap: 7,
            padding: '11px 24px', borderRadius: 8, fontSize: 13, fontWeight: 600,
            background: 'rgba(251,191,36,.08)', color: '#fcd34d',
            border: '1px solid rgba(251,191,36,.22)', textDecoration: 'none',
            transition: 'background var(--t), border-color var(--t)',
          }}>⧖ Pipelines</Link>
        </div>
      </div>

      {/* ── Stats ────────────────────────────────────────────────────────── */}
      <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginBottom: 44 }}>
        {stats.map(s => (
          <StatTile key={s.label} value={s.value} label={s.label} color={s.color} icon={s.icon} />
        ))}
      </div>

      {/* ── Core Concepts ────────────────────────────────────────────────── */}
      <SectionHeader title="Core concepts" sub="Four ideas that everything else is built on." />

      {CONCEPTS.map(c => (
        <div key={c.n} className="card-accent" style={{
          background: 'var(--card)',
          backdropFilter: 'blur(8px)',
          WebkitBackdropFilter: 'blur(8px)',
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

      {/* ── What's included ──────────────────────────────────────────────── */}
      <SectionHeader title="What TraceBi includes" sub="Six building blocks — each independent, all composable." />

      <div className="grid-3" style={{ marginBottom: 44 }}>
        {FEATURES.map(f => (
          <div key={f.title} className="card-hover" style={{
            background: 'var(--card)',
            border: '1px solid var(--border)',
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

      {/* ── Walkthrough ──────────────────────────────────────────────────── */}
      <SectionHeader title="End-to-end walkthrough" sub="A complete pipeline from raw data to scheduled report." />

      <div style={{ marginBottom: 44 }}>
        <div style={{
          display: 'flex', flexWrap: 'wrap', gap: 4,
          padding: '6px 6px 0', marginBottom: 0,
          background: 'rgba(0,0,0,.25)',
          border: '1px solid var(--border)',
          borderBottom: 'none',
          borderRadius: '10px 10px 0 0',
        }}>
          {STEPS.map((s, i) => (
            <button key={i} onClick={() => setStep(i)} style={{
              padding: '7px 16px', border: 'none',
              background: step === i ? 'rgba(59,130,246,.15)' : 'none',
              fontSize: 12.5, fontWeight: 600,
              cursor: 'pointer',
              color: step === i ? '#93c5fd' : 'var(--muted)',
              borderRadius: '6px 6px 0 0',
              borderBottom: `2px solid ${step === i ? 'var(--blue)' : 'transparent'}`,
              transition: 'color var(--t), background var(--t)',
            }}>{s.label}</button>
          ))}
        </div>
        <div style={{
          background: 'var(--card)',
          backdropFilter: 'blur(8px)', WebkitBackdropFilter: 'blur(8px)',
          border: '1px solid var(--border)',
          borderTop: 'none',
          borderRadius: '0 0 10px 10px',
          padding: '22px 26px',
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

      {/* ── How to use it ────────────────────────────────────────────────── */}
      <SectionHeader title="Two ways to use TraceBi" />

      <div className="grid-2" style={{ marginBottom: 36 }}>
        <div className="card-hover" style={{
          background: 'var(--card)', border: '1px solid var(--border)',
          borderRadius: 12, padding: '22px 26px',
        }}>
          <div style={{
            display: 'inline-block', padding: '4px 12px', borderRadius: 20, fontSize: 11,
            fontWeight: 700, textTransform: 'uppercase', letterSpacing: .6,
            background: 'var(--blue-lt)', color: '#93c5fd',
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
            background: 'rgba(167,139,250,.12)', color: '#c4b5fd',
            border: '1px solid rgba(167,139,250,.25)', marginBottom: 14,
          }}>Web UI (this app)</div>
          <p style={{ fontSize: 13, color: 'var(--muted)', lineHeight: 1.7, marginBottom: 14 }}>
            Register connectors, models, reports, and pipelines in your app module.
            The web server surfaces them with run buttons, lineage diagrams, and a REST API.
          </p>
          <CodeBlock>{'# web/demo_app.py\nregistry.add_connector(my_connector)\nregistry.add_model(my_model)\nregistry.add_pipeline("sales", runner)\n\n@registry.report("my_report")\ndef my_report(): ...'}</CodeBlock>
        </div>
      </div>

      {/* ── Bottom row ───────────────────────────────────────────────────── */}
      <div className="grid-2" style={{ marginBottom: 8 }}>
        <div className="card-hover" style={{
          background: 'linear-gradient(135deg, rgba(10,20,55,.8), rgba(15,10,40,.8))',
          backdropFilter: 'blur(8px)', WebkitBackdropFilter: 'blur(8px)',
          border: '1px solid rgba(124,58,237,.3)',
          borderRadius: 12, padding: '22px 26px',
          position: 'relative', overflow: 'hidden',
        }}>
          <div style={{
            position: 'absolute', top: -20, right: -20, width: 140, height: 140,
            background: 'radial-gradient(circle, rgba(124,58,237,.2) 0%, transparent 65%)',
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
            borderRadius: 6, background: 'rgba(167,139,250,.12)',
            color: '#c4b5fd', border: '1px solid rgba(167,139,250,.3)',
            textDecoration: 'none',
          }}>Explore lineage →</Link>
        </div>

        <div className="card-hover" style={{
          background: 'linear-gradient(135deg, rgba(10,30,55,.8), rgba(5,18,40,.8))',
          backdropFilter: 'blur(8px)', WebkitBackdropFilter: 'blur(8px)',
          border: '1px solid rgba(59,130,246,.25)',
          borderRadius: 12, padding: '22px 26px',
          position: 'relative', overflow: 'hidden',
        }}>
          <div style={{
            position: 'absolute', top: -20, right: -20, width: 140, height: 140,
            background: 'radial-gradient(circle, rgba(59,130,246,.18) 0%, transparent 65%)',
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
              color: '#fff', textDecoration: 'none',
              boxShadow: '0 2px 10px rgba(59,130,246,.3)',
            }}>Swagger UI</a>
            <a href="/redoc" target="_blank" rel="noopener noreferrer" style={{
              display: 'inline-flex', padding: '6px 14px', fontSize: 12, fontWeight: 600,
              borderRadius: 6, background: 'transparent',
              color: '#93c5fd', border: '1px solid var(--blue-br)', textDecoration: 'none',
            }}>ReDoc</a>
          </div>
        </div>
      </div>
    </div>
  )
}
