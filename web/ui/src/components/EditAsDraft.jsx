import { useNavigate } from 'react-router-dom'

import { reportPath, useMe, useStartDraft } from '../api'
import { Btn, useToast } from './Shared'

// "Edit as a draft": start my own working copy of a published report or model
// (or open the one I already have) and go to its page. Nothing a draft holds
// changes what anyone sees until it is published.
//
// kind is 'reports' or 'models'; path is the report's path or the model's name.
// A viewer cannot start a draft, so they are not offered the button. A refusal
// (a Python model, a report with a report.py) is the server's own sentence: it
// names why and where to edit it instead.

export default function EditAsDraft({ kind, path, label = 'Edit as a draft', bare = false, className = 'cmd', role, size }) {
  const { data: me } = useMe()
  const start = useStartDraft()
  const navigate = useNavigate()
  const toast = useToast()

  if (me?.role !== 'analyst' && me?.role !== 'admin') return null

  const go = () => start.mutate({ kind, path }, {
    onSuccess: d => navigate(`/drafts/${encodeURIComponent(d.owner)}/${d.kind}/${reportPath(d.path)}`),
    onError: err => toast(err.message, 'error'),
  })

  // In a toolbar it is a flat command like its neighbours (or an item in its menu).
  if (bare) {
    return (
      <button type="button" className={className} role={role} aria-label={label} onClick={go} disabled={start.isPending}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
             strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M4 20h4L19 9l-4-4L4 16z" /></svg>
        <span className="cmd__lab">{start.isPending ? 'Starting…' : label}</span>
      </button>
    )
  }
  // `size="sm"`: among a page's other actions, top right (a resource page's).
  return (
    <Btn variant="outline" size={size} onClick={go} disabled={start.isPending} style={size ? undefined : { minHeight: 44 }}>
      {start.isPending ? 'Starting…' : label}
    </Btn>
  )
}
