import { Fragment, useEffect, useRef } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'

import { useConnectors, useInputs, usePipelines, useSource, useTransforms, useWarehouses } from '../api'
import { useLineFacts } from '../components/TheLine'
import { useModelLabel } from '../components/Scope'
import { CodeFiles } from '../components/CodeView'
import { ContractLine, ReadInput, TableList, groupContract } from '../components/Warehouse'
import { PipelineDetail } from './Pipelines'
import { FORM_LABEL } from '../chain'
import { humanise } from '../ask'
import { ago, stamp } from '../when'
import * as nav from '../nav'
import { DataFrame } from './Data'
import {
  Badge, Card, Chip, Empty, ErrorDetail, SkeletonCard, Spinner, useToast,
} from '../components/Shared'

const { modelPath, sourceTablePath, transformsPath } = nav

// One transform file's page (/data/transforms/<name>), whether or not a
// pipeline runs it: when it last wrote and whether that failed, the pipeline
// that runs it (Refresh data), its code beside its checks, what its run read
// and the tables it wrote. Data's frame gives the breadcrumb; the page gives
// its own h1.

// What a run's end changes: every page that says when the data was refreshed.
const AFTER_A_RUN = ['pipelines', 'history', 'warehouse', 'warehouses', 'transforms', 'desk', 'reports', 'models', 'model']

// How the run read a source, as the certificate records it.
const METHOD_TITLE = {
  scanner: 'Read in place through DuckDB’s scanner',
  arrow: 'Read as Arrow',
  pandas: 'Read through the connector',
}

// The refresh phrase: what the pipeline's runs say, else what the sink's
// certificate says (a run outside the app leaves no run here).
function refreshPhrase(t, written) {
  if (t?.running) return { text: 'Running now' }
  if (t?.failed) return { bad: true, text: `Refresh failed ${ago(t.lastAt)}` }
  if (t?.lastAt) return { text: `Refreshed ${ago(t.lastAt)}` }
  if (written) return { text: `Written ${ago(written)} · outside the app` }
  return { text: 'Not refreshed yet' }
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

// The state line: the refresh phrase, and when the last run failed, why.
function StateLine({ phrase, transform, lastCheck, stale }) {
  if (!phrase.bad) return <p className="tfpage__state">{phrase.text}.</p>
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
    <StateLine phrase={refreshPhrase(transform, written)} transform={transform} lastCheck={lastCheck}
               stale={tables.some(t => t.contract?.status === 'stale')} />
  )
}

function Section({ id, title, children }) {
  return (
    <section aria-labelledby={id} className="tfpage__section">
      <h2 id={id} className="stage__heading">{title}</h2>
      {children}
    </section>
  )
}

// The pipelines that run the transform, each with its Refresh data, steps,
// code and latest run; none says how to run the file by hand.
function Run({ name, pipelines }) {
  const labelOf = useModelLabel()
  return (
    <Section id="tf-run" title="Run">
      {pipelines.length === 0 ? (
        <Card>
          <Empty body="No pipeline runs this transform. Run it with:"
                 command={`tracebi run-transform ${name}`} />
        </Card>
      ) : pipelines.map(p => (
        <div key={p.pipeline} className="tfpage__pipeline">
          {/* A pipeline has no label of its own: the model's is its name when it is the model's. */}
          <PipelineDetail pipeline={p.pipeline} layers={p.layers || []} primary
                          label={p.model ? labelOf(p.model) : humanise(p.pipeline)} />
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
    <Section id="tf-code" title="Code">
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

export default function Transform() {
  const { name } = useParams()
  const { data: listing, isLoading, error } = useTransforms()
  const { data: pipelines } = usePipelines()
  const { data: warehouses } = useWarehouses()
  const { data: inputs } = useInputs()
  const labelOf = useModelLabel()

  const frame = children => <DataFrame trail={[[transformsPath(), 'Transforms']]} here={name} code>{children}</DataFrame>
  if (isLoading) return frame(<SkeletonCard />)
  if (error) return frame(<ErrorDetail error={error} />)
  const t = (listing || []).find(x => x.name === name)
  if (!t) {
    return frame(
      <Empty title="No such transform"
             body={<>There is no <code>{name}</code> in transforms/. <Link to={transformsPath()}>Every transform</Link></>} />
    )
  }

  const runs = (pipelines || []).filter(p => t.pipelines.includes(p.pipeline))
  const model = runs[0] && nav.pipelineModels(runs[0])[0]
  // What the certificate says it wrote, warehouse by warehouse.
  const groups = (warehouses?.warehouses || []).flatMap(w => (w.writers || [])
    .filter(wr => wr.transform === name)
    .map(wr => ({ w, wr, tables: w.tables.filter(x => wr.tables.includes(x.name)) })))
  const writers = groups.map(g => g.wr)
  const tables = groups.flatMap(g => g.tables)
  const files = (inputs?.files || []).filter(f => (f.read_by || []).includes(name))

  return frame(
    <div className="tfpage">
      <header className="overview__head">
        <h1 className="overview__title">
          <span className="tfpage__name">{name}</span> <Badge>{FORM_LABEL[t.form] || t.form}</Badge>
        </h1>
        <p className="overview__sub">
          {t.models.length
            ? <>Feeds {t.models.map((m, i) => <Fragment key={m}>{i > 0 && ', '}<Link to={modelPath(m)}>{labelOf(m)}</Link></Fragment>)}</>
            : 'Feeds no model'}
          {' · '}last wrote {t.written_at ? stamp(t.written_at) : 'never, here'}
        </p>
      </header>

      {model
        ? <RunState name={name} model={model} written={t.written_at} tables={tables} />
        : (pipelines || !t.pipelines.length) && <StateLine phrase={refreshPhrase(null, t.written_at)} />}

      <Run name={name} pipelines={runs} />
      <Code name={name} note={t.note} />
      <Reads name={name} writers={writers} files={files} />
      <Produces groups={groups} />
    </div>
  )
}
