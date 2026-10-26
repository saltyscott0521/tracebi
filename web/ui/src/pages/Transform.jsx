import { useEffect, useRef } from 'react'
import { useParams } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'

import { usePipelines, useTransforms } from '../api'
import { useLineFacts } from '../components/TheLine'
import Warehouse from '../components/Warehouse'
import { stamp } from '../when'
import Pipelines from './Pipelines'
import { DataFrame } from './Data'
import { pipelineModels, transformsPath } from '../nav'
import { Card, Empty, SkeletonCard } from '../components/Shared'

// A stand-in for one transform's page (/data/transforms/<name>), which its
// own package replaces: what the model page's Transform tab showed, moved
// here so the address works and Refresh data stays one click away.

// The failing check, open: what the checks said when the tables were written,
// in their own words. A failure that was not a check shows what the run printed.
function WhyItFailed({ transform, lastCheck, stale }) {
  const f = transform.failure
  const message = (transform.message || '').trim()
  return (
    <Card>
      <details open className="why">
        <summary>
          <span aria-hidden="true">✕</span>{' '}
          {f ? `Checks failed when the tables were written: ${f.failed} of ${f.total}` : 'The last run failed'}
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
          <pre className="code-block" style={{ maxHeight: 260, overflowY: 'auto' }}>{message}</pre>
        )}
      </details>
    </Card>
  )
}

const AFTER_A_RUN = ['pipelines', 'history', 'warehouse', 'warehouses', 'desk', 'reports', 'models', 'model']

// When it last ran, why it failed if it did, the pipeline's steps, runs and
// code (Refresh data is its one primary action), then the tables it writes.
function Refreshed({ model }) {
  const facts = useLineFacts(model)
  const file = facts.source
  const { transform } = facts
  const qc = useQueryClient()
  // A run that ends changes what this page says: read it all again.
  const was = useRef(false)
  useEffect(() => {
    if (was.current && !transform.running) AFTER_A_RUN.forEach(key => qc.invalidateQueries({ queryKey: [key] }))
    was.current = transform.running
  }, [transform.running]) // eslint-disable-line react-hooks/exhaustive-deps
  const refreshed = transform.goodAt && `Last refreshed ${stamp(transform.goodAt)}${transform.failed ? ' (the latest run failed)' : ''}.`
  return (
    <>
      {(facts.description || refreshed) && (
        <div className="dtab__head">
          <p>
            {facts.description && <>{facts.description} </>}
            {refreshed && <span className="overview__muted">{refreshed}</span>}
          </p>
        </div>
      )}
      {transform.failed && (
        <WhyItFailed transform={transform} lastCheck={facts.lastCheck}
                     stale={facts.tables.some(t => t.contract?.status === 'stale')} />
      )}
      <Pipelines model={model} />
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

export default function Transform() {
  const { name } = useParams()
  const { data: transforms, isLoading } = useTransforms()
  const { data: pipelines } = usePipelines()
  const t = (transforms || []).find(x => x.name === name)
  const p = (pipelines || []).find(x => x.transform === name)
  const model = p && pipelineModels(p)[0]
  return (
    <DataFrame trail={[[transformsPath(), 'Transforms']]} here={name} code>
      <header className="tpage__head"><h1 className="tpage__name">{name}</h1></header>
      {isLoading ? <SkeletonCard />
        : !t ? <Empty title="No transform by that name" body="It may have been renamed or removed from transforms/." />
          : model ? <Refreshed model={model} />
            : (
              <Empty title="No pipeline runs this transform" body="Run it from the project:"
                     command={`tracebi run-transform ${name}`} />
            )}
    </DataFrame>
  )
}
