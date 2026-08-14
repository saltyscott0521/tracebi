// The three-phase workflow, as a flowchart. Each phase is a folder with its
// own cadence; the pills between them are the freeze points — the materialized
// artifact that hands one phase to the next. Token-only colors so it holds in
// both themes.

const PHASES = [
  {
    n: '1',
    tag: 'transforms/',
    title: 'Manipulate',
    color: '#0891b2',
    body: 'Pull the queries you need and run real Python — window functions, algorithms, cleaning — then sink the result.',
    cadence: 'runs rarely · code is unconstrained',
  },
  {
    n: '2',
    tag: 'models/',
    title: 'Model',
    color: '#7c3aed',
    body: 'Declare a star schema over the warehouse — grain, keys, measures. A contract a reviewer reads in minutes, without opening the pandas.',
    cadence: 'changes deliberately',
  },
  {
    n: '3',
    tag: 'dashboards/',
    title: 'Dashboard',
    color: '#db2777',
    body: 'Point a spec at the model — KPI cards, charts, tables. Every figure a live query; edit and re-render in milliseconds.',
    cadence: 'iterate constantly',
  },
]

// what freezes between the phases
const HANDOFFS = [
  { label: 'warehouse.duckdb', sub: 'materialized tables' },
  { label: 'the model', sub: 'the semantic contract' },
]

function Arrow() {
  return (
    <svg className="wf-arrow" viewBox="0 0 24 24" width="22" height="22" fill="none"
      stroke="var(--muted)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M4 12h15" />
      <path d="M13 6l7 6-7 6" />
    </svg>
  )
}

function Handoff({ label, sub }) {
  return (
    <div className="wf-handoff">
      <Arrow />
      <div className="wf-freeze" title="frozen between phases">
        <div className="wf-freeze-label">
          <svg viewBox="0 0 20 20" width="12" height="12" fill="currentColor" aria-hidden="true">
            <path fillRule="evenodd" d="M10 1a1 1 0 011 1v2.02l1.3-.75a1 1 0 111 1.73l-1.3.76 1.74 1V6a1 1 0 112 0v2.29l1.75 1.01a1 1 0 010 1.73L16.74 12H18a1 1 0 110 2h-2.02l.76 1.3a1 1 0 11-1.73 1l-.76-1.3-1 1.74H14a1 1 0 110 2h-2.29l-1.01 1.75a1 1 0 01-1.73 0L7.96 20H6a1 1 0 110-2h.02l-.75-1.3a1 1 0 111.73-1l.75 1.3 1-1.74V16a1 1 0 11-2 0v-.02l-1.3.76a1 1 0 11-1-1.73l1.3-.76L4.01 12H4a1 1 0 110-2h.02l-.76-1.3a1 1 0 111.73-1l.76 1.3 1-1.74V6a1 1 0 112 0v.02l1.3-.76a1 1 0 111 1.74L11.06 8h.01L10 6.26 8.94 8h.01L7.7 6.72 10 5.02V4a1 1 0 011-1z" clipRule="evenodd" />
          </svg>
          {label}
        </div>
        <div className="wf-freeze-sub">{sub}</div>
      </div>
      <Arrow />
    </div>
  )
}

function Phase({ n, tag, title, color, body, cadence }) {
  return (
    <div className="wf-phase card-hover" style={{ '--wf': color }}>
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
        <span>raw sources</span>
        <small>API pulls · CSV · SQL</small>
      </div>
      <Arrow />
      <Phase {...PHASES[0]} />
      <Handoff {...HANDOFFS[0]} />
      <Phase {...PHASES[1]} />
      <Handoff {...HANDOFFS[1]} />
      <Phase {...PHASES[2]} />
      <Arrow />
      <div className="wf-endcap wf-served">
        <span>served</span>
        <small>Reports page · HTML · Excel</small>
      </div>
    </div>
  )
}
