import { Link } from 'react-router-dom'
import { useGuides } from '../api'
import { PageTitle, PageSub, CodeBlock } from '../components/Shared'

const STEPS = [
  {
    n: 1,
    title: 'Install',
    desc: 'One install gets you connectors, transforms, reports, and the CLI.',
    code: `pip install "tracebi[analyst]"`,
  },
  {
    n: 2,
    title: 'Connect to your data',
    desc: 'Register a connector and define a DataModel. Mix sources — SQL, CSV, BigQuery — and reference them all by name.',
    code: `from tracebi import DataModel, SQLConnector

db = SQLConnector("sales_db", url="sqlite:///data/sales.db")

model = DataModel("SalesModel")
model.add_connector(db)
model.add_table("orders", connector="sales_db", source="orders")
model.connect()`,
  },
  {
    n: 3,
    title: 'Load and transform',
    desc: 'Every method returns a new immutable DataSet with the step appended to its lineage chain.',
    code: `orders = model.load("orders")

result = (
    orders
    .filter("status == 'shipped'", description="Shipped orders only")
    .transform(
        lambda df: df.assign(margin=df["revenue"] - df["cost"]),
        description="margin = revenue - cost",
    )
    .sort("margin", ascending=False)
)

result.print_lineage()
# Step 1: [LOAD]       Loaded 'orders' from 'sales_db'
# Step 2: [FILTER]     Shipped orders only  (250 → 198 rows)
# Step 3: [TRANSFORM]  margin = revenue - cost
# Step 4: [SORT]       Sorted by margin (desc)`,
  },
  {
    n: 4,
    title: 'Build and verify a report',
    desc: 'Point a report spec at your model and build a self-contained HTML artifact — every figure a live query, backed by an embedded, fingerprinted receipt you can re-check offline.',
    code: `# reports/revenue.json — a spec that queries your model
$ tracebi report build revenue
  → output/revenue.html                # self-contained: data + receipt inlined
  → output/revenue.html.manifest.json  # the lineage manifest

$ tracebi verify output/revenue.html.manifest.json
  ✓ every figure re-runs and reproduces`,
  },
  {
    n: 5,
    title: 'Author from the CLI',
    desc: 'Scaffold a report package, live-preview it while you edit, then serve the published portal — the CLI handles the whole loop.',
    code: `# Scaffold a report package (report.json + template.html + style.css)
tracebi new-report "revenue by region"

# Live-preview while you edit — exploration blocks that die at build
tracebi dev revenue_by_region   # → http://localhost:8001

# Serve the published portal (Reports page surfaces every artifact)
python -m tracebi.web.run       # → http://localhost:8000`,
  },
]

const LINK_STYLE = {
  display: 'inline-flex', alignItems: 'center', gap: 5,
  padding: '7px 14px', borderRadius: 7, fontSize: 12, fontWeight: 600,
  background: 'var(--blue-lt)', color: 'var(--accent-text)',
  border: '1px solid var(--blue-br)', textDecoration: 'none',
}

// ── Guides (markdown from docs/, served by /api/docs) ─────────────────────────

function Guides() {
  // The docs live on their own page now — the vault outgrew a flat row of
  // buttons the moment docs/ became a tree. This is the pointer to it.
  const { data: guides, isLoading } = useGuides()
  if (isLoading || !guides?.length) return null
  return (
    <div style={{ marginBottom: 40 }}>
      <div style={{ fontWeight: 700, fontSize: 15, color: 'var(--text)', marginBottom: 4 }}>Docs</div>
      <p style={{ fontSize: 13, color: 'var(--muted)', marginBottom: 14 }}>
        The full handbook — concepts, guides and reference, versioned in <code>docs/</code>.
      </p>
      <Link to="/handbook" style={{ ...LINK_STYLE, fontSize: 12.5 }}>
        ☰ Browse the docs ({guides.length} pages)
      </Link>
    </div>
  )
}

export default function GettingStarted() {
  return (
    <div>
      <PageTitle>Getting started</PageTitle>
      <PageSub>Five steps from install to your first lineage-tracked report.</PageSub>

      <Guides />

      <div style={{ display: 'flex', flexDirection: 'column', gap: 14, marginBottom: 40 }}>
        {STEPS.map(s => (
          <div key={s.n} style={{
            display: 'flex', gap: 18, alignItems: 'flex-start',
            background: 'var(--card)', border: '1px solid var(--border)',
            borderRadius: 12, padding: '20px 24px',
          }}>
            <div style={{
              width: 34, height: 34, borderRadius: 8, flexShrink: 0, marginTop: 1,
              background: 'linear-gradient(135deg, rgba(37,99,235,.12), rgba(124,58,237,.12))',
              border: '1px solid rgba(124,58,237,.22)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 14, fontWeight: 800, color: '#6d28d9',
            }}>{s.n}</div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontWeight: 700, fontSize: 14, color: 'var(--text)', marginBottom: 5 }}>{s.title}</div>
              <p style={{ fontSize: 13, color: 'var(--muted)', lineHeight: 1.6, marginBottom: 12 }}>{s.desc}</p>
              <CodeBlock>{s.code}</CodeBlock>
            </div>
          </div>
        ))}
      </div>

      <div style={{
        background: 'var(--blue-lt)', border: '1px solid var(--blue-br)',
        borderRadius: 12, padding: '20px 24px',
      }}>
        <div style={{ fontWeight: 700, fontSize: 14, color: 'var(--text)', marginBottom: 12 }}>Go deeper</div>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <Link to="/connectors" style={LINK_STYLE}>⇌ Connectors</Link>
          <Link to="/models" style={LINK_STYLE}>⬡ Data Models</Link>
          <Link to="/pipelines" style={LINK_STYLE}>⧖ Pipelines</Link>
          <Link to="/reports" style={LINK_STYLE}>▤ Reports</Link>
          <Link to="/explore" style={LINK_STYLE}>◬ Explore</Link>
        </div>
      </div>
    </div>
  )
}
