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

export default function EditAsDraft({ kind, path, label = 'Edit as a draft' }) {
  const { data: me } = useMe()
  const start = useStartDraft()
  const navigate = useNavigate()
  const toast = useToast()

  if (me?.role !== 'analyst' && me?.role !== 'admin') return null

  const go = () => start.mutate({ kind, path }, {
    onSuccess: d => navigate(`/drafts/${encodeURIComponent(d.owner)}/${d.kind}/${reportPath(d.path)}`),
    onError: err => toast(err.message, 'error'),
  })

  return (
    <Btn variant="outline" onClick={go} disabled={start.isPending} style={{ minHeight: 44 }}>
      {start.isPending ? 'Starting…' : label}
    </Btn>
  )
}
