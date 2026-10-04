import WorkflowDiagram from './WorkflowDiagram'

function Code({ children }) {
  return (
    <pre tabIndex={0} style={{
      background: 'var(--code-bg)', color: 'var(--code-text)',
      border: '1px solid var(--terminal-border)', borderRadius: 8,
      padding: '12px 14px', margin: 0, overflowX: 'auto',
      fontSize: 12, lineHeight: 1.6,
      fontFamily: "'Cascadia Code', 'Fira Code', monospace",
    }}>{children}</pre>
  )
}

function Card({ children, style }) {
  return (
    <div style={{
      background: 'var(--card)', border: '1px solid var(--border)',
      borderRadius: 14, padding: '20px 22px', ...style,
    }}>{children}</div>
  )
}

const PHASE_DETAIL = [
  {
    n: '1', color: 'var(--phase-transform)', folder: 'transforms/', title: 'Transform',
    lead: 'The phase the framework does not constrain. Pull the queries you need and write as much Python as the work takes — window functions, algorithmic passes, prose parsing, cleaning — then write the result into the warehouse.',
    point: 'The contract is not how you clean, it is what lands: the named tables at the end of the script.',
    code: `# transforms/holdings_transform.py
df = pd.read_csv(RAW)
df["issuer"] = parse_issuer(df["position"])   # any pandas you like
...
wh = DuckDBConnector("warehouse", database=WAREHOUSE)
wh.write(fact,  "fact_holdings")   # ← sink
wh.write(dim_issuer, "dim_issuer")`,
  },
  {
    n: '2', color: 'var(--phase-model)', folder: 'models/', title: 'Model',
    lead: 'A star schema over the warehouse. This is the reviewable contract — grain, keys and measures in a few dozen declarative lines. It reads the sink; it never sees the pandas above it.',
    point: 'A reviewer checks the model, not the transform. Change the shape here without touching the analysis.',
    code: `# models/portfolio_model.py
model = (DataModel("portfolio_model")
  .add_connector(DuckDBConnector("warehouse", database=WAREHOUSE))
  .add_table("fact_holdings", connector="warehouse", source="fact_holdings")
  .add_dimension("dim_issuer", table_name="dim_issuer", key_col="issuer_id",
                 attributes=["issuer", "sector"])
  .add_fact("fact_holdings", table_name="fact_holdings",
            measures=["fair_value"], foreign_keys={"dim_issuer": "issuer_id"})
  .add_measure("fair_value", column="fair_value", agg="sum", format="currency0"))`,
  },
  {
    n: '3', color: 'var(--phase-report)', folder: 'reports/', title: 'Report',
    lead: 'A spec pointed at the model. KPI cards, charts and tables, each a query. Because the model is materialized, the page re-renders in milliseconds — no pandas in the loop.',
    point: 'Edit the JSON to reshape the page. A metrics card whose value names a measure reads it live.',
    code: `// reports/portfolio_model/portfolio_dashboard.json
{ "type": "chart", "chart_type": "bar",
  "x": "dim_issuer.sector", "y": "fair_value",
  "data": { "model": "portfolio_model",
    "query": { "fact": "fact_holdings",
      "measures": ["fair_value"],
      "dimensions": ["dim_issuer.sector"] } } }`,
  },
]

/**
 * The three phases, with the freeze points between them: a section of
 * Get started (it was a page of its own that no menu led to).
 */
export function ThreePhases() {
  return (
    <div className="fade-in">
      <Card style={{ marginBottom: 28, padding: '26px 24px' }}>
        <WorkflowDiagram />
      </Card>

      <div style={{
        display: 'flex', gap: 12, alignItems: 'flex-start',
        background: 'var(--blue-lt)', border: '1px solid var(--blue-br)',
        borderRadius: 12, padding: '14px 18px', marginBottom: 32,
      }}>
        <span style={{ fontSize: 18, lineHeight: 1 }} aria-hidden="true">❄️</span>
        <p style={{ fontSize: 13, color: 'var(--text-2)', margin: 0, lineHeight: 1.6 }}>
          <strong style={{ color: 'var(--text)' }}>The freeze points are the whole idea.</strong>{' '}
          Once phase ① has run, the warehouse is a fixed input — phase ② is small enough to review as
          data, and phase ③ never touches pandas. Tracing lineage through the raw analysis is hard;
          this design doesn’t try to. It draws the line at the sink, where the numbers become a
          contract you can report against.
        </p>
      </div>

      {/* Per-phase detail */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 18, marginBottom: 32 }}>
        {PHASE_DETAIL.map(p => (
          <Card key={p.n} style={{ borderTop: `3px solid ${p.color}` }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
              <span style={{
                width: 26, height: 26, borderRadius: 7, flex: 'none',
                background: `color-mix(in srgb, ${p.color} 13%, transparent)`, border: `1px solid color-mix(in srgb, ${p.color} 27%, transparent)`,
                color: p.color, fontSize: 14, fontWeight: 800,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>{p.n}</span>
              <span style={{ fontSize: 17, fontWeight: 800, color: 'var(--text)' }}>{p.title}</span>
              <code style={{
                fontFamily: "'Cascadia Code', 'Fira Code', monospace", fontSize: 12,
                color: p.color, background: `color-mix(in srgb, ${p.color} 8%, transparent)`, border: `1px solid color-mix(in srgb, ${p.color} 16%, transparent)`,
                padding: '1px 8px', borderRadius: 5,
              }}>{p.folder}</code>
            </div>
            <div className="workflow-detail-grid">
              <div>
                <p style={{ fontSize: 13.5, color: 'var(--text-2)', lineHeight: 1.6, margin: '0 0 10px' }}>{p.lead}</p>
                <p style={{ fontSize: 12.5, color: 'var(--muted)', lineHeight: 1.55, margin: 0 }}>{p.point}</p>
              </div>
              <Code>{p.code}</Code>
            </div>
          </Card>
        ))}
      </div>

    </div>
  )
}
