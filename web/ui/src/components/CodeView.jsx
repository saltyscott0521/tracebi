import { useState } from 'react'

import { useSource } from '../api'
import { Btn, ErrorDetail, Spinner } from './Shared'

// The code behind an object, read-only: one tab per file, line numbers, Copy.
// `data` is what the API's /source routes return ({files, hint}); the files are
// the ones discovery found, never a path typed in.

const name = f => f.label || f.path.split('/').pop()

export function CodeFiles({ files, hint, other }) {
  const [active, setActive] = useState(0)
  const [copied, setCopied] = useState(false)
  const file = files[Math.min(active, files.length - 1)]
  const lines = file ? file.content.replace(/\n$/, '').split('\n').length : 0

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(file.content)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch { /* clipboard blocked: the code is selectable */ }
  }

  return (
    <div className="fade-in">
      {hint && <div className="codeview__hint">{hint}</div>}
      {files.length > 1 && (
        <div className="codeview__tabs">
          {files.map((f, i) => (
            <Btn key={f.path} size="sm" variant={i === active ? undefined : 'outline'}
                 onClick={() => { setActive(i); setCopied(false) }}>{name(f)}</Btn>
          ))}
        </div>
      )}
      {file && (
        <>
          <div className="codeview__bar">
            <span className="codeview__path">{file.path}{file.truncated ? ' (first 256 KB)' : ''}</span>
            <Btn size="sm" variant="outline" onClick={copy}>{copied ? 'Copied' : 'Copy'}</Btn>
          </div>
          <div className="codeview" role="region" aria-label={`Code of ${file.path}`} tabIndex={0}>
            <pre className="codeview__gutter" aria-hidden="true">
              {Array.from({ length: lines }, (_, i) => i + 1).join('\n')}
            </pre>
            <pre className="codeview__code">{file.content}</pre>
          </div>
        </>
      )}
      {other?.length > 0 && (
        <div className="codeview__hint" style={{ marginTop: 10 }}>Also in the package: {other.join(', ')}</div>
      )}
    </div>
  )
}

/** The Code tab/view for an API object: `kind` is the route family ('models', 'pipelines', 'connectors'). */
export default function CodeView({ kind, name: of }) {
  const { data, isLoading, error } = useSource(kind, of)
  if (isLoading) return <div className="codeview__hint"><Spinner /> Loading code…</div>
  if (error) return <ErrorDetail error={error} />
  const files = data?.files || []
  if (!files.length) return <div className="codeview__hint">{data?.hint || 'No code to show.'}</div>
  return <CodeFiles files={files} hint={data.hint} />
}
