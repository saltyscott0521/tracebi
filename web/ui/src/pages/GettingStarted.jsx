import { useState } from 'react'
import { Link } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

import { useGuides, useGuide } from '../api'
import { PageTitle, PageSub, CodeBlock, Spinner } from '../components/Shared'

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
    title: 'Run from the CLI',
    desc: 'Scaffold a new script, run it, or start the web UI — the CLI handles all three.',
    code: `# Scaffold a new script
tracebi new-request "revenue by region"

# Run the script
tracebi run requests/revenue_by_region.py

# Start the web UI (Requests page surfaces all scripts)
python -m tracebi.web.run   # → http://localhost:8000`,
  },
]

const LINK_STYLE = {
  display: 'inline-flex', alignItems: 'center', gap: 5,
  padding: '7px 14px', borderRadius: 7, fontSize: 12, fontWeight: 600,
  background: 'var(--blue-lt)', color: 'var(--accent-text)',
  border: '1px solid var(--blue-br)', textDecoration: 'none',
}

// ── Guides (markdown from docs/, served by /api/docs) ─────────────────────────

function GuideReader({ name }) {
  const { data, isLoading, error } = useGuide(name)
  if (isLoading) return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: 20, color: 'var(--muted)', fontSize: 13 }}>
      <Spinner size={14} /> Loading guide…
    </div>
  )
  if (error) return <div style={{ padding: 16, color: 'var(--red-text)', fontSize: 13 }}>{error.message}</div>
  if (!data) return null
  return (
    <div className="markdown-doc fade-in">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          // Repo-relative links don't resolve inside the SPA — send them to nothing
          // useful is worse than opening the file path as text, so render as plain text.
          a: ({ href, children }) =>
            /^https?:\/\//.test(href || '')
              ? <a href={href} target="_blank" rel="noreferrer">{children}</a>
              : <span className="md-deadlink">{children}</span>,
        }}
      >
        {data.content}
      </ReactMarkdown>
    </div>
  )
}

function Guides() {
  const { data: guides, isLoading } = useGuides()
  const [active, setActive] = useState(null)

  if (isLoading || !guides?.length) return null

  return (
    <div style={{ marginBottom: 40 }}>
      <div style={{ fontWeight: 700, fontSize: 15, color: 'var(--text)', marginBottom: 4 }}>Guides</div>
      <p style={{ fontSize: 13, color: 'var(--muted)', marginBottom: 14 }}>
        The full handbooks — readable here, versioned in <code>docs/</code>.
      </p>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: active ? 16 : 0 }}>
        {guides.map(g => (
          <button
            key={g.name}
            onClick={() => setActive(active === g.name ? null : g.name)}
            style={{
              ...LINK_STYLE,
              cursor: 'pointer', fontFamily: 'inherit', fontSize: 12.5,
              background: active === g.name ? 'var(--blue)' : 'var(--blue-lt)',
              color: active === g.name ? '#fff' : 'var(--accent-text)',
            }}
          >
            ☰ {g.title}
          </button>
        ))}
      </div>
      {active && (
        <div style={{
          background: 'var(--card)', border: '1px solid var(--border)',
          borderRadius: 12, padding: '26px 30px', maxHeight: 640, overflowY: 'auto',
        }}>
          <GuideReader name={active} />
        </div>
      )}
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
