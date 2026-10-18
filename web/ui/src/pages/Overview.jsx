import { useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'

import { useAppStatus, useModel } from '../api'
import TheLine, { stamp, since, useLineFacts } from '../components/TheLine'
import Warehouse from '../components/Warehouse'
import EditAsDraft from '../components/EditAsDraft'
import { ModelDetail } from './Models'
import Pipelines from './Pipelines'
import Connectors from './Connectors'
import Runs from './Runs'
import { ProjectFeedFold } from '../components/Workbench'
import { dataPath } from '../nav'
import { Card, useToast } from '../components/Shared'

// What changed on the line when a run ends: every station may read differently.
const AFTER_A_RUN = ['pipelines', 'history', 'warehouse', 'desk', 'reports', 'models', 'model']

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

// The Transform tab: when it last ran, why it failed if it did, the pipeline's
// steps, runs and code (its Refresh data is this page's one primary action),
// then the tables it writes.
function TransformTab({ model, facts }) {
  const file = facts.source
  const { transform } = facts
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

const TABS = [['model', 'Model'], ['transform', 'Transform'], ['sources', 'Sources'], ['runs', 'Runs']]

/**
 * A model's Data page: its name and where it is defined, the line as the
 * header (nav.js says which address is which tab), then the tab you are on.
 */
function ModelPage({ model, tab }) {
  const facts = useLineFacts(model)
  const { transform } = facts
  const { data: detail } = useModel(model)
  const { data: appStatus } = useAppStatus()
  const dev = !!appStatus?.build_mode
  const toast = useToast()
  const qc = useQueryClient()
  const label = detail?.label || model

  // A refresh (Refresh data on the Transform tab, or a run started elsewhere)
  // changes what every station says; a toast says how it ended.
  const was = useRef(false)
  useEffect(() => {
    if (was.current && !transform.running) {
      AFTER_A_RUN.forEach(key => qc.invalidateQueries({ queryKey: [key] }))
      toast(transform.failed ? 'The refresh failed. The Transform tab says why.' : `Refreshed ${label}.`,
        transform.failed ? 'error' : 'info')
    }
    was.current = transform.running
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [transform.running])

  const reads = (detail?.connector_details || []).map(c => c.storage?.where).filter(Boolean)

  return (
    <div className="overview">
      <header className="overview__head">
        <div className="overview__cap"><Link to="/data">Data</Link></div>
        <h1 className="overview__title">{label} {label !== model && <span className="overview__id">{model}</span>}</h1>
        {detail && (
          <p className="overview__sub">
            {detail.source_file && <>Defined in <code>{detail.source_file}</code></>}
            {detail.source_file && reads.length > 0 && ' · '}
            {reads.length > 0 && <>reads {reads.map((w, i) => <span key={w}>{i > 0 && ', '}<code>{w}</code></span>)}</>}
          </p>
        )}
      </header>

      {transform.failed && (
        <p role="status" className="overview__alert">
          <strong>
            <span aria-hidden="true">✕</span> <span className="overview__name">{transform.name}</span> failed
            {transform.failure ? ' its checks' : ''} {since(transform.lastAt)}.
          </strong>
          {transform.failure && facts.builtCount > 0 && <span>The built reports were made from the tables it replaced.</span>}
          {tab !== 'transform' && <Link to={dataPath(model, 'transform')}>See why</Link>}
        </p>
      )}

      <TheLine model={model} tab={tab} line={facts.line} />

      <nav aria-label={`${label}: what to show`}>
        <ul className="dtabs">
          {TABS.map(([key, text]) => (
            <li key={key}>
              <Link to={dataPath(model, key === 'model' ? '' : key)} aria-current={tab === key ? 'page' : undefined}>{text}</Link>
            </li>
          ))}
        </ul>
      </nav>

      <section className="stage" key={tab} aria-label={TABS.find(([key]) => key === tab)[1]}>
        {tab === 'model' && (
          <ModelDetail name={model} action={<EditAsDraft kind="models" path={model} bare />} />
        )}
        {tab === 'transform' && <TransformTab model={model} facts={facts} />}
        {tab === 'sources' && <Connectors model={model} />}
        {tab === 'runs' && <Runs model={model} />}
      </section>
      {/* In dev mode (`tracebi dev`) what the agent shows you while it works on
          the transform and the model, and your notes to it, are here, folded,
          even before a report exists. */}
      {dev && <ProjectFeedFold />}
    </div>
  )
}

export default ModelPage
