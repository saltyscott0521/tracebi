import { useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import { useIsFetching, useQueryClient } from '@tanstack/react-query'

import { useMe, useStartPipelineRun } from '../api'
import TheLine, { Breakable, stamp, since, useLineFacts } from '../components/TheLine'
import Warehouse from '../components/Warehouse'
import { ModelDetail } from './Models'
import Pipelines from './Pipelines'
import Reports from './Reports'
import { pagePath } from '../nav'
import { Btn, Card, Spinner, useToast } from '../components/Shared'

// What changed on the line when a run ends: every stage may read differently.
const AFTER_A_RUN = ['pipelines', 'history', 'warehouse', 'desk', 'reports', 'models', 'model']

// The queries that read the warehouse's data. One answered while a transform is
// writing it can fail the run ("another process holds the warehouse open"), so
// a refresh starts only when the page is not in the middle of them.
const READS = ['warehouse', 'desk', 'models', 'model']

// The failing check, open: what the sink contract said, in its own words. A
// failure that was not the contract shows what the run printed.
function WhyItFailed({ transform, lastCheck, stale }) {
  const f = transform.failure
  const message = (transform.message || '').trim()
  return (
    <Card>
      <details open className="why">
        <summary>
          <span aria-hidden="true">✕</span>{' '}
          {f ? `Sink contract failed: ${f.failed} of ${f.total} ${f.total === 1 ? 'check' : 'checks'}` : 'The last run failed'}
        </summary>
        {f ? (
          <>
            <p className="why__note">
              The latest run wrote these tables, then {f.failed} of {f.total} {f.total === 1 ? 'check' : 'checks'} failed.
              {lastCheck && (stale
                ? ` They no longer match their last certificate, from ${stamp(lastCheck)}.`
                : ` Their last certificate, from ${stamp(lastCheck)}, still matches them.`)}
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
          <pre className="code-block" style={{ maxHeight: 260, overflowY: 'auto' }}>{message}</pre>
        )}
      </details>
    </Card>
  )
}

// ① the pipeline's steps, runs and code; then the tables it writes.
function TransformStage({ model, facts }) {
  const file = facts.source
  return (
    <>
      {facts.transform.failed && (
        <WhyItFailed transform={facts.transform} lastCheck={facts.lastCheck}
                     stale={facts.tables.some(t => t.contract?.status === 'stale')} />
      )}
      <Pipelines model={model} embedded />
      {file && (
        <>
          <h2 className="stage__heading">
            Produces <span className="stage__where">in {file.storage.where.split('/').pop()}</span>
          </h2>
          <Card><Warehouse connector={file} only={facts.read.size ? facts.read : undefined} /></Card>
        </>
      )}
    </>
  )
}

const STAGE_LABEL = { transform: 'Transform', model: 'Model', reports: 'Reports' }

/**
 * A model's page: how it is made, as the line (nav.js says which address is
 * which stage), and under it the stage you are looking at.
 */
export default function Overview({ model, stage }) {
  const facts = useLineFacts(model)
  const { transform } = facts
  const { data: me } = useMe()
  const toast = useToast()
  const qc = useQueryClient()
  const { mutate: start, isPending: isStarting } = useStartPipelineRun()

  // Refresh data runs the model's pipeline: the same run as "Run all" on its
  // Transform stage, in the background. The line follows it; a toast says how it ended.
  const busy = isStarting || transform.running
  const reading = useIsFetching({ predicate: q => READS.includes(q.queryKey[0]) }) > 0
  const refresh = () => start({ pipeline: transform.pipeline.pipeline }, {
    onSuccess: res => { if (res.already_running) toast('Already refreshing.', 'info') },
    onError: err => toast(`Could not start: ${err.message}`, 'error'),
  })
  const was = useRef(false)
  useEffect(() => {
    if (was.current && !transform.running) {
      AFTER_A_RUN.forEach(key => qc.invalidateQueries({ queryKey: [key] }))
      toast(transform.failed ? 'The refresh failed. See why on the Transform stage.' : `Refreshed ${model}.`,
        transform.failed ? 'error' : 'info')
    }
    was.current = transform.running
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [transform.running])

  const refreshed = transform.goodAt && `Last refreshed ${stamp(transform.goodAt)}${transform.failed ? ' (the latest run failed)' : ''}.`

  return (
    <div className="overview">
      <header className="overview__head">
        <div className="overview__id">
          <div className="overview__cap">Overview</div>
          <h1 className="overview__title"><Breakable name={model} /></h1>
          <p className="overview__sub">
            {facts.description && <>{facts.description} </>}
            {refreshed && <span className="overview__muted">{refreshed} </span>}
            <Link to={pagePath('runs', model)}>History</Link>
          </p>
        </div>
        {me?.role === 'admin' && transform.pipeline && (
          <Btn onClick={refresh} disabled={busy || reading}>
            {busy ? <><Spinner size={12} /> Refreshing…</> : (
              <>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2"
                     strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M20 11a8 8 0 1 0-2.3 5.7M20 4v7h-7" />
                </svg>
                Refresh data
              </>
            )}
          </Btn>
        )}
      </header>

      {transform.failed && (
        <p role="status" className="overview__alert">
          <strong>
            <span aria-hidden="true">✕</span> <span className="overview__name">{transform.name}</span> failed {since(transform.lastAt)}
            {transform.failure ? ' at its sink contract' : ''}.
          </strong>
          {transform.failure && facts.builtCount > 0 && <span>The built reports were made from the tables it replaced.</span>}
          {stage !== 'transform' && <Link to={pagePath('transform', model)}>See why</Link>}
        </p>
      )}

      <TheLine model={model} stage={stage} line={facts.line} />

      <section className="stage" aria-label={STAGE_LABEL[stage]}>
        {stage === 'reports' && <Reports model={model} embedded />}
        {stage === 'model' && <ModelDetail name={model} />}
        {stage === 'transform' && <TransformStage model={model} facts={facts} />}
      </section>
    </div>
  )
}
