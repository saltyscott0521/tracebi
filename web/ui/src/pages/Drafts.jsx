import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import {
  useDrafts, useDraftVersion, useDraftFiles, useDraftPreview, useDraftImpact,
  usePublishDraft, useDeleteDraft, useWriteDraftFile, useMe,
  useDraftDestinations, usePublishRequests, useDecideRequest,
  useCodeRequests, useCodeRequest, useDecideCodeRequest,
} from '../api'
import { reportPagePath } from '../nav'
import {
  PageTitle, PageSub, Card, Btn, BtnLink, Chip, Empty, Spinner, Alert, ErrorDetail,
  ReportFrame, Segmented, SkeletonList, Time, Verdict, useToast,
} from '../components/Shared'
import { CodeFiles } from '../components/CodeView'
import { stamp } from '../when'

// Drafts: what an agent (or a person) is writing before it is published, as a
// section of Review and a page per draft. A draft is private to its owner; Publish is the one step that changes what
// everyone sees. An analyst or admin can edit a draft's files here; Save writes
// the file and the live preview follows.

const href = d => `/drafts/${encodeURIComponent(d.owner)}/${d.kind}/${d.path.split('/').map(encodeURIComponent).join('/')}`
const kindLabel = kind => (kind === 'models' ? 'Model' : 'Report')

// The owner a sign-in name becomes on disk (tracebi.drafts.slug_owner): a
// name with characters that had to be replaced gains a short hash, so match
// its prefix then.
function isMine(owner, actor) {
  const lowered = (actor || '').replace(/^mcp:/, '').toLowerCase()
  const slug = lowered.replace(/[^a-z0-9._@+-]/g, '-').replace(/^\.+/, m => '-'.repeat(m.length)) || 'anonymous'
  return owner === slug || (slug !== lowered && owner.startsWith(`${slug}-`))
}

/**
 * Review's Drafts: the person's own drafts first; an admin may see
 * everyone's. A viewer cannot start one, and is told so instead of a list.
 * Requests already decided sit below, folded.
 */
export default function DraftList() {
  const { data: me } = useMe()
  const canDraft = me?.role === 'analyst' || me?.role === 'admin'
  const { data, isLoading, error } = useDrafts()
  // With no sign-in there is no "own": every draft is shown.
  const [everyone, setEveryone] = useState(null)
  const all = data?.drafts || []
  const actor = me?.actor
  const showAll = everyone ?? !actor
  const others = all.some(d => !isMine(d.owner, actor))
  const list = (showAll || !actor ? all : all.filter(d => isMine(d.owner, actor)))
    .map((d, i) => [d, i])
    .sort(([a, i], [b, j]) => (isMine(b.owner, actor) - isMine(a.owner, actor)) || (i - j))
    .map(([d]) => d)

  if (me && !canDraft) {
    return (
      <p className="review__quiet">
        Drafts need the analyst role. A draft is a report or model being written before it is published.
      </p>
    )
  }
  return (
    <>
      {me?.role === 'admin' && actor && others && (
        <Segmented label="Whose drafts" value={showAll ? 'all' : 'mine'} onChange={v => setEveryone(v === 'all')}
                   options={[['mine', 'Mine'], ['all', 'Everyone’s']]} />
      )}
      {error && <ErrorDetail error={error} />}
      {isLoading && <SkeletonList rows={2} />}
      {data && list.length === 0 && (
        <>
          <Empty title="No drafts"
                 body="A draft is a report or model being written before it is published. Start one from a report's page with Edit as a draft, or keep an answer from Ask."
                 action={<BtnLink to="/" size="sm">Open the reports</BtnLink>} />
          <details className="review__agent">
            <summary>For your agent</summary>
            <p>
              An agent connected to this server over MCP starts a draft with <code>start_draft</code> and
              writes its files with <code>write_draft_file</code>; the draft appears here. Python (a transform,
              a model in Python) comes from a laptop instead: <code>tracebi push</code> sends it as a code
              request for an admin to review.
            </p>
          </details>
        </>
      )}
      {list.length > 0 && (
        <ul aria-label="Drafts" className="dlist">
          {list.map(d => (
            <li key={`${d.owner}/${d.kind}/${d.path}`}>
              <Link to={href(d)} className="dlist__row">
                <span className="dlist__main">
                  <span className="dlist__name">
                    <Verdict state="draft" size="sm" />
                    <span style={{ overflowWrap: 'anywhere' }}>{d.path}</span>
                  </span>
                  <span className="dlist__facts">
                    {kindLabel(d.kind)} · by {d.owner} ·{' '}
                    {d.differs_from_published ? 'Changed from the published one' : 'Same as published'}
                  </span>
                </span>
                <span className="dlist__side">
                  <span className="dlist__when">changed <Time iso={d.updated} fallback="unknown" /></span>
                  <span className="review__open">Open</span>
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
      <SettledRequests />
    </>
  )
}

/**
 * Approve or decline one pending publish request, in place. Declining asks
 * for a reason, which the person who asked sees.
 */
export function RequestDecision({ request: r }) {
  const decide = useDecideRequest()
  const toast = useToast()
  const [declining, setDeclining] = useState(false)
  const [reason, setReason] = useState('')
  const [failure, setFailure] = useState(null)
  const run = approve => decide.mutate(
    { id: r.id, approve, note: approve ? '' : reason.trim() }, {
      onSuccess: () => {
        setDeclining(false); setReason(''); setFailure(null)
        toast(approve ? `Published ${r.destination}` : 'Request declined', 'success')
      },
      onError: err => setFailure(err),
    })
  return (
    <div>
      {failure && <div role="alert"><ErrorDetail error={failure} /></div>}
      {!declining ? (
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <Btn size="sm" onClick={() => run(true)} disabled={decide.isPending}
               aria-label={`Approve publishing ${r.destination}`}>Approve and publish</Btn>
          <Btn size="sm" variant="outline" onClick={() => { setDeclining(true); setReason(''); setFailure(null) }}
               aria-label={`Decline publishing ${r.destination}`}>Decline</Btn>
        </div>
      ) : (
        <div>
          <label htmlFor={`decline-${r.id}`} style={{ display: 'block', fontSize: 'var(--text-sm)', fontWeight: 600, marginBottom: 4 }}>
            Reason (the person who asked will see it)
          </label>
          <input id={`decline-${r.id}`} value={reason} onChange={e => setReason(e.target.value)}
            style={{
              width: '100%', maxWidth: 480, padding: '8px 10px', marginBottom: 8,
              border: '1px solid var(--border-strong)', borderRadius: 'var(--radius-sm)',
              background: 'var(--surface)', color: 'var(--text)', fontSize: 'var(--text-caption)', fontFamily: 'inherit',
            }} />
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <Btn size="sm" variant="red" onClick={() => run(false)} disabled={decide.isPending || !reason.trim()}>
              Decline request
            </Btn>
            <Btn size="sm" variant="outline" onClick={() => setDeclining(false)}>Cancel</Btn>
          </div>
        </div>
      )}
    </div>
  )
}

// Requests already decided: publish requests (someone with only Build in a
// folder asks; someone with Publish there decides) and code pushed from a
// laptop (`tracebi push`, which an admin reviews file by file). The ones still
// waiting are under Needs attention.
function SettledRequests() {
  const { data: publish } = usePublishRequests()
  const { data: code } = useCodeRequests()
  const [open, setOpen] = useState(null)               // code request id shown
  const settled = (publish || []).filter(r => r.status !== 'pending').slice(0, 5)
  const pushed = (code || []).filter(r => r.status !== 'pending').slice(0, 5)
  if (!settled.length && !pushed.length) return null
  const decided = r => (
    <>
      Asked by {r.requested_by || 'unknown'} <Time iso={r.requested_at} />
      {r.note && <> · “{r.note}”</>}
      {r.decided_by && <> · {r.status === 'approved' ? 'approved' : 'declined'} by {r.decided_by} <Time iso={r.decided_at} /></>}
      {r.status === 'rejected' && r.decision_note && <> · reason: {r.decision_note}</>}
    </>
  )
  const status = r => (
    <Chip tone={r.status === 'approved' ? '' : 'none'}>{r.status === 'approved' ? 'Approved' : 'Declined'}</Chip>
  )
  return (
    <details className="review__requests">
      <summary>Requests <span className="review__count">{settled.length + pushed.length}</span></summary>
      <ul aria-label="Requests" style={{ listStyle: 'none', padding: 0, margin: 0 }}>
        {settled.map(r => (
          <li key={r.id} className="review__request">
            <div><span style={{ fontWeight: 600, overflowWrap: 'anywhere' }}>Publish {r.destination}</span> {status(r)}</div>
            <div className="review__quiet">{decided(r)}</div>
          </li>
        ))}
        {pushed.map(r => (
          <li key={r.id} className="review__request">
            <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 8 }}>
              <span style={{ fontWeight: 600, overflowWrap: 'anywhere' }}>
                Code: {r.files.length === 1 ? r.files[0] : `${r.files.length} files`}
              </span>
              {status(r)}
              <Btn size="sm" variant="outline" style={{ marginLeft: 'auto' }}
                   onClick={() => setOpen(open === r.id ? null : r.id)} aria-expanded={open === r.id}>
                {open === r.id ? 'Close' : 'Details'}
              </Btn>
            </div>
            <div className="review__quiet">{decided(r)}</div>
            {open === r.id && <CodeReview id={r.id} />}
          </li>
        ))}
      </ul>
    </details>
  )
}

function Diff({ text }) {
  return (
    <pre style={{ margin: 0, padding: '8px 10px', overflowX: 'auto', fontSize: 'var(--text-sm)', lineHeight: 1.45,
                  background: 'var(--surface-2)', borderRadius: 'var(--radius-sm)' }}>
      {text.split('\n').map((line, i) => (
        <div key={i} style={{
          color: line.startsWith('+') && !line.startsWith('+++') ? 'var(--green-text)'
            : line.startsWith('-') && !line.startsWith('---') ? 'var(--red-text)' : undefined,
        }}>{line || ' '}</div>
      ))}
    </pre>
  )
}

export function CodeReview({ id }) {
  const { data: req, isLoading, error } = useCodeRequest(id, true)
  const decide = useDecideCodeRequest()
  const toast = useToast()
  const [declining, setDeclining] = useState(false)
  const [reason, setReason] = useState('')
  const [failure, setFailure] = useState(null)
  if (isLoading) return <Spinner />
  if (error) return <ErrorDetail error={error} />
  const act = approve => decide.mutate({ id, approve, note: approve ? '' : reason.trim() }, {
    onSuccess: res => {
      setFailure(null); setDeclining(false)
      toast(approve ? `Approved: ${(res.runs || []).length} pipeline run(s) started` : 'Request declined', 'success')
    },
    onError: err => setFailure(err),
  })
  return (
    <div style={{ marginTop: 10, display: 'grid', gap: 10 }}>
      {req.files.map(f => (
        <div key={f.path}>
          <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600, marginBottom: 4 }}>
            {f.path} {f.new && <Chip>New file</Chip>}
          </div>
          <Diff text={f.diff || '(no change)'} />
        </div>
      ))}
      {(req.runs || []).length > 0 && (
        <div style={{ fontSize: 'var(--text-sm)' }}>
          Runs after approval:{' '}
          {req.runs.map(run => (
            <span key={run.pipeline} style={{ marginRight: 10 }}>
              {run.pipeline}: <strong>{run.error ? 'did not start' : run.status || 'started'}</strong>
              {run.error && <> ({run.error})</>}
            </span>
          ))}
          <Link to="/runs">See runs</Link>
        </div>
      )}
      {failure && <div role="alert"><ErrorDetail error={failure} /></div>}
      {req.status === 'pending' && req.can_decide && !declining && (
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <Btn size="sm" onClick={() => act(true)} disabled={decide.isPending}>Approve and run</Btn>
          <Btn size="sm" variant="outline" onClick={() => setDeclining(true)}>Decline</Btn>
        </div>
      )}
      {req.status === 'pending' && !req.can_decide && (
        <div style={{ fontSize: 'var(--text-sm)', color: 'var(--muted)' }}>An admin will review it.</div>
      )}
      {declining && (
        <div>
          <label htmlFor={`code-decline-${id}`} style={{ display: 'block', fontSize: 'var(--text-sm)', fontWeight: 600, marginBottom: 4 }}>
            Reason (the person who asked will see it)
          </label>
          <input id={`code-decline-${id}`} value={reason} onChange={e => setReason(e.target.value)}
            style={{
              width: '100%', maxWidth: 480, padding: '8px 10px', marginBottom: 8,
              border: '1px solid var(--border-strong)', borderRadius: 'var(--radius-sm)',
              background: 'var(--surface)', color: 'var(--text)', fontSize: 'var(--text-caption)', fontFamily: 'inherit',
            }} />
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <Btn size="sm" variant="red" onClick={() => act(false)} disabled={decide.isPending || !reason.trim()}>
              Decline request
            </Btn>
            <Btn size="sm" variant="outline" onClick={() => setDeclining(false)}>Cancel</Btn>
          </div>
        </div>
      )}
    </div>
  )
}

// Where a draft sits: Review › Drafts, then its own name as the title.
function DraftCrumb() {
  return (
    <nav aria-label="Where this draft is" className="rp__crumb" style={{ marginBottom: 6 }}>
      <Link to="/review">Review</Link>
      <span aria-hidden="true">›</span>
      <Link to="/review/drafts">Drafts</Link>
    </nav>
  )
}

const modeSentence = {
  publish: 'Publishes directly: you hold Publish permission there.',
  request: 'Sends a request: you can build there but not publish, so someone with Publish permission approves it first.',
}

export function DraftPage() {
  const { owner, kind, '*': path } = useParams()
  const d = { owner, kind, path }
  const toast = useToast()
  const navigate = useNavigate()
  const isReport = kind === 'reports'
  const [tab, setTab] = useState(isReport ? 'Preview' : 'Files')
  const [step, setStep] = useState(null) // null | 'publish' | 'delete'
  const [note, setNote] = useState('')
  const [accept, setAccept] = useState(false)
  const [published, setPublished] = useState(null)
  const [dest, setDest] = useState(null)          // chosen destination folder ('' = its own place)
  const [refusal, setRefusal] = useState(null)
  const [edits, setEdits] = useState({}) // file name -> { base, text, saved, error }

  const { data: me } = useMe()
  const canEdit = me?.role === 'analyst' || me?.role === 'admin'
  const { data: version, error: versionError } = useDraftVersion(d)
  const { data: files, isPlaceholderData: filesStale } = useDraftFiles(d, version)
  const { data: html, error: previewError } = useDraftPreview(d, version, isReport)
  const { data: impact, error: impactError } = useDraftImpact(d, version, !isReport)
  const needsAccept = !!impact?.needs_acceptance
  useEffect(() => { setAccept(false) }, [version])   // a changed draft needs its impact accepted again
  // Keep the last page that rendered, so a broken save shows its error above
  // the previous page instead of a blank one.
  const lastHtml = useRef(null)
  if (html) lastHtml.current = html
  const { data: places } = useDraftDestinations(d, isReport && step === 'publish')
  const usable = (places || []).filter(p => p.mode)
  const chosen = usable.find(p => (p.folder || '') === dest) || usable[0]
  const publish = usePublishDraft(d)
  const del = useDeleteDraft(d)
  const write = useWriteDraftFile(d)
  const unsaved = Object.values(edits).some(e => e.text !== e.base)

  // Closing the tab with text that never reached the draft would lose it.
  useEffect(() => {
    if (!unsaved) return undefined
    const warn = e => { e.preventDefault(); e.returnValue = '' }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [unsaved])

  const doPublish = () => {
    setRefusal(null)
    publish.mutate({ note: note.trim(), acceptImpact: needsAccept && accept, folder: chosen?.folder }, {
      onSuccess: res => {
        setStep(null); setNote(''); setAccept(false); setPublished(res)
        toast(res.status === 'requested'
          ? `Asked to publish ${path}`
          : `Published ${kindLabel(kind).toLowerCase()} ${path}`, 'success')
      },
      onError: err => { setRefusal(err); setStep(null) },
    })
  }
  const doDelete = () => del.mutate(undefined, {
    onSuccess: () => { toast('Draft deleted', 'success'); navigate('/review/drafts') },
    onError: err => { setRefusal(err); setStep(null) },
  })

  if (versionError) {
    return (
      <div className="fade-in">
        <DraftCrumb />
        <PageTitle>{path}</PageTitle>
        <ErrorDetail error={versionError} />
      </div>
    )
  }

  const busy = publish.isPending || del.isPending || write.isPending

  return (
    <div className="fade-in">
      <DraftCrumb />
      <PageTitle>{path}</PageTitle>
      <PageSub>Draft by {owner} · updated {stamp(files?.updated) || '…'}</PageSub>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 16, alignItems: 'center' }}>
        <Btn onClick={() => setStep('publish')} disabled={busy || step === 'publish'}>Publish</Btn>
        <Btn variant="outline" onClick={() => setStep('delete')} disabled={busy || step === 'delete'}>Delete</Btn>
        {busy && <Spinner />}
      </div>

      {step === 'publish' && (
        <Card style={{ marginBottom: 16 }}>
          <p style={{ fontSize: 'var(--text-caption)', lineHeight: 1.6, marginBottom: 10 }}>
            {chosen?.personal
              ? 'Publishing puts this report in My published: only you, and anyone you share the folder with, see it. The version it replaces is kept.'
              : `Publishing replaces the ${kindLabel(kind).toLowerCase()} everyone who can see it sees with this draft. The version it replaces is kept.`}
          </p>
          {isReport && places && (
            <div style={{ marginBottom: 12 }}>
              <label htmlFor="draft-dest" style={{ display: 'block', fontSize: 'var(--text-sm)', fontWeight: 600, marginBottom: 4 }}>
                Publish to
              </label>
              <select id="draft-dest" value={chosen ? (chosen.folder || '') : ''}
                onChange={e => setDest(e.target.value)} disabled={!usable.length}
                style={{
                  minHeight: 36, maxWidth: '100%', padding: '6px 10px',
                  border: '1px solid var(--border-strong)', borderRadius: 'var(--radius-sm)',
                  background: 'var(--surface)', color: 'var(--text)', fontSize: 'var(--text-caption)', fontFamily: 'inherit',
                }}>
                {usable.map(p => (
                  <option key={p.folder || ''} value={p.folder || ''}>
                    {p.label} ({p.mode === 'publish' ? 'publishes directly' : 'asks for approval'})
                  </option>
                ))}
              </select>
              {chosen && (
                <p role="status" style={{ fontSize: 'var(--text-sm)', color: 'var(--muted)', margin: '6px 0 0' }}>
                  {modeSentence[chosen.mode]} It will be {chosen.destination}.
                  {chosen.accepts === 'checkable' && ' This folder accepts only reports whose every number a query can re-run.'}
                </p>
              )}
              {!usable.length && (
                <Alert variant="warn">You do not hold Build permission on any folder this report can go to.</Alert>
              )}
            </div>
          )}
          {unsaved && (
            <Alert variant="warn">
              △ A file has unsaved changes. Publishing uses what is saved in the draft.
            </Alert>
          )}
          <label htmlFor="draft-note" style={{ display: 'block', fontSize: 'var(--text-sm)', fontWeight: 600, marginBottom: 4 }}>
            Note (optional)
          </label>
          <input id="draft-note" value={note} onChange={e => setNote(e.target.value)}
            placeholder="What changed and why"
            style={{
              width: '100%', maxWidth: 480, padding: '8px 10px', marginBottom: 12,
              border: '1px solid var(--border-strong)', borderRadius: 'var(--radius-sm)',
              background: 'var(--surface)', color: 'var(--text)', fontSize: 'var(--text-caption)', fontFamily: 'inherit',
            }} />
          {needsAccept && (
            <label style={{ display: 'flex', gap: 8, alignItems: 'flex-start', fontSize: 'var(--text-caption)', lineHeight: 1.5, marginBottom: 12 }}>
              <input type="checkbox" checked={accept} onChange={e => setAccept(e.target.checked)}
                style={{ marginTop: 3 }} />
              <span>
                I have read the impact below and accept it: {impact.summary.moves || 0} report(s)
                change{impact.summary.breaks ? ` and ${impact.summary.breaks} stop(s) working` : ''}.
              </span>
            </label>
          )}
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <Btn onClick={doPublish}
                 disabled={busy || (needsAccept && !accept) || (isReport && !chosen)}>
              {chosen?.mode === 'request' ? 'Ask to publish'
                : chosen?.folder ? `Publish to ${chosen.label}` : 'Publish for everyone'}
            </Btn>
            <Btn variant="outline" onClick={() => setStep(null)}>Cancel</Btn>
          </div>
        </Card>
      )}
      {step === 'delete' && (
        <Card style={{ marginBottom: 16 }}>
          <p style={{ fontSize: 'var(--text-caption)', lineHeight: 1.6, marginBottom: 12 }}>
            Delete this draft? Anything published stays as it is.
          </p>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <Btn variant="red" onClick={doDelete} disabled={busy}>Delete draft</Btn>
            <Btn variant="outline" onClick={() => setStep(null)}>Cancel</Btn>
          </div>
        </Card>
      )}

      {!isReport && <ModelImpact impact={impact} error={impactError} />}

      {refusal && <div role="alert"><ErrorDetail error={refusal} /></div>}
      {published?.status === 'requested' && (
        <Alert variant="info">
          Asked. Nothing is published yet: someone with Publish permission on {published.request.destination} will
          approve or decline it under <Link to="/review">Review</Link>, and you will see the answer there.
        </Alert>
      )}
      {published && published.status !== 'requested' && (
        <Alert variant="info">
          Published.{' '}
          {isReport
            ? <Link to={reportPagePath(published.path)}>Open the published report</Link>
            : 'The model is live once discovery picks it up.'}
        </Alert>
      )}

      {isReport && <Segmented options={['Preview', 'Files']} value={tab} onChange={setTab} label="What to show of the draft" />}

      {tab === 'Preview' && isReport && (
        <>
          {previewError && <div role="alert"><ErrorDetail error={previewError} /></div>}
          {lastHtml.current
            ? <ReportFrame html={lastHtml.current} title={`Draft ${path}`} />
            : !previewError && <Spinner />}
        </>
      )}
      {/* Hidden, not unmounted, off its tab: an open editor keeps its text. */}
      <div hidden={tab !== 'Files'}>
        {!isReport && (
          <p style={{ fontSize: 'var(--text-caption)', color: 'var(--muted)', marginBottom: 12 }}>
            A model draft has no page. It is the file below, and it becomes a model when published.
          </p>
        )}
        {files
          ? <DraftFiles texts={files.files} stale={filesStale} edits={edits} setEdits={setEdits}
              write={write} canEdit={canEdit} />
          : <Spinner />}
      </div>
    </div>
  )
}

const IMPACT_TONE = { unchanged: '', moves: 'warn', breaks: 'bad', not_built: 'none', not_checkable: 'none' }
const IMPACT_LABEL = {
  unchanged: 'Unchanged', moves: 'Numbers move', breaks: 'Breaks',
  not_built: 'Not built, cannot compare', not_checkable: 'Cannot compare',
}
const show = v => (v === null || v === undefined ? 'n/a' : typeof v === 'number' ? v.toLocaleString() : String(v))

// Which published reports reading this model a publish would change, from
// re-running their last build's queries against the draft.
function ModelImpact({ impact, error }) {
  if (error) return <div role="alert"><ErrorDetail error={error} /></div>
  if (!impact) return null
  return (
    <Card style={{ marginBottom: 16 }}>
      <h2 style={{ fontSize: 'var(--text-base)', margin: '0 0 6px' }}>Impact on published reports</h2>
      {impact.reports.length === 0 && (
        <p style={{ fontSize: 'var(--text-caption)', color: 'var(--muted)', margin: 0 }}>No published report reads this model.</p>
      )}
      <ul aria-label="Reports this model draft touches" style={{ listStyle: 'none', padding: 0, margin: 0, display: 'grid', gap: 10 }}>
        {impact.reports.map(r => (
          <li key={r.report} style={{ fontSize: 'var(--text-caption)', lineHeight: 1.5 }}>
            <span style={{ fontWeight: 600, overflowWrap: 'anywhere' }}>{r.report}</span>{' '}
            <Chip tone={IMPACT_TONE[r.status]}>{IMPACT_LABEL[r.status]}</Chip>
            {(r.status === 'not_built' || r.status === 'not_checkable') && (
              <div style={{ color: 'var(--muted)' }}>{r.detail}</div>
            )}
            {(r.moved || []).map(m => (
              <div key={m.binding} style={{ marginLeft: 12 }}>
                <span style={{ fontFamily: 'var(--font-mono)' }}>{m.binding}</span>
                {m.figures.length === 0 && <> changes ({show(m.rows[0])} to {show(m.rows[1])} rows)</>}
                {m.figures.map(f => (
                  <div key={f.id}>{f.id}: {show(f.old)} to {show(f.new)}</div>
                ))}
              </div>
            ))}
            {(r.broken || []).map(b => (
              <div key={b.binding} style={{ marginLeft: 12, color: 'var(--red-text)' }}>
                <span style={{ fontFamily: 'var(--font-mono)' }}>{b.binding}</span>: {b.error}
              </div>
            ))}
          </li>
        ))}
      </ul>
    </Card>
  )
}

const mono = { fontFamily: 'var(--font-mono)' }
const target = { minHeight: 44 }

// The Files tab: each file read-only until Edit, then a textarea. Nothing
// reaches the draft until Save. The text lives in the page's `edits` so it
// survives choosing another file or tab.
function DraftFiles({ texts, stale, edits, setEdits, write, canEdit }) {
  const names = Object.keys(texts)
  const [active, setActive] = useState(null)
  const leave = useRef(false)   // Esc was pressed: the next Tab leaves the textarea
  const focus = useRef(false)   // focus the textarea once, when Edit opens it
  const name = names.includes(active) ? active : names[0]
  const edit = edits[name]
  const dirty = !!edit && edit.text !== edit.base
  // The file changed under the editor (an agent wrote it). With typing in the
  // editor Save would replace that, so say so; with none, the editor just
  // follows the file.
  const changed = !!edit && !stale && texts[name] !== edit.base
  const elsewhere = changed && dirty

  const patch = (file, change) =>
    setEdits(all => (all[file] ? { ...all, [file]: { ...all[file], ...change } } : all))
  const begin = () => {
    focus.current = true
    setEdits(all => ({ ...all, [name]: { base: texts[name], text: texts[name], saved: false, error: null } }))
  }
  const close = () => setEdits(all => {
    const { [name]: _closed, ...rest } = all
    return rest
  })
  const save = () => {
    if (!dirty || write.isPending) return
    const { text } = edit
    write.mutate({ file: name, content: text }, {
      onSuccess: () => setEdits(all => (all[name]
        ? { ...all, [name]: { ...all[name], base: text, saved: all[name].text === text, error: null } }
        : all)),
      onError: error => patch(name, { error }),
    })
  }

  useEffect(() => {
    if (changed && !dirty) patch(name, { base: texts[name], text: texts[name] })
  }, [changed, dirty, name, texts]) // eslint-disable-line react-hooks/exhaustive-deps

  const onKeyDown = e => {
    if ((e.metaKey || e.ctrlKey) && !e.altKey && e.key.toLowerCase() === 's') {
      e.preventDefault()
      save()
    } else if (e.key === 'Escape') {
      leave.current = true
    } else if (e.key !== 'Tab') {
      leave.current = false
    } else if (!leave.current && !e.shiftKey && !e.metaKey && !e.ctrlKey && !e.altKey) {
      e.preventDefault()
      const box = e.currentTarget
      box.setRangeText('  ', box.selectionStart, box.selectionEnd, 'end')
      patch(name, { text: box.value, saved: false, error: null })
    }
  }

  if (!name) return <Spinner />

  return (
    <>
      {names.length > 1 && (
        <div className="codeview__tabs">
          {names.map(n => {
            const open = edits[n] && edits[n].text !== edits[n].base
            return (
              <Btn key={n} size="sm" variant={n === name ? undefined : 'outline'}
                   aria-label={open ? `${n}, unsaved changes` : undefined}
                   onClick={() => setActive(n)} style={{ ...mono, minHeight: 36 }}>
                {n}{open && ' △'}
              </Btn>
            )
          })}
        </div>
      )}

      {canEdit && (
        <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 8, marginBottom: 10 }}>
          {edit ? (
            <>
              <Btn onClick={save} disabled={!dirty || write.isPending} style={target}>
                {write.isPending ? 'Saving…' : 'Save'}
              </Btn>
              <Btn variant="outline" onClick={close} disabled={write.isPending} style={target}>
                {dirty ? 'Discard' : 'Close'}
              </Btn>
            </>
          ) : (
            <Btn variant="outline" onClick={begin} style={target}>Edit</Btn>
          )}
          <span role="status" style={{
            fontSize: 'var(--text-sm)', color: dirty ? 'var(--amber-text)' : 'var(--muted)', fontWeight: dirty ? 600 : 400,
          }}>
            {dirty ? '△ Unsaved changes' : edit?.saved ? 'Saved' : ''}
          </span>
        </div>
      )}

      {edit?.error && <div role="alert"><ErrorDetail error={edit.error} /></div>}
      {elsewhere && (
        <Alert variant="warn">
          △ This file changed on the server since you started editing. Saving replaces it with your version.
        </Alert>
      )}

      {edit ? (
        <>
          <div className="codeview__bar"><span className="codeview__path">{name}</span></div>
          <textarea
            key={name}
            ref={el => { if (el && focus.current) { focus.current = false; el.focus() } }}
            aria-label={`Edit ${name}`} aria-describedby="draft-editor-hint"
            value={edit.text} wrap="off" spellCheck={false} autoCapitalize="off" autoComplete="off"
            rows={Math.min(32, Math.max(14, edit.text.split('\n').length + 1))}
            onChange={e => patch(name, { text: e.target.value, saved: false, error: null })}
            onKeyDown={onKeyDown} onBlur={() => { leave.current = false }}
            style={{
              ...mono, display: 'block', width: '100%', boxSizing: 'border-box', padding: '12px 14px',
              fontSize: 'var(--text-caption)', lineHeight: 1.6, tabSize: 2, whiteSpace: 'pre', overflow: 'auto', resize: 'vertical',
              color: 'var(--text)', background: 'var(--surface)',
              border: '1px solid var(--border-strong)', borderRadius: 'var(--radius-lg)',
            }} />
          <p id="draft-editor-hint" style={{ fontSize: 'var(--text-sm)', color: 'var(--muted)', margin: '6px 0 0' }}>
            Tab inserts two spaces; Esc, then Tab, leaves the editor. Cmd or Ctrl+S saves.
          </p>
        </>
      ) : (
        <CodeFiles key={name} files={[{ path: name, content: texts[name] }]} />
      )}
    </>
  )
}
