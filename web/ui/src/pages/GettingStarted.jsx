import { useEffect } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useGuides } from '../api'
import { PageTitle, PageSub, CodeBlock } from '../components/Shared'
import { ThreePhases } from '../components/ThreePhases'

const STEPS = [
  {
    n: 1,
    title: 'Install and scaffold',
    desc: 'One install, then a project with the three folders the workflow uses.',
    code: `pip install "tracebi[analyst]"
tracebi init`,
  },
  {
    n: 2,
    title: 'Sink the warehouse',
    desc: 'Phase ① is ordinary pandas in transforms/. It ends by writing named tables. The sink contract checks what landed.',
    code: `tracebi new-transform "holdings"
tracebi run-transform holdings`,
  },
  {
    n: 3,
    title: 'Declare the data model',
    desc: 'Phase ② is a DataModel in models/: grain, keys, measures. A reviewer reads it without opening the pandas above it.',
    code: `tracebi new-model "Portfolio"`,
  },
  {
    n: 4,
    title: 'Build the report and verify it',
    desc: 'Phase ③ is a package in reports/. tracebi dev opens it in this app with Build mode on. The build fills every figure from a query. verify re-runs those queries.',
    code: `tracebi new-report "portfolio"
tracebi dev portfolio
tracebi report build portfolio
tracebi verify output/portfolio.html.manifest.json`,
  },
  {
    n: 5,
    title: 'Open the app',
    desc: 'The published file is the thing a person approves. The app opens on Reports: every report, with its verdict. Data shows how each model is made.',
    code: `python -m tracebi.web.run
# → http://localhost:8000`,
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
      <h2 className="section-title">Docs</h2>
      <p style={{ fontSize: 13, color: 'var(--muted)', marginBottom: 14 }}>
        The full handbook — concepts, guides and reference, versioned in <code>docs/</code>.
      </p>
      <Link to="/handbook" style={{ ...LINK_STYLE, fontSize: 12.5 }}>
        ☰ Browse the docs ({guides.length} pages)
      </Link>
    </div>
  )
}

// How the pieces fit: four places, each for one job, in the sidebar's order,
// and who sees each (nav.js placesFor).
const PLACES = [
  { to: '/', name: 'Reports', text: <>
    Where the app opens: every report you may see, by folder, each with its verdict (whether
    its numbers still reproduce). A chip per model narrows the list. Open a report to read it as
    delivered; About this build holds its receipt, lineage, history and files. Everyone sees it.</> },
  { to: '/ask', name: 'Ask', text: <>
    Put a question to one model as a sentence of its own measures and categories; the answer is
    a live query, with each measure&rsquo;s definition and the query behind it. Keep this turns it
    into a draft report; Advanced is the query builder. Everyone sees it.</> },
  { to: '/data', name: 'Data', text: <>
    How the numbers are made. The models, one row each, or all of them as one picture (Map).
    A model's page leads with its line, transform → model → reports, then tabs: Model,
    Transform (where Refresh data is), Sources and Runs. Only admins see it.</> },
  { to: '/review', name: 'Review', text: <>
    What waits on a person, in four tabs: Attention (a refresh that failed, a build that needs a
    look, a request to publish), Drafts, History (what ran and when) and Verify (a file you were
    sent). Analysts and admins see it.</> },
]

function HowItFits() {
  return (
    <div style={{ marginBottom: 36 }}>
      <h2 className="section-title">How the app fits together</h2>
      <dl style={{ fontSize: 13, color: 'var(--muted)', lineHeight: 1.6, margin: 0, maxWidth: '74ch' }}>
        {PLACES.map(p => (
          <div key={p.to} style={{ marginBottom: 10 }}>
            <dt style={{ fontWeight: 600 }}><Link to={p.to}>{p.name}</Link></dt>
            <dd style={{ margin: 0 }}>{p.text}</dd>
          </div>
        ))}
      </dl>
      <p style={{ fontSize: 13, color: 'var(--muted)', lineHeight: 1.6, margin: 0, maxWidth: '74ch' }}>
        With no sign-in, everyone sees all four.
      </p>
    </div>
  )
}

export default function GettingStarted() {
  // /workflow (now a section here) and other links land on a section by hash.
  const { hash } = useLocation()
  useEffect(() => {
    if (hash) document.getElementById(hash.slice(1))?.scrollIntoView()
  }, [hash])
  return (
    <div>
      <PageTitle>Get started</PageTitle>
      <PageSub>Every number, traced. How TraceBi fits together, then five steps from install to your first report with a receipt.</PageSub>

      <HowItFits />

      <section id="phases" style={{ marginBottom: 40 }}>
        <h2 className="section-title">The three phases</h2>
        <p className="section-sub">
          From a messy source to a served report. Each phase has its own folder and its own pace,
          and hands the next a frozen artifact, so slow analysis and fast reporting never block
          each other.
        </p>
        <ThreePhases />
      </section>

      <h2 className="section-title" id="steps">Five steps</h2>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14, marginBottom: 40 }}>
        {STEPS.map(s => (
          <div key={s.n} style={{
            display: 'flex', gap: 18, alignItems: 'flex-start',
            background: 'var(--card)', border: '1px solid var(--border)',
            borderRadius: 12, padding: '20px 24px',
          }}>
            <div style={{
              width: 34, height: 34, borderRadius: 8, flexShrink: 0, marginTop: 1,
              background: 'var(--surface-2)',
              border: '1px solid var(--border)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 14, fontWeight: 600, color: 'var(--text)',
            }}>{s.n}</div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontWeight: 600, fontSize: 14, color: 'var(--text)', marginBottom: 5 }}>{s.title}</div>
              <p style={{ fontSize: 13, color: 'var(--muted)', lineHeight: 1.6, marginBottom: 12 }}>{s.desc}</p>
              <CodeBlock>{s.code}</CodeBlock>
            </div>
          </div>
        ))}
      </div>

      <Guides />

      <div style={{
        background: 'var(--blue-lt)', border: '1px solid var(--blue-br)',
        borderRadius: 12, padding: '20px 24px',
      }}>
        <div style={{ fontWeight: 600, fontSize: 14, color: 'var(--text)', marginBottom: 12 }}>Go deeper</div>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <Link to="/" style={LINK_STYLE}>Reports</Link>
          <Link to="/data" style={LINK_STYLE}>Data</Link>
        </div>
      </div>
    </div>
  )
}
