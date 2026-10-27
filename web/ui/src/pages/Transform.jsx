import { useEffect, useRef, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'

import {
  useConnectors, useDesk, useGraph, useInputs, useMe, usePipelines, useReports, useRuns, useSource, useTransforms,
  useWarehouses,
} from '../api'
import { useLineFacts } from '../components/TheLine'
import { useModelLabel } from '../components/Scope'
import { CodeFiles } from '../components/CodeView'
import { StateChip } from '../components/Passport'
import ResourcePage, { ActivityList, Details, Links } from '../components/ResourcePage'
import { ContractLine, ReadInput, TableList, groupContract } from '../components/Warehouse'
import { PipelineDetail } from './Pipelines'
import { FORM_LABEL, movedWords, refreshWords, statusWords } from '../words'
import { humanise } from '../ask'
import { stamp } from '../when'
import { count } from '../format'
import * as nav from '../nav'
import { DataFrame } from './Data'
import {
  Btn, BtnLink, Card, Chip, Empty, ErrorDetail, SkeletonCard, Spinner, useToast,
} from '../components/Shared'

const { modelPath, sourceTablePath, transformPath, transformsPath, warehouseTablePath } = nav

// One transform file's page (/data/transforms/<name>), whether or not a
// pipeline runs it, in the console's shape: Overview (its facts as a grid,
// when it last wrote and whether that failed, what its run read and the
// tables it wrote), Steps (the pipeline that runs it), Code (its code beside
// its checks), Lineage, Activity (its pipeline's runs), Agents, Settings.
// Refresh data is top right; its run unfolds on Steps.

// What a run's end changes: every page that says when the data was refreshed.
const AFTER_A_RUN = ['pipelines', 'history', 'warehouse', 'warehouses', 'transforms', 'desk', 'reports', 'models', 'model']

// How the run read a source, as the certificate records it.
const METHOD_TITLE = {
  scanner: 'Read in place through DuckDB’s scanner',
  arrow: 'Read as Arrow',
  pandas: 'Read through the connector',
}

// The failing run, open: the checks that failed in their own words, or what
// the run printed when it was not a check.
function WhyItFailed({ transform, lastCheck, stale }) {
  const f = transform.failure
  return (
    <details open className="why">
      <summary>
        {f ? `Checks failed when the tables were written: ${f.failed} of ${f.total}` : 'What the run said'}
      </summary>
      {f ? (
        <>
          <p className="why__note">
            The latest run wrote these tables, then {f.failed} of {f.total} {f.total === 1 ? 'check' : 'checks'} failed.
            {lastCheck && (stale
              ? ` They no longer match the checks that last passed, on ${stamp(lastCheck)}.`
              : ` The checks that last passed, on ${stamp(lastCheck)}, still describe them.`)}
          </p>
          <ul className="why__checks">
            {f.checks.map(c => (
              <li key={c.check}>
                <code>{c.check}</code>
                <span className="flag flag--bad"><span aria-hidden="true">✕</span> observed {c.observed}</span>
              </li>
            ))}
          </ul>
        </>
      ) : (
        <pre className="code-block tfpage__error">{(transform.message || '').trim()}</pre>
      )}
    </details>
  )
}

// The state line: the refresh in the app's words (words.js refreshWords),
// and when the last run failed, why.
function StateLine({ phrase, transform, lastCheck, stale }) {
  if (phrase.kind !== 'failed') return <p className="tfpage__state">{phrase.text}.</p>
  return (
    <Card>
      <p role="status" className="overview__alert tfpage__alert">
        <strong><span aria-hidden="true">✕</span> {phrase.text}.</strong>
      </p>
      <WhyItFailed transform={transform} lastCheck={lastCheck} stale={stale} />
    </Card>
  )
}

// A transform a pipeline runs: what the model's line computes about its
// transform step, and a toast here when a run ends.
function RunState({ name, model, written, tables }) {
  const { transform } = useLineFacts(model)
  const toast = useToast()
  const qc = useQueryClient()
  const was = useRef(false)
  useEffect(() => {
    if (was.current && !transform.running) {
      AFTER_A_RUN.forEach(key => qc.invalidateQueries({ queryKey: [key] }))
      toast(transform.failed ? `${name} failed. This page says why.` : `Refreshed ${name}.`,
        transform.failed ? 'error' : 'info')
    }
    was.current = transform.running
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [transform.running])
  if (!transform.known) return null
  const lastCheck = tables.map(t => t.contract?.checked_at).filter(Boolean).sort().pop()
  return (
    <StateLine phrase={refreshWords({
                 running: transform.running, failedAt: transform.failed ? transform.lastAt : null,
                 ranAt: transform.lastAt, writtenAt: written,
               })}
               transform={transform} lastCheck={lastCheck}
               stale={tables.some(t => t.contract?.status === 'stale')} />
  )
}

function Section({ id, title, children }) {
  return (
    <section aria-labelledby={id} className="tfpage__section">
      {title && <h2 id={id} className="stage__heading">{title}</h2>}
      {children}
    </section>
  )
}

// The pipelines that run the transform, each with its Refresh data, steps,
// code and latest run; none says how to run the file by hand. A step with no
// run here says what was written (*written*, the certificate's time) or built
// (the newest build of a report on the pipeline's models) outside the app.
function Run({ name, pipelines, written, start }) {
  const labelOf = useModelLabel()
  const { data: desk } = useDesk()
  const { data: reports } = useReports()
  const builtFor = p => {
    const models = nav.pipelineModels(p)
    const mine = new Set((reports || []).filter(r => nav.reportModels(r).some(m => models.includes(m))).map(r => r.name))
    return (desk?.builds || []).filter(b => mine.has(b.report) && b.built_at).map(b => b.built_at).sort().pop()
  }
  return (
    <Section id="tf-run">
      {pipelines.length === 0 ? (
        <Card>
          <Empty body="No pipeline runs this transform. Run it with:"
                 command={`tracebi run-transform ${name}`} />
        </Card>
      ) : pipelines.map(p => (
        <div key={p.pipeline} className="tfpage__pipeline">
          {/* A pipeline has no label of its own: the model's is its name when it is the model's. */}
          <PipelineDetail pipeline={p.pipeline} layers={p.layers || []} primary
                          label={p.model ? labelOf(p.model) : humanise(p.pipeline)}
                          written={written} built={builtFor(p)} start={p === pipelines[0] ? start : undefined} />
        </div>
      ))}
    </Section>
  )
}

// The transform and its checks, side by side when the column is wide.
function Code({ name, note }) {
  const { data, isLoading, error } = useSource('transforms', name)
  const files = data?.files || []
  return (
    <Section id="tf-code">
      <Card>
        {note && <p className="tfpage__note">{note}</p>}
        {isLoading ? <div className="codeview__hint"><Spinner /> Loading code…</div>
          : error ? <ErrorDetail error={error} />
            : !files.length ? <div className="codeview__hint">{data?.hint || 'No code to show.'}</div>
              : (
                <div className="tfpage__codewrap">
                  <div className={`tfpage__code${files.length > 1 ? ' tfpage__code--two' : ''}`}>
                    {files.map(f => <div key={f.path}><CodeFiles files={[f]} /></div>)}
                  </div>
                </div>
              )}
      </Card>
    </Section>
  )
}

// What the run read: each outside table as the certificate recorded it (how,
// or the snapshot that stood in); with no recorded run, the tables the file
// names. Then the input files it names.
function Reads({ name, writers, files }) {
  const { data: connectors } = useConnectors()
  const recorded = writers.flatMap(wr => wr.read)
  const named = recorded.length ? [] : (connectors || []).flatMap(c =>
    ((c.read_by?.transforms || []).find(t => t.name === name)?.tables || []).map(table => ({ connection: c.name, table })))
  const none = !recorded.length && !named.length && !files.length
  return (
    <Section id="tf-reads" title="Reads">
      <Card>
        {none ? <p className="wb-meta">The file names no connection and no input file.</p> : (
          <ul className="tfpage__reads">
            {recorded.map(src => (
              <li key={src.ref}>
                <ReadInput src={src} />
                {src.method && <> <Chip tone="none" title={METHOD_TITLE[src.method]}>{src.method}</Chip></>}
              </li>
            ))}
            {named.map(s => (
              <li key={`${s.connection}.${s.table}`}>
                <Link to={sourceTablePath(s.connection, s.table)}><code>{s.connection}.{s.table}</code></Link>
                <span className="wb-meta"> · named in the file; no recorded run read it</span>
              </li>
            ))}
            {files.map(f => (
              <li key={f.path}>
                {f.table
                  ? <Link to={sourceTablePath('inputs', f.path.replace(/^inputs\//, ''))}><code>{f.path}</code></Link>
                  : <code>{f.path}</code>}
                <span className="wb-meta"> · input file</span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </Section>
  )
}

// The tables and views the transform wrote, per warehouse, under what its
// checks said; the models that read them are named once, in the sub line.
function Produces({ groups }) {
  return (
    <Section id="tf-produces" title="Produces">
      <Card>
        {groups.length === 0
          ? <p className="wb-meta">No certificate names a table this transform wrote: it has not run here.</p>
          : groups.map(({ w, wr, tables }) => (
            <div key={`${w.name}:${wr.contract}`} className="tfpage__group" data-writer={wr.transform || wr.contract}>
              {/* The note leads the Code section; it is said once. */}
              <ContractLine contract={{ ...groupContract(wr, tables), note: null }} subject="A table it wrote" />
              <TableList warehouse={w.name} tables={tables} readBy={false} />
            </div>
          ))}
      </Card>
    </Section>
  )
}

// Agents and a transform: never read, only proposed.
function AgentsTab() {
  return (
    <div className="rsection">
      <p className="rsection__lede">
        <StateChip state={{ state: 'none', text: 'May propose a change' }} />{' '}
        An agent never reads a transform through the gateway and never writes the warehouse. It may propose a
        change (propose_transform): a code request an admin reviews, approves and runs once.
      </p>
      <BtnLink size="sm" to="/review">Review</BtnLink>
    </div>
  )
}

export default function Transform() {
  const { name } = useParams()
  const [, setParams] = useSearchParams()
  const { data: listing, isLoading, error } = useTransforms()
  const { data: pipelines } = usePipelines()
  const { data: warehouses } = useWarehouses()
  const { data: inputs } = useInputs()
  const { data: graph } = useGraph()
  const { data: me } = useMe()
  const admin = !!me && (!me.role || me.role === 'admin')
  const labelOf = useModelLabel()
  const [start, setStart] = useState(0)
  const t = (listing || []).find(x => x.name === name)
  const { data: runs } = useRuns('pipeline_run', t?.pipelines?.[0] || '__none__')

  const frame = children => <DataFrame trail={[[transformsPath(), 'Transforms']]} here={name} code>{children}</DataFrame>
  if (isLoading) return frame(<SkeletonCard />)
  if (error) return frame(<ErrorDetail error={error} />)
  if (!t) {
    return frame(
      <Empty title="No such transform"
             body={<>There is no <code>{name}</code> in transforms/. <Link to={transformsPath()}>Every transform</Link></>} />
    )
  }

  const node = (graph?.nodes || []).find(n => n.id === `transform:${name}`)
  const p = node?.passport
  const ran = (pipelines || []).filter(x => t.pipelines.includes(x.pipeline))
  const model = ran[0] && nav.pipelineModels(ran[0])[0]
  // What the certificate says it wrote, warehouse by warehouse.
  const groups = (warehouses?.warehouses || []).flatMap(w => (w.writers || [])
    .filter(wr => wr.transform === name)
    .map(wr => ({ w, wr, tables: w.tables.filter(x => wr.tables.includes(x.name)) })))
  const writers = groups.map(g => g.wr)
  const tables = groups.flatMap(g => g.tables)
  const files = (inputs?.files || []).filter(f => (f.read_by || []).includes(name))
  const feeds = <Links items={t.models.map(m => ({ key: m, to: modelPath(m), label: labelOf(m) }))} none="No model" />
  const refresh = () => { setParams({ tab: 'steps' }); setStart(n => n + 1) }
  // When it last wrote and whether that failed: Overview's and Steps' first line.
  const state = model
    ? <RunState name={name} model={model} written={t.written_at} tables={tables} />
    : (pipelines || !t.pipelines.length) && <StateLine phrase={refreshWords({ pipeline: false, writtenAt: t.written_at })} />

  return (
    <ResourcePage
      trail={[[transformsPath(), 'Transforms']]} here={name} code
      title={name} type={FORM_LABEL[t.form] || t.form} status={node ? statusWords(node) : null}
      sub={<>{t.tables.length ? `Writes ${count(t.tables.length, 'table')}` : 'Has written nothing here'} · feeds {t.models.length ? t.models.map(labelOf).join(', ') : 'no model'}{t.pipelines.length ? ` · run by ${t.pipelines.join(', ')}` : ' · no pipeline runs it'}</>}
      node={`transform:${name}`}
      actions={<>
        {admin && ran.length > 0 && <Btn size="sm" onClick={refresh}>Refresh data</Btn>}
        <Btn size="sm" variant="outline" onClick={() => setParams({ tab: 'code' })}>View code</Btn>
      </>}
      tabs={[
        { key: 'overview', label: 'Overview', render: () => (
          <div className="tfpage">
            <Details items={[
              ['Form', FORM_LABEL[t.form] || t.form],
              ['From', p?.origin ? <code>{p.origin}</code> : null],
              ['Writes', <Links items={t.tables.map(x => ({ key: x, to: warehouseTablePath(x), label: x, code: true }))} none="Nothing recorded" />],
              ['Feeds', feeds],
              ['Last moved', p ? movedWords(p.moved, 'transform') : refreshWords({ pipeline: t.pipelines.length > 0, writtenAt: t.written_at }).text],
              ['Trust', <StateChip state={p?.trust} />],
              ['Agents', <StateChip state={p?.agents || { state: 'none', text: 'May propose a change' }} />],
              ['Run by', t.pipelines.length ? <code>{t.pipelines.join(', ')}</code> : <Chip tone="warn">No pipeline runs it</Chip>],
              ['Checks in', t.contract_file ? <code>{t.contract_file}</code> : 'No contract'],
            ]} />
            {state}
            <Reads name={name} writers={writers} files={files} />
            <Produces groups={groups} />
          </div>
        ) },
        { key: 'steps', label: 'Steps', render: () => (
          <div className="tfpage">
            {state}
            <Run name={name} pipelines={ran} written={t.written_at} start={admin && ran.length ? start : undefined} />
          </div>
        ) },
        { key: 'code', label: 'Code', render: () => <Code name={name} note={t.note} /> },
        t.pipelines.length > 0 && { key: 'activity', label: 'Activity', render: () => (
          <ActivityList empty="No run of its pipeline is recorded here." items={(runs || []).slice(0, 20).map(r => ({
            key: r.id,
            status: { text: r.status === 'succeeded' ? 'Refreshed' : r.status === 'running' ? 'Running' : 'Refresh failed', tone: r.status === 'failed' ? 'bad' : r.status === 'succeeded' ? 'ok' : 'none' },
            what: r.target, to: `${transformPath(name)}?tab=steps`, sub: r.actor ? `by ${r.actor}` : null, at: r.started,
          }))} />
        ) },
        { key: 'agents', label: 'Agents', render: () => <AgentsTab /> },
        { key: 'settings', label: 'Settings', render: () => (
          <Details items={[
            ['Declared in', <code>{t.file}</code>],
            ['Checks in', t.contract_file ? <code>{t.contract_file}</code> : 'No contract'],
            ['Run by', t.pipelines.length ? <code>{t.pipelines.join(', ')}</code> : <>Nothing: <code>tracebi run-transform {name}</code></>],
          ]} />
        ) },
      ]}
    />
  )
}
