// The three-phase workflow, as a flowchart. Each phase is a folder with its
// own cadence; the pills between them are the freeze points — the materialized
// artifact that hands one phase to the next. Token-only colors so it holds in
// both themes.

const PHASES = [
  {
    n: '1',
    tag: 'transforms/',
    title: 'Transform',
    color: 'var(--phase-transform)',
    body: 'Pull the queries you need and run real Python — window functions, algorithms, cleaning — then sink the result.',
    cadence: 'runs rarely · code is unconstrained',
  },
  {
    n: '2',
    tag: 'models/',
    title: 'Model',
    color: 'var(--phase-model)',
    body: 'Declare a star schema over the warehouse — grain, keys, measures. A contract a reviewer reads in minutes, without opening the pandas.',
    cadence: 'changes deliberately',
  },
  {
    n: '3',
    tag: 'reports/',
    title: 'Report',
    color: 'var(--phase-report)',
    body: 'Point a spec at the model — KPI cards, charts, tables. Every figure a live query; edit and re-render in milliseconds.',
    cadence: 'iterate constantly',
  },
]

// what freezes between the phases
const HANDOFFS = [
  { label: 'warehouse.duckdb', sub: 'materialized tables' },
  { label: 'the model', sub: 'the semantic contract' },
]

// Each arrow carries a data packet along it, staggered by position (i), so
// the eye reads the diagram left to right the way the data moves.
function Arrow({ i = 0 }) {
  return (
    <svg className="wf-arrow" viewBox="0 0 24 24" width="22" height="22" fill="none"
      stroke="var(--muted)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M4 12h15" />
      <path d="M13 6l7 6-7 6" />
      <circle className="wf-packet" style={{ '--i': i }} cx="4" cy="12" r="2.4"
              fill="var(--accent-text)" stroke="none" />
    </svg>
  )
}

function Handoff({ label, sub, i }) {
  return (
    <div className="wf-handoff">
      <Arrow i={i} />
      <div className="wf-freeze" title="frozen between phases">
        <div className="wf-freeze-label">
          {label}
        </div>
        <div className="wf-freeze-sub">{sub}</div>
      </div>
      <Arrow i={i + 1} />
    </div>
  )
}

function Phase({ n, tag, title, color, body, cadence }) {
  return (
    <div className="wf-phase card-hover" style={{ '--wf': color, '--i': Number(n) - 1 }}>
      <div className="wf-phase-head">
        <span className="wf-num">{n}</span>
        <code className="wf-tag">{tag}</code>
      </div>
      <div className="wf-title">{title}</div>
      <p className="wf-body">{body}</p>
      <div className="wf-cadence">{cadence}</div>
    </div>
  )
}

export default function WorkflowDiagram() {
  return (
    <div className="wf-wrap">
      <div className="wf-endcap wf-source">
        <span>inputs/</span>
        <small>raw pulls · API · CSV · SQL</small>
      </div>
      <Arrow i={0} />
      <Phase {...PHASES[0]} />
      <Handoff {...HANDOFFS[0]} i={1} />
      <Phase {...PHASES[1]} />
      <Handoff {...HANDOFFS[1]} i={3} />
      <Phase {...PHASES[2]} />
      <Arrow i={5} />
      <div className="wf-endcap wf-served">
        <span>served</span>
        <small>Reports page · one HTML file</small>
      </div>
    </div>
  )
}
