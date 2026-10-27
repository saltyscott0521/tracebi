import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import {
  useConnectors, useGraph, useModels, usePipelines, useReports, useRole, useRunningRuns, useRuns, useStartPipelineRun,
} from '../api'
import { DataFrame } from './Data'
import { SetupSheet, useConnectionWrite } from './Connectors'
import ConnectionSheet from '../components/ConnectionForm'
import { DropMenu, StatusPill } from '../components/ResourceTable'
import { ActivityList } from '../components/ResourcePage'
import { useModelLabel } from '../components/Scope'
import { count } from '../format'
import { scheduleWords } from '../schedule'
import { useBuilds } from '../folders'
import { movedWords, reachWords, refreshWords } from '../words'
import {
  dataFolder, historyPath, libraryPath, lineagePath, modelsPath, reportPagePath, sourcePath, sourcesPath,
  transformPath, transformsPath, warehousePath,
} from '../nav'
import { Btn, BtnLink, Empty, ErrorDetail, SkeletonCard, useToast } from '../components/Shared'

// Data's home (/data): a status board, the console's front page. A card per
// folder, each with its count and one health pill from the graph's summary;
// Needs attention, a row per gap and per unreachable source, each with its
// action; what agents may read; what happened lately; what runs on a
// schedule. The map is one click away (View lineage, /data/lineage), where it
// earns its place: tracing a number, not orienting a newcomer.

const cap = s => (s ? s[0].toUpperCase() + s.slice(1) : s)

// One card: the folder's name, its count, one pill; the whole card opens the list.
function Card({ to, label, n, unit, status }) {
  return (
    <Link to={to} className="rcard" data-card={label}>
      <span className="rcard__k">{label}</span>
      <span className="rcard__v">{n ?? '—'}{unit && <span className="rcard__unit"> {unit}</span>}</span>
      <span className="rcard__s"><StatusPill status={status} /></span>
    </Link>
  )
}

// A row of a panel: a pill, what and why, and its one action.
function Row({ status, what, why, action, id }) {
  return (
    <li className="rrow" data-attention={id}>
      <StatusPill status={status} />
      <span className="rrow__what"><b>{what}</b>{why && <span>{why}</span>}</span>
      {action || <span />}
    </li>
  )
}

// The reports' verdicts as the library says them (the desk's re-check,
// verdict.js): how many need a look first, else how many reproduce. Before
// the desk answers, nothing is claimed.
function reportsPill(reports, verdictFor) {
  const states = reports.map(r => verdictFor(r)?.state).filter(Boolean)
  if (!states.length) return { text: 'Checking…', tone: 'none' }
  const off = states.filter(s => s === 'needs-a-look' || s === 'does-not-reproduce').length
  const ok = states.filter(s => s === 'reproduces').length
  if (off) return { text: `${off} need${off === 1 ? 's' : ''} a look`, tone: 'warn' }
  if (ok) return { text: `${ok} reproduce`, tone: ok === states.length ? 'good' : 'none' }
  return { text: `${count(states.length, 'report')} not checked`, tone: 'none' }
}

// What happened lately, newest first: the run store's rows (a run of builds
// said once, "Built X and N others"), the transforms' writes and the snapshot
// reads the certificates record. A refresh going now leads, in its live state
// (useRunningRuns: the step it is on, the reports it has rebuilt so far).
function recent(runs, nodes, going = []) {
  const items = []
  const live = going.filter(r => r.status === 'running').map(r => {
    const at = Math.max(0, r.steps.findIndex(s => s.state === 'running'))
    const step = r.steps[at]
    return {
      key: `live${r.run_id}`, status: { text: refreshWords({ running: true }).text, tone: 'none' },
      what: runs.find(x => String(x.id) === r.run_id)?.display_name || r.pipeline,
      to: r.transform ? `${transformPath(r.transform)}?tab=steps` : null,
      sub: [step && `step ${at + 1} of ${r.steps.length}: ${step.name}`,
        r.reports.length && `${count(r.reports.length, 'report')} rebuilt`].filter(Boolean).join(' · ') || null,
      at: r.started_at,
    }
  })
  const liveIds = new Set(live.map(it => it.key.slice(4)))
  runs = runs.filter(r => !liveIds.has(String(r.id)))
  const builds = []
  const flush = () => {
    if (!builds.length) return
    const [first] = builds
    items.push({
      key: `b${first.id}`, status: { text: 'Built', tone: 'ok' },
      what: first.display_name || first.target, to: reportPagePath(first.target),
      sub: builds.length > 1 ? `and ${count(builds.length - 1, 'other')}` : null, at: first.started,
    })
    builds.length = 0
  }
  for (const r of runs) {
    if (['report_build', 'background_run'].includes(r.kind) && r.status === 'succeeded') { builds.push(r); continue }
    flush()
    if (r.kind === 'pipeline_layer') continue
    const failed = ['failed', 'error', 'refused'].includes(r.status)
    const word = {
      report_build: 'Build', background_run: 'Build', pipeline_run: 'Refreshed', schedule: 'Scheduled run',
      publish: 'Published', export: 'Exported', credential: r.status === 'unset' ? 'Credential removed' : 'Credential set',
    }[r.kind] || cap(r.kind)
    items.push({
      key: `r${r.id}`, status: failed ? { text: `${word} failed`, tone: 'bad' } : { text: word, tone: 'ok' },
      what: r.display_name || r.target, to: ['report_build', 'background_run', 'schedule'].includes(r.kind) ? reportPagePath(r.target) : null,
      sub: r.actor ? `by ${r.actor}` : null, at: r.started,
    })
  }
  flush()
  for (const n of nodes) {
    const m = n.passport?.moved
    if (n.kind === 'transform' && m?.how === 'written' && m.at) {
      items.push({ key: n.id, status: { text: 'Written', tone: 'ok' }, what: n.label, to: n.open, sub: n.sub, at: m.at })
    }
    if (n.kind === 'source' && m?.how === 'snapshot' && m.at) {
      items.push({ key: n.id, status: { text: 'Snapshot read', tone: 'warn' }, what: n.label, to: n.open, sub: 'its last run read the committed snapshot', at: m.at })
    }
  }
  return [...live, ...items.sort((a, b) => String(b.at || '').localeCompare(String(a.at || '')))].slice(0, 6 + live.length)
}

function Board({ graph }) {
  const navigate = useNavigate()
  const toast = useToast()
  const admin = useRole() === 'admin'
  const write = useConnectionWrite()
  const labelOf = useModelLabel()
  const { data: connectors } = useConnectors()
  const { data: models } = useModels()
  const { data: reports } = useReports()
  const { data: pipelines } = usePipelines()
  const { data: runs } = useRuns()
  const { data: going } = useRunningRuns()
  const { mutate: start } = useStartPipelineRun()
  const { verdictFor } = useBuilds()
  const [setup, setSetup] = useState(null)
  const [adding, setAdding] = useState(false)

  const s = graph.summary || {}
  const nodes = graph.nodes
  const of = kind => nodes.filter(n => n.kind === kind)
  const unreachable = of('source').filter(n => n.passport?.reach?.connected === false)
  const files = nodes.filter(n => n.kind === 'file' && n.gap)
  const gaps = nodes.filter(n => n.gap && n.kind !== 'file')
  const tables = of('table')
  const written = tables.map(n => n.passport?.moved?.at).filter(Boolean).sort().pop()
  const measures = (models || []).reduce((n, m) => n + (m.measures || []).length, 0)
  const sourceTables = of('source_table')
  const warehouse = (connectors || []).find(c => c.warehouse)
  const scheduled = (reports || []).filter(r => r.schedule?.cron)

  const refresh = p => start({ pipeline: p.pipeline }, {
    onSuccess: res => toast(<>{res.already_running ? 'Already running.' : 'Started.'}{' '}
      {p.transform && <Link to={`${transformPath(p.transform)}?tab=steps`}>Its log</Link>}</>, 'info'),
    onError: err => toast(`Could not start: ${err.message}`, 'error'),
  })

  return (
    <>
      <header className="rhome__head">
        <div>
          <h1 className="rhome__title">{dataFolder('overview').label}</h1>
          <p className="rpage__sub">
            {warehouse?.storage?.where && <>Warehouse <code>{warehouse.storage.where}</code> · </>}
            {count(s.sources || 0, 'source')} · {count(s.transforms || 0, 'transform')} · {count(s.tables || 0, 'table')}
            {' · '}{count(s.models || 0, 'model')} · {count(s.reports || 0, 'report')}
          </p>
        </div>
        <div className="rpage__acts">
          <BtnLink size="sm" to={lineagePath()}>View lineage</BtnLink>
          {write.can && <Btn size="sm" variant="outline" onClick={() => setAdding(true)}>Add connection</Btn>}
          {admin && (pipelines || []).length > 0 && (
            <DropMenu variant="button" label="Refresh data" items={(pipelines || []).map(p => ({
              label: p.model ? `${labelOf(p.model)} (${p.pipeline})` : p.pipeline, onClick: () => refresh(p),
            }))}>Refresh data <span aria-hidden="true">▾</span></DropMenu>
          )}
        </div>
      </header>

      <div className="rcards" aria-label="What the project holds">
        <Card to={sourcesPath()} label="Sources" n={s.sources}
              status={unreachable.length ? { text: `${unreachable.length} unreachable`, tone: 'warn' } : { text: 'All connected', tone: 'ok' }} />
        <Card to={transformsPath()} label="Transforms" n={s.transforms}
              status={s.checks ? { text: `${s.checks.satisfied} of ${s.checks.of} checks passed`, tone: s.checks.satisfied === s.checks.of ? 'ok' : 'warn' } : null} />
        <Card to={warehousePath()} label="Warehouse" n={s.tables} unit="tables"
              status={written ? { text: movedWords({ how: 'written', at: written }), tone: 'ok' } : { text: 'Not written yet', tone: 'none' }} />
        <Card to={modelsPath()} label="Models" n={s.models} status={{ text: count(measures, 'measure'), tone: 'ok' }} />
        <Card to={libraryPath()} label="Reports" n={s.reports} status={reportsPill(reports || [], verdictFor)} />
      </div>

      <div className="rhome__two">
        <div>
          <section className="rhome__sec" aria-labelledby="attention">
            <h2 id="attention" className="rsec">Needs attention <span className="rsec__n">{unreachable.length + gaps.length + (files.length ? 1 : 0)}</span></h2>
            {unreachable.length + gaps.length + files.length === 0
              ? <p className="rrow__none">Nothing: every source is reachable and everything is wired on both sides.</p>
              : (
                <ul className="rrows">
                  {unreachable.map(n => {
                    const c = (connectors || []).find(x => x.name === n.name)
                    return (
                      <Row key={n.id} id={n.id} status={{ text: 'Unreachable', tone: 'warn' }}
                           what={n.label}
                           why={`${reachWords(n.passport.reach).text}${n.passport?.trust?.text === 'Read from snapshot' ? ' · the last run read the snapshot' : ''}`}
                           action={c
                             ? <Btn size="sm" variant="outline" onClick={() => setSetup(c)}>Setup</Btn>
                             : <BtnLink size="sm" to={`${sourcePath(n.name)}?tab=settings`}>Setup</BtnLink>} />
                    )
                  })}
                  {gaps.map(n => (
                    <Row key={n.id} id={n.id} status={{ text: 'Gap', tone: 'warn' }} what={n.label}
                         why={`${cap(n.gap.reason)}${n.passport?.moved?.how === 'never' ? ' · never written here' : ''}`}
                         action={n.open && <BtnLink size="sm" to={n.open}>Open</BtnLink>} />
                  ))}
                  {files.length > 0 && (
                    <Row id="files:unread" status={{ text: 'Gap', tone: 'warn' }}
                         what={files.length === 1 ? files[0].label : `${files.length} input files nobody reads`}
                         why={files.length === 1 ? cap(files[0].gap.reason) : files.map(f => f.label).join(' · ')}
                         action={<BtnLink size="sm" to={`${sourcesPath()}?filter=files`}>Open</BtnLink>} />
                  )}
                </ul>
              )}
          </section>

          <section className="rhome__sec" aria-labelledby="agents">
            <h2 id="agents" className="rsec">Agent access <Link to={`${sourcesPath()}?filter=agents`}>Manage</Link></h2>
            <ul className="rrows">
              <Row status={{ text: `${s.agents?.source_tables ?? 0} of ${sourceTables.length}`, tone: s.agents?.source_tables ? 'ok' : 'none' }}
                   what="Source tables agents may read"
                   why={s.agents?.source_tables ? 'Ticked on their sources, read through the gateway'
                     : `Nothing ticked on ${of('source').map(n => n.name).join(', ') || 'any source'}`}
                   action={<BtnLink size="sm" to={`${sourcesPath()}?filter=connections`}>Tick tables</BtnLink>} />
              <Row status={{ text: count(s.agents?.models ?? 0, 'model'), tone: 'ok' }}
                   what="Full semantic layer" why="Every model and its measures, through the gateway" />
              <Row status={{ text: `${s.agents?.reports ?? 0} published`, tone: 'ok' }}
                   what="Published reports" why="What people read, agents read too" />
            </ul>
          </section>
        </div>

        <div>
          <section className="rhome__sec" aria-labelledby="recent">
            <h2 id="recent" className="rsec">Recent activity <Link to={historyPath()}>History</Link></h2>
            <ActivityList items={recent(runs || [], nodes, going || [])} empty="Nothing has run here yet." />
          </section>

          <section className="rhome__sec" aria-labelledby="schedules">
            <h2 id="schedules" className="rsec">Schedules <Link to="/runs?kind=schedule">All</Link></h2>
            {scheduled.length === 0
              ? <p className="rrow__none">No report has a schedule. A report.json <code>"schedule"</code> block adds one.</p>
              : (
                <ActivityList items={scheduled.map(r => ({
                  key: r.name, status: { text: 'Scheduled', tone: 'ok' },
                  what: r.display_name || r.name, to: reportPagePath(r.name),
                  sub: scheduleWords(r.schedule)?.long, when: scheduleWords(r.schedule)?.short,
                }))} />
              )}
          </section>
        </div>
      </div>

      {setup && <SetupSheet c={setup} onClose={() => setSetup(null)} onSaved={() => setSetup(null)} />}
      {adding && <ConnectionSheet editing={null} onClose={() => setAdding(false)}
                                  onSaved={name => { setAdding(false); navigate(`${sourcePath(name)}?tab=tables&saved=1`) }} />}
    </>
  )
}

/** Data's home (/data). */
export default function DataHome() {
  const { data: graph, error, isLoading } = useGraph()
  return (
    <DataFrame folder="overview">
      <div className="rhome">
        {error ? <ErrorDetail error={error} />
          : isLoading || !graph ? <SkeletonCard />
          : !graph.nodes.length
            ? (
              <>
                <h1 className="rhome__title">Data</h1>
                <Empty title="Nothing here yet"
                       body="Put files under inputs/ or add a connection, write a transform that sinks tables into the warehouse, then a model over them."
                       command={'tracebi new-transform "Holdings"'} />
              </>
            )
            : <Board graph={graph} />}
      </div>
    </DataFrame>
  )
}
