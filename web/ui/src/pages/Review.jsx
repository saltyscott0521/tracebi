import { useEffect, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'

import { useCodeRequests, useDesk, useDrafts, usePipelines, usePublishRequests, useReports, useRuns } from '../api'
import { attentionItems, when } from '../components/Attention'
import { PageHeader, useReportModels } from '../components/Scope'
import { Badge, Spinner, Verdict } from '../components/Shared'
import { historyPath } from '../nav'
import DraftList, { CodeReview, RequestDecision } from './Drafts'
import { VerifyZone } from './Verify'

// Review: what waits on a person, in the order they act on it. Needs
// attention first (failed runs, builds that need a look, requests waiting on
// a decision), then Drafts, then Verify a file as a quiet entry at the bottom.
// History (/runs) and the full Verify page (/verify) keep their own pages.

export default function Review() {
  const { data: desk, isLoading: deskLoading } = useDesk()
  const { data: pipelines } = usePipelines()
  const { data: reports } = useReports()
  const { data: runs } = useRuns('', '')
  const { data: requests } = usePublishRequests()
  const { data: codeRequests } = useCodeRequests()
  const { data: drafts } = useDrafts()
  const modelsOf = useReportModels()
  const items = attentionItems(desk, pipelines, modelsOf, reports || [], { runs, requests, codeRequests })

  // /drafts lands here as /review#drafts: scroll to the section once it is drawn.
  const { hash } = useLocation()
  useEffect(() => {
    if (hash) document.getElementById(hash.slice(1))?.scrollIntoView()
  }, [hash, drafts])

  return (
    <div className="fade-in review">
      <PageHeader pageKey="review" />

      <section aria-labelledby="attention-h" className="review__section">
        <div className="review__head">
          <h2 id="attention-h">Needs attention {items.length > 0 && <span className="review__count">{items.length}</span>}</h2>
          <Link to={historyPath()}>All history →</Link>
        </div>
        {items.length > 0 ? <Attention items={items} /> : deskLoading ? (
          <p className="review__quiet"><Spinner size={13} /> Checking the builds…</p>
        ) : (
          <p className="review__quiet">Nothing needs attention.</p>
        )}
        {items.length > 0 && deskLoading && <p className="review__quiet"><Spinner size={13} /> Checking the builds…</p>}
      </section>

      <section aria-labelledby="drafts" className="review__section">
        <div className="review__head"><h2 id="drafts">Drafts</h2></div>
        <DraftList />
      </section>

      <section aria-labelledby="verify-h" className="review__section review__section--quiet">
        <div className="review__head">
          <h2 id="verify-h">Verify a file</h2>
          <Link to="/verify">Full page →</Link>
        </div>
        <p className="review__quiet">Check a report file you were sent.</p>
        <VerifyZone entry />
      </section>
    </div>
  )
}

// One row per thing: its chip, what, why, when, and what to do about it. A
// request the person may decide is decided here; a code request opens its
// files here.
function Attention({ items }) {
  const [open, setOpen] = useState(null)        // key of the request opened in place
  return (
    <ul aria-label="Needs attention" className="dlist review__attention">
      {items.map(it => {
        const acting = open === it.key
        return (
          <li key={it.key}>
            <div className="dlist__row review__row">
              <span className="dlist__main">
                <span className="dlist__name">
                  {it.verdict
                    ? <Verdict state={it.verdict} size="sm" />
                    : <Badge variant={it.variant} style={{ textTransform: 'none' }}>{it.kind}</Badge>}
                  <span style={{ overflowWrap: 'anywhere' }}>{it.title}</span>
                </span>
                <span className="dlist__facts">{it.detail}</span>
              </span>
              <span className="dlist__side">
                {when(it.at) && <span className="dlist__when">{when(it.at)}</span>}
                {it.href && <Link to={it.href} className="review__open">{it.action || 'Open'}</Link>}
                {(it.decide || it.review) && (
                  <button type="button" className="review__open review__btn" aria-expanded={acting}
                          onClick={() => setOpen(acting ? null : it.key)}>
                    {acting ? 'Close' : it.decide ? 'Decide' : 'Review'}
                  </button>
                )}
              </span>
            </div>
            {acting && (
              <div className="review__act">
                {it.decide && <RequestDecision request={it.decide} />}
                {it.review && <CodeReview id={it.review.id} />}
              </div>
            )}
          </li>
        )
      })}
    </ul>
  )
}
