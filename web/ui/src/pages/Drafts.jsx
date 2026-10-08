import { useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import {
  useDrafts, useDraftVersion, useDraftFiles, useDraftPreview,
  usePublishDraft, useDeleteDraft,
} from '../api'
import { reportModels, reportPagePath } from '../nav'
import {
  PageTitle, PageSub, Card, Btn, Badge, Spinner, Empty, Alert, ErrorDetail,
  ReportFrame, Tabs, SkeletonList, useToast,
} from '../components/Shared'
import { CodeFiles } from '../components/CodeView'
import { when } from '../components/Attention'

// Drafts: what an agent (or a person) is writing before it is published. A
// draft is private to its owner; Publish is the one step that changes what
// everyone sees.

const href = d => `/drafts/${encodeURIComponent(d.owner)}/${d.kind}/${d.path.split('/').map(encodeURIComponent).join('/')}`
const kindLabel = kind => (kind === 'models' ? 'Model' : 'Report')

function Differs({ differs }) {
  return differs
    ? <Badge variant="amber">Changed</Badge>
    : <Badge variant="gray">Same as published</Badge>
}

export default function Drafts() {
  const { data, isLoading, error } = useDrafts()
  const list = data?.drafts || []
  const manyOwners = new Set(list.map(d => d.owner)).size > 1

  return (
    <div className="fade-in">
      <PageTitle>Drafts</PageTitle>
      <PageSub>
        Reports and models being written before they are published, newest first.
        Nothing here changes what anyone sees until it is published.
      </PageSub>
      {error && <ErrorDetail error={error} />}
      {isLoading && <SkeletonList rows={3} />}
      {data && list.length === 0 && (
        <Card>
          <Empty
            message="No drafts yet. A draft starts when an agent connected to this server over MCP calls start_draft and write_draft_file. Ask your agent to draft a report here, and it will appear in this list."
          />
        </Card>
      )}
      {list.length > 0 && (
        <ul aria-label="Drafts" style={{ listStyle: 'none', padding: 0, display: 'grid', gap: 10 }}>
          {list.map(d => (
            <li key={`${d.owner}/${d.kind}/${d.path}`}>
              <Link to={href(d)} className="draft-row" style={{
                display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: '6px 12px',
                padding: '12px 16px', textDecoration: 'none', color: 'var(--text)',
                background: 'var(--surface)', border: '1px solid var(--border)',
                borderRadius: 'var(--radius-lg)',
              }}>
                <span style={{ fontWeight: 600, fontSize: 14, minWidth: 0, overflowWrap: 'anywhere' }}>{d.path}</span>
                <Badge variant="blue">{kindLabel(d.kind)}</Badge>
                <Differs differs={d.differs_from_published} />
                <span style={{ marginLeft: 'auto', fontSize: 12, color: 'var(--muted)' }}>
                  {manyOwners && <>by {d.owner} · </>}updated {when(d.updated) || 'unknown'}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
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
  const [published, setPublished] = useState(null)
  const [refusal, setRefusal] = useState(null)

  const { data: version, error: versionError } = useDraftVersion(d)
  const { data: files } = useDraftFiles(d, version)
  const { data: html, error: previewError } = useDraftPreview(d, version, isReport)
  // Keep the last page that rendered, so a broken save shows its error above
  // the previous page instead of a blank one.
  const lastHtml = useRef(null)
  if (html) lastHtml.current = html
  const publish = usePublishDraft(d)
  const del = useDeleteDraft(d)

  const doPublish = () => {
    setRefusal(null)
    publish.mutate(note.trim(), {
      onSuccess: res => {
        setStep(null); setNote(''); setPublished(res)
        toast(`Published ${kindLabel(kind).toLowerCase()} ${path}`, 'success')
      },
      onError: err => { setRefusal(err); setStep(null) },
    })
  }
  const doDelete = () => del.mutate(undefined, {
    onSuccess: () => { toast('Draft deleted', 'success'); navigate('/drafts') },
    onError: err => { setRefusal(err); setStep(null) },
  })

  if (versionError) {
    return (
      <div className="fade-in">
        <PageTitle>{path}</PageTitle>
        <PageSub><Link to="/drafts">All drafts</Link></PageSub>
        <ErrorDetail error={versionError} />
      </div>
    )
  }

  const fileList = Object.entries(files?.files || {}).map(([name, content]) => ({
    path: name, content,
  }))
  const busy = publish.isPending || del.isPending

  return (
    <div className="fade-in">
      <PageTitle>{path}</PageTitle>
      <PageSub>
        Draft by {owner} · updated {when(files?.updated) || '…'} ·{' '}
        <Link to="/drafts">All drafts</Link>
      </PageSub>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 16, alignItems: 'center' }}>
        <Btn onClick={() => setStep('publish')} disabled={busy || step === 'publish'}>Publish</Btn>
        <Btn variant="outline" onClick={() => setStep('delete')} disabled={busy || step === 'delete'}>Delete</Btn>
        {busy && <Spinner />}
      </div>

      {step === 'publish' && (
        <Card style={{ marginBottom: 16 }}>
          <p style={{ fontSize: 13, lineHeight: 1.6, marginBottom: 10 }}>
            Publishing replaces the {kindLabel(kind).toLowerCase()} everyone sees with this draft.
            The version it replaces is kept.
          </p>
          <label htmlFor="draft-note" style={{ display: 'block', fontSize: 12, fontWeight: 600, marginBottom: 4 }}>
            Note (optional)
          </label>
          <input id="draft-note" value={note} onChange={e => setNote(e.target.value)}
            placeholder="What changed and why"
            style={{
              width: '100%', maxWidth: 480, padding: '8px 10px', marginBottom: 12,
              border: '1px solid var(--border-strong)', borderRadius: 'var(--radius-sm)',
              background: 'var(--surface)', color: 'var(--text)', fontSize: 13, fontFamily: 'inherit',
            }} />
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <Btn onClick={doPublish} disabled={busy}>Publish for everyone</Btn>
            <Btn variant="outline" onClick={() => setStep(null)}>Cancel</Btn>
          </div>
        </Card>
      )}
      {step === 'delete' && (
        <Card style={{ marginBottom: 16 }}>
          <p style={{ fontSize: 13, lineHeight: 1.6, marginBottom: 12 }}>
            Delete this draft? Anything published stays as it is.
          </p>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <Btn variant="red" onClick={doDelete} disabled={busy}>Delete draft</Btn>
            <Btn variant="outline" onClick={() => setStep(null)}>Cancel</Btn>
          </div>
        </Card>
      )}

      {refusal && <div role="alert"><ErrorDetail error={refusal} /></div>}
      {published && (
        <Alert variant="info">
          Published.{' '}
          {isReport
            ? <Link to={reportPagePath(published.path, reportModels({ name: published.path }))}>Open the published report</Link>
            : 'The model is live once discovery picks it up.'}
        </Alert>
      )}

      <Tabs tabs={isReport ? ['Preview', 'Files'] : ['Files']} active={tab} onChange={setTab} />

      {tab === 'Preview' && isReport && (
        <>
          {previewError && <div role="alert"><ErrorDetail error={previewError} /></div>}
          {lastHtml.current
            ? <ReportFrame html={lastHtml.current} title={`Draft ${path}`} />
            : !previewError && <Spinner />}
        </>
      )}
      {tab === 'Files' && (
        <>
          {!isReport && (
            <p style={{ fontSize: 13, color: 'var(--muted)', marginBottom: 12 }}>
              A model draft has no page. It is the file below, and it becomes a model when published.
            </p>
          )}
          {fileList.length ? <CodeFiles files={fileList} /> : <Spinner />}
        </>
      )}
    </div>
  )
}
