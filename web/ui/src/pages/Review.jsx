import { useState } from 'react'
import { Link, Navigate, useLocation } from 'react-router-dom'

import { useCodeRequests, useDesk, usePipelines, usePublishRequests, useReports, useRuns } from '../api'
import { attentionItems } from '../components/Attention'
import { PageHeader, useReportModels } from '../components/Scope'
import { Chip, Spinner, Time, Verdict } from '../components/Shared'
import { REVIEW_TABS, whereAmI } from '../nav'
import DraftList, { CodeReview, RequestDecision } from './Drafts'

// Review: what waits on a person, as tabs in the order they act on it, each
// at its own address: Attention (/review: failed runs, builds that need a
// look, requests waiting on a decision), Drafts (/review/drafts), History
// (/runs) and Verify (/verify).

/** Review's heading and tab row, around one tab's page. */
export function ReviewFrame({ children }) {
  const here = whereAmI(useLocation().pathname)?.page
  return (
    <div className="fade-in review">
      <PageHeader pageKey="review" />
      <nav aria-label="Review: what to show">
        <ul className="dtabs review__tabs">
          {REVIEW_TABS.map(t => (
            <li key={t.key}>
              <Link to={t.path} aria-current={here === t.key ? 'page' : undefined}>{t.label}</Link>
            </li>
          ))}
        </ul>
      </nav>
      <div className="stage">{children}</div>
    </div>
  )
}

export default function Review() {
  const { data: desk, isLoading: deskLoading } = useDesk()
  const { data: pipelines } = usePipelines()
  const { data: reports } = useReports()
  const { data: runs } = useRuns('', '')
  const { data: requests } = usePublishRequests()
  const { data: codeRequests } = useCodeRequests()
  const modelsOf = useReportModels()
  const items = attentionItems(desk, pipelines, modelsOf, reports || [], { runs, requests, codeRequests })

  // The old Drafts section's address is the Drafts tab now.
  if (useLocation().hash === '#drafts') return <Navigate to="/review/drafts" replace />

  return (
    <ReviewFrame>
      <section aria-labelledby="attention-h" className="review__section">
        <div className="review__head">
          <h2 id="attention-h">Needs attention {items.length > 0 && <span className="review__count">{items.length}</span>}</h2>
        </div>
        {items.length > 0 ? <Attention items={items} /> : deskLoading ? (
          <p className="review__quiet"><Spinner size={13} /> Checking the builds…</p>
        ) : (
          <p className="review__quiet">Nothing needs attention.</p>
        )}
        {items.length > 0 && deskLoading && <p className="review__quiet"><Spinner size={13} /> Checking the builds…</p>}
      </section>
    </ReviewFrame>
  )
}

/** The Drafts tab. */
export function ReviewDrafts() {
  return (
    <ReviewFrame>
      <section aria-labelledby="drafts" className="review__section">
        <div className="review__head"><h2 id="drafts">Drafts</h2></div>
        <DraftList />
      </section>
    </ReviewFrame>
  )
}

// An item's state is a chip: its colour from what Attention says of it.
const TONE = { red: 'bad', amber: 'warn', gray: 'none' }

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
                    : <Chip tone={TONE[it.variant]}>{it.kind}</Chip>}
                  <span style={{ overflowWrap: 'anywhere' }}>{it.title}</span>
                </span>
                <span className="dlist__facts">{it.detail}</span>
              </span>
              <span className="dlist__side">
                {it.at && <span className="dlist__when"><Time iso={it.at} /></span>}
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
