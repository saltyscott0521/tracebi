import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useConnectors, useModels, useReports, usePipelines } from '../api'
import { StatTile, CodeBlock } from '../components/Shared'

const CONCEPTS = [
  {
    n: 1,
    title: 'DataSet — immutable by design',
    body: `The core data container in TraceBi is the DataSet — a thin wrapper around a pandas
DataFrame. The critical rule: every operation returns a new DataSet. Nothing mutates the original.

This means you can chain transformations freely — filter, transform, sort, rename, select —
and each step produces a clean, independent result. If you filter the wrong rows, the original
is still there. If you want to branch two different ways, both start from the same source.`,
    code: [
      { t: 'c', v: '# Every step returns a NEW DataSet — nothing mutates' },
      { t: 'n', v: 'orders = model.load("orders")' },
      { t: 'n', v: '' },
      { t: 'n', v: 'shipped = orders.filter("status == \'shipped\'")\nwith_margin = shipped.transform(\n  lambda df: df.assign(margin=df["revenue"] - df["cost"])\n)\ntop10 = with_margin.sort("margin", ascending=False)' },
      { t: 'n', v: '' },
      { t: 'c', v: '# Original is unchanged — still has all statuses' },
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

Because each operation appends a new node rather than replacing anything, a DataSet at the
end of a chain holds the complete history of everything that produced it — connector, filters,
joins, transforms, aggregations — traceable back to the original source.`,
    code: [
      { t: 'n', v: 'top10.print_lineage()' },
      { t: 'n', v: '' },
      { t: 'c', v: '# Step 1: [LOAD]       Loaded \'orders\' from \'sales_db\'' },
      { t: 'c', v: '# Step 2: [FILTER]     Shipped orders only (250 → 198 rows)' },
      { t: 'c', v: '# Step 3: [TRANSFORM]  margin = revenue - cost' },
      { t: 'c', v: '# Step 4: [SORT]       Sorted by margin (desc)' },
      { t: 'n', v: '' },
      { t: 'c', v: '# Or visualise as a DAG diagram' },
      { t: 'n', v: 'from tracebi.lineage.diagram import LineageDiagram\n\nLineageDiagram(top10).to_html("lineage.html")' },
    ],
  },
  {
    n: 3,
    title: 'Landing → Manipulation → Final (medallion-compatible)',
    body: `TraceBi structures pipelines as three named layers, each with a distinct purpose.
The new canonical names — Landing / Manipulation / Final — and the legacy medallion
names — Bronze / Silver / Gold — refer to the same classes; pick whichever vocabulary
fits your team.

Landing (Bronze) — Connect to upstream tables and ingest as-is. No transforms.
Acts as the permanent audit record of exactly what arrived.

Manipulation (Silver) — Optional light cleaning before serving. Type casting,
null removal, deduplication, column renames.

Final (Gold) — Serving layer. Groups measures by dimensions via a StarSchema
query (DuckDB-backed). Output feeds reports and dashboards directly.`,
    code: [
      { t: 'b', v: '# Landing — raw ingest, zero transforms' },
      { t: 'n', v: 'landing = LandingLayer(\n  connector=db, source="orders_raw",\n  sink=db, sink_table="orders_bronze",\n)' },
      { t: 'n', v: '' },
      { t: 's', v: '# Manipulation — declarative cleaning' },
      { t: 'n', v: 'manip = (\n  ManipulationLayer(source=db, source_table="orders_bronze",\n                    sink=db, sink_table="orders_silver")\n  .cast({"qty": "int64"})\n  .drop_nulls()\n  .deduplicate(subset=["order_id"])\n)' },
      { t: 'n', v: '' },
      { t: 'g', v: '# Final — aggregated via StarSchema' },
      { t: 'n', v: 'final = FinalLayer(\n  schema=schema, fact="fact_orders",\n  measures={"revenue": "sum"},\n  dimensions=["dim_customer.region"],\n  sink=db, sink_table="revenue_by_region",\n)' },
    ],
  },
  {
    n: 4,
    title: 'Star Schema — declarative analytics',
    body: `A StarSchema sits above the connector layer and adds BI semantics. You declare two
types of tables:

Facts — Transactional tables with numeric measures to aggregate (revenue, qty, count).

Dimensions — Lookup tables with categorical attributes to group by (region, segment, product).

Once defined, schema.query() is fully declarative. You describe the result you want —
which measures, grouped by which dimension attributes, filtered how — and TraceBi resolves
all the joins, applies filters, and aggregates automatically. You never write join logic by hand.`,
    code: [
      { t: 'n', v: 'schema = StarSchema("Sales", model=model)\n\nschema.add_dimension(\n  "dim_customer",\n  table_name="customers_silver",\n  key_col="customer_id",\n  attributes=["region", "segment"],\n)\nschema.add_fact(\n  "fact_orders",\n  table_name="orders_silver",\n  measures=["revenue", "qty"],\n  foreign_keys={"dim_customer": "customer_id"},\n)' },
      { t: 'n', v: '' },
      { t: 'c', v: '# Declarative query — joins resolved automatically' },
      { t: 'n', v: 'ds = schema.query(\n  fact="fact_orders",\n  measures={"revenue": "sum"},\n  dimensions=["dim_customer.region"],\n  filters={"status": "shipped"},\n)' },
    ],
  },
]

const FEATURES = [
  { icon: '⇌', title: 'Connectors', desc: 'CSV, SQL (any SQLAlchemy dialect), BigQuery, Snowflake, DuckDB, and in-memory DataFrames. All share connector.load(source, filter=..., columns=...) with push-down to source where possible.' },
  { icon: '⬡', title: 'Landing → Manipulation → Final', desc: 'Three-layer pipeline (medallion-compatible). Landing ingests as-is, Manipulation cleans declaratively, Final aggregates via StarSchema.' },
  { icon: '✦', title: 'Star Schema (DuckDB-backed)', desc: 'Declare facts and dimensions once. Query with dot-notation ("dim_customer.region"). Joins, filters and aggregations execute inside DuckDB; the result comes back as a pandas DataFrame.' },
  { icon: '▤', title: 'Reports', desc: 'Compose from TextSection, TableSection, ChartSection. Render to Excel, HTML, or PDF. A lineage manifest is written alongside every render.' },
  { icon: '⧖', title: 'Pipelines', desc: 'Register layers, assign cron schedules, declare dependencies. Run history persisted to SQLite with row counts and upstream run IDs.' },
  { icon: '◫', title: 'Dashboards', desc: 'Interactive dashboards with associative filters — selecting one panel auto-filters all others that share the same column.' },
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
    desc: 'Every method on DataSet returns a new immutable DataSet with the step appended to its lineage chain. Call print_lineage() at any point to see the full audit trail.',
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
    label: '3. Landing → Manipulation → Final',
    title: 'Structure as a three-layer pipeline',
    desc: 'Structure work as Landing → Manipulation → Final (the medallion Bronze/Silver/Gold classes are still exported as aliases). Each layer reads from the previous sink and writes output to the next.',
    code: `from tracebi import LandingLayer, ManipulationLayer, FinalLayer
from tracebi.model.star_schema import StarSchema

landing = LandingLayer(connector=db, source="orders_raw",
                       sink=db, sink_table="orders_bronze")

manip = (
  ManipulationLayer(source=db, source_table="orders_bronze",
                    sink=db, sink_table="orders_silver")
  .cast({"qty": "int64", "order_date": "datetime64[ns]"})
  .drop_nulls(subset=["order_id"])
  .deduplicate(subset=["order_id"])
)

final = FinalLayer(schema=schema, fact="fact_orders",
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
  .add(TextSection(title="Summary", content="Summary", style="heading1"))
  .add(ChartSection(title="Revenue by Region", dataset=gold_ds,
                    chart_type="bar", x="dim_customer.region", y="revenue"))
  .add(TableSection(title="Detail", dataset=gold_ds,
                    columns=["dim_customer.region", "revenue"],
                    totals=["revenue"]))
)

ExcelRenderer().render(report, "output/q2_sales.xlsx")
HTMLRenderer().render(report, "output/q2_sales.html")
HTMLRenderer().serve(report, port=8080)`,
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

# Run one layer on demand
runner.run("orders_silver")

# Full refresh — runs landing → manipulation → final in order
runner.run("revenue_by_region", refresh=True)

# Start the APScheduler (blocking)
runner.start()`,
  },
  {
    label: '6. Dashboard',
    title: 'Add a live dashboard',
    desc: 'Build a Dashboard from panel components — metrics, charts, tables, and filters. Filters are associative: selecting one panel updates every panel sharing that column.',
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
  const colorMap = { c: '#64748b', b: '#fbbf24', s: '#94a3b8', g: '#fde68a' }
  return (
    <pre className="code-block">
      {lines.map((l, i) => (
        l.t === 'n'
          ? <span key={i}>{l.v}</span>
          : <span key={i} style={{ color: colorMap[l.t] || '#64748b' }}>{l.v}</span>
      )).reduce((acc, el, i) => {
        if (i > 0) return [...acc, '\n', el]
        return [el]
      }, [])}
    </pre>
  )
}

export default function Home() {
  const { data: connectors } = useConnectors()
  const { data: models } = useModels()
  const { data: reports } = useReports()
  const { data: pipelines } = usePipelines()
  const [step, setStep] = useState(0)

  const stats = [
    { value: connectors?.length, label: `Connector${connectors?.length !== 1 ? 's' : ''}` },
    { value: models?.length,     label: `Data Model${models?.length !== 1 ? 's' : ''}` },
    { value: reports?.length,    label: `Report${reports?.length !== 1 ? 's' : ''}` },
    { value: pipelines?.length,  label: `Pipeline${pipelines?.length !== 1 ? 's' : ''}` },
  ]

  return (
    <div>
      {/* Hero */}
      <div style={{
        background: 'linear-gradient(135deg,#0d1835 0%,#0f1e40 50%,#0c1a38 100%)',
        border: '1px solid var(--border)', borderRadius: 14,
        padding: '52px 48px 48px', marginBottom: 32, position: 'relative', overflow: 'hidden',
      }}>
        <div style={{
          position: 'absolute', top: -60, right: -60, width: 280, height: 280,
          background: 'radial-gradient(circle,rgba(59,130,246,.12) 0%,transparent 70%)',
          pointerEvents: 'none',
        }} />
        <div style={{
          display: 'inline-block', padding: '4px 12px',
          background: 'var(--blue-lt)', border: '1px solid var(--blue-br)',
          borderRadius: 20, fontSize: 11, fontWeight: 700, color: '#93c5fd',
          letterSpacing: .8, textTransform: 'uppercase', marginBottom: 20,
        }}>Code-first · Traceable · Open Source</div>
        <h2 style={{
          fontSize: 36, fontWeight: 800, lineHeight: 1.2, marginBottom: 16,
          background: 'linear-gradient(90deg,#e2e8f0 0%,#93c5fd 60%,#a78bfa 100%)',
          WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', maxWidth: 560,
        }}>Build analytics pipelines that explain themselves.</h2>
        <p style={{ fontSize: 15, color: '#94a3b8', lineHeight: 1.7, maxWidth: 580, marginBottom: 28 }}>
          TraceBi is a Python framework for building BI workflows — from raw data ingestion
          to star schemas, reports, and dashboards — where every transformation is tracked
          with a full lineage chain. No black boxes. No mystery queries.
        </p>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          <Link to="/reports" style={{ display:'inline-flex', alignItems:'center', gap:6, padding:'10px 22px', borderRadius:6, fontSize:14, fontWeight:600, background:'linear-gradient(135deg,var(--blue),var(--blue-md))', color:'#fff', textDecoration:'none', boxShadow:'0 2px 12px rgba(59,130,246,.3)' }}>▤ View Reports</Link>
          <Link to="/models"  style={{ display:'inline-flex', alignItems:'center', gap:6, padding:'10px 22px', borderRadius:6, fontSize:14, fontWeight:600, background:'transparent', color:'var(--blue)', border:'1px solid var(--blue-br)', textDecoration:'none' }}>⊞ Explore Models</Link>
          <Link to="/pipelines" style={{ display:'inline-flex', alignItems:'center', gap:6, padding:'10px 22px', borderRadius:6, fontSize:14, fontWeight:600, background:'transparent', color:'var(--blue)', border:'1px solid var(--blue-br)', textDecoration:'none' }}>⧖ Pipelines</Link>
        </div>
      </div>

      {/* Stats */}
      <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginBottom: 40 }}>
        {stats.map(s => <StatTile key={s.label} value={s.value} label={s.label} />)}
      </div>

      {/* Core Concepts */}
      <div style={{ fontSize: 24, fontWeight: 700, color: 'var(--text)', marginBottom: 6 }}>Core concepts</div>
      <p style={{ fontSize: 13, color: 'var(--muted)', marginBottom: 24 }}>Four ideas that everything else is built on.</p>

      {CONCEPTS.map(c => (
        <div key={c.n} style={{ background:'var(--card)', border:'1px solid var(--border)', borderRadius:10, padding:'20px 24px', marginBottom:16 }}>
          <div className="concept-grid">
            <div>
              <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:12 }}>
                <div style={{ width:32, height:32, borderRadius:8, background:'var(--blue-lt)', border:'1px solid var(--blue-br)', display:'flex', alignItems:'center', justifyContent:'center', fontSize:15, fontWeight:800, color:'#93c5fd' }}>{c.n}</div>
                <div style={{ fontSize:16, fontWeight:700, color:'var(--text)' }}>{c.title}</div>
              </div>
              {c.body.split('\n\n').map((para, i) => (
                <p key={i} style={{ fontSize:13, color:'var(--muted)', lineHeight:1.7, marginBottom:10 }}>{para.trim()}</p>
              ))}
            </div>
            <ConceptCode lines={c.code} />
          </div>
        </div>
      ))}

      {/* Feature grid */}
      <div style={{ fontSize: 24, fontWeight: 700, color: 'var(--text)', marginBottom: 6, marginTop: 16 }}>What TraceBi includes</div>
      <p style={{ fontSize: 13, color: 'var(--muted)', marginBottom: 24 }}>Six building blocks — each independent, all composable.</p>

      <div className="grid-3" style={{ marginBottom:40 }}>
        {FEATURES.map(f => (
          <div key={f.title} style={{ background:'var(--card)', border:'1px solid var(--border)', borderRadius:10, padding:'20px 24px' }}>
            <div style={{ fontSize:26, marginBottom:12 }}>{f.icon}</div>
            <div style={{ fontWeight:700, fontSize:14, color:'var(--text)', marginBottom:6 }}>{f.title}</div>
            <p style={{ fontSize:13, color:'var(--muted)', lineHeight:1.6 }}>{f.desc}</p>
          </div>
        ))}
      </div>

      {/* Walkthrough */}
      <div style={{ fontSize: 24, fontWeight: 700, color: 'var(--text)', marginBottom: 6 }}>End-to-end walkthrough</div>
      <p style={{ fontSize: 13, color: 'var(--muted)', marginBottom: 0 }}>A complete pipeline from raw data to scheduled report.</p>

      <div style={{ marginBottom: 40 }}>
        <div style={{ display:'flex', borderBottom:'1px solid var(--border)', flexWrap:'wrap' }}>
          {STEPS.map((s, i) => (
            <button key={i} onClick={() => setStep(i)} style={{
              padding:'9px 18px', border:'none', background:'none', fontSize:13, fontWeight:600,
              cursor:'pointer', color: step===i ? 'var(--blue)' : 'var(--muted)',
              borderBottom: `2px solid ${step===i ? 'var(--blue)' : 'transparent'}`,
              marginBottom:-1, transition:'color .15s, border-color .15s',
            }}>{s.label}</button>
          ))}
        </div>
        <div style={{ background:'var(--card)', border:'1px solid var(--border)', borderTop:'none', borderRadius:'0 0 10px 10px', padding:'20px 24px' }}>
          <div style={{ fontWeight:700, fontSize:14, color:'var(--text)', marginBottom:8 }}>{STEPS[step].title}</div>
          <p style={{ fontSize:13, color:'var(--muted)', lineHeight:1.6, marginBottom:14 }}>{STEPS[step].desc}</p>
          <CodeBlock>{STEPS[step].code}</CodeBlock>
        </div>
      </div>

      {/* Usage options */}
      <div style={{ fontSize: 24, fontWeight: 700, color: 'var(--text)', marginBottom: 6 }}>How to use it</div>
      <p style={{ fontSize: 13, color: 'var(--muted)', marginBottom: 24 }}>Two ways to work with TraceBi.</p>

      <div className="grid-2" style={{ marginBottom:32 }}>
        <div style={{ background:'var(--card)', border:'1px solid var(--border)', borderRadius:10, padding:'20px 24px' }}>
          <div style={{ display:'inline-block', padding:'4px 10px', borderRadius:6, fontSize:11, fontWeight:700, textTransform:'uppercase', letterSpacing:.6, background:'var(--blue-lt)', color:'#93c5fd', border:'1px solid var(--blue-br)', marginBottom:14 }}>Option 1 — Python library</div>
          <p style={{ fontSize:13, color:'var(--muted)', lineHeight:1.6, marginBottom:14 }}>Install TraceBi and use it from a notebook or script. Build connectors, Landing/Manipulation/Final layers, star schema queries, and render reports to HTML, Excel, or PDF.</p>
          <CodeBlock>{'pip install -e ".[reports,pipeline,lineage,sql]"'}</CodeBlock>
          <p style={{ fontSize:12, color:'var(--muted)', margin:'10px 0 6px' }}>Then follow the walkthrough above:</p>
          <CodeBlock>{'python examples/phase25_example.py'}</CodeBlock>
        </div>
        <div style={{ background:'var(--card)', border:'1px solid var(--border)', borderRadius:10, padding:'20px 24px' }}>
          <div style={{ display:'inline-block', padding:'4px 10px', borderRadius:6, fontSize:11, fontWeight:700, textTransform:'uppercase', letterSpacing:.6, background:'rgba(167,139,250,.12)', color:'#c4b5fd', border:'1px solid rgba(167,139,250,.25)', marginBottom:14 }}>Option 2 — Web UI (this app)</div>
          <p style={{ fontSize:13, color:'var(--muted)', lineHeight:1.6, marginBottom:14 }}>Register connectors, models, reports, and pipelines in your app module. The web server surfaces them with run buttons, lineage diagrams, and a REST API.</p>
          <CodeBlock>{'# web/demo_app.py\nregistry.add_connector(my_connector)\nregistry.add_model(my_model)\nregistry.add_pipeline("sales", runner)\n\n@registry.report("my_report")\ndef my_report(): ...'}</CodeBlock>
        </div>
      </div>

      {/* Bottom row */}
      <div className="grid-2">
        <div style={{ background:'linear-gradient(135deg,#0d1835 0%,#111827 100%)', border:'1px solid var(--blue-br)', borderRadius:10, padding:'20px 24px' }}>
          <div style={{ fontSize:22, marginBottom:10 }}>⊶</div>
          <div style={{ fontWeight:700, fontSize:14, color:'var(--text)', marginBottom:8 }}>Full lineage, always</div>
          <p style={{ fontSize:13, color:'var(--muted)', lineHeight:1.6 }}>Every DataSet carries a chain of LineageNode records describing exactly which connector, transformation, and timestamp produced each result. Run any report to visualise the full DAG.</p>
          <Link to="/reports" style={{ display:'inline-flex', marginTop:16, padding:'5px 11px', fontSize:12, fontWeight:600, borderRadius:6, background:'transparent', color:'var(--blue)', border:'1px solid var(--blue-br)', textDecoration:'none' }}>Explore lineage →</Link>
        </div>
        <div style={{ background:'var(--card)', border:'1px solid var(--border)', borderRadius:10, padding:'20px 24px' }}>
          <div style={{ fontSize:22, marginBottom:10 }}>⬡</div>
          <div style={{ fontWeight:700, fontSize:14, color:'var(--text)', marginBottom:8 }}>REST API included</div>
          <p style={{ fontSize:13, color:'var(--muted)', lineHeight:1.6 }}>Every UI feature is backed by a documented REST API. Trigger report runs, kick pipeline layers, and pull lineage data programmatically.</p>
          <div style={{ marginTop:16, display:'flex', gap:10 }}>
            <a href="/docs" target="_blank" rel="noopener noreferrer" style={{ display:'inline-flex', padding:'5px 11px', fontSize:12, fontWeight:600, borderRadius:6, background:'linear-gradient(135deg,var(--blue),var(--blue-md))', color:'#fff', textDecoration:'none' }}>Swagger UI</a>
            <a href="/redoc" target="_blank" rel="noopener noreferrer" style={{ display:'inline-flex', padding:'5px 11px', fontSize:12, fontWeight:600, borderRadius:6, background:'transparent', color:'var(--blue)', border:'1px solid var(--blue-br)', textDecoration:'none' }}>ReDoc</a>
          </div>
        </div>
      </div>
    </div>
  )
}
