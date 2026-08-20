import { useState, useCallback, useRef } from 'react'

import { useVerifyFile } from '../api'
import {
  PageTitle, PageSub, Card, Btn, Spinner, ErrorDetail, useToast,
} from '../components/Shared'

// The offline file check, in the browser: pick a report .html and its
// .manifest.json receipt; the server rehashes the embedded data against the
// manifest and returns the verdict. No model, no warehouse — the sharpest
// thing TraceBi does, in the moment BI fails: a number in a shared file.

function classify(files) {
  // Sort dropped files into the html and its manifest by name/shape.
  const out = { html: null, manifest: null }
  for (const f of files) {
    const n = f.name.toLowerCase()
    if (n.endsWith('.json')) out.manifest = f
    else if (n.endsWith('.html') || n.endsWith('.htm')) out.html = f
  }
  return out
}

const read = (file) => new Promise((resolve, reject) => {
  const fr = new FileReader()
  fr.onload = () => resolve(fr.result)
  fr.onerror = () => reject(fr.error)
  fr.readAsText(file)
})

const VERDICT = {
  file_intact: { label: 'FILE INTACT', tone: 'ok',
    line: 'The numbers in this file are exactly what was fingerprinted at build.' },
  file_altered: { label: 'FILE ALTERED', tone: 'bad',
    line: 'A value in this file was changed after it was built — it is not the number that was recorded.' },
  file_nothing_embedded: { label: 'NOTHING EMBEDDED', tone: 'mut',
    line: 'This file carries no embedded data, so there was nothing to check.' },
  refused_snapshot: { label: 'REFUSED', tone: 'mut',
    line: 'This is a review snapshot, not a published report — snapshots carry no receipt and cannot be verified.' },
}

const TONE = {
  ok:  { color: 'var(--accent-text)', wash: 'var(--blue-lt)',  border: 'var(--blue-br)' },
  bad: { color: 'var(--red-text)',    wash: 'var(--red-lt)',   border: 'var(--red-br)' },
  mut: { color: 'var(--muted)',       wash: 'var(--surface-2)', border: 'var(--border)' },
}

function FileChip({ file, kind }) {
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 7, padding: '5px 11px',
      borderRadius: 7, border: '1px solid var(--border)', background: 'var(--surface-2)',
      fontSize: 12.5, fontFamily: "'IBM Plex Mono', monospace",
    }}>
      <span style={{ color: 'var(--accent-text)', fontWeight: 600 }}>{kind}</span>
      {file.name}
    </span>
  )
}

function Result({ result }) {
  const v = VERDICT[result.verdict] || { label: result.verdict, tone: 'mut', line: result.verdict_detail }
  const tone = TONE[v.tone]
  const figures = result.figures || []
  return (
    <Card style={{ padding: 0, overflow: 'hidden', marginTop: 20 }}>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 14, padding: '20px 22px',
        borderBottom: '1px solid var(--border)', background: tone.wash,
      }}>
        <div style={{
          width: 40, height: 40, borderRadius: 9, flex: 'none',
          border: `2px solid ${tone.color}`, color: tone.color,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <svg width="21" height="21" viewBox="0 0 20 20" fill="none">
            <path
              d={v.tone === 'bad' ? 'M5 5l10 10M15 5L5 15' : 'M4 10.5l4 4 8-9'}
              stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </div>
        <div>
          <div style={{
            fontFamily: "'IBM Plex Mono', monospace", fontWeight: 600, fontSize: 18,
            color: tone.color, letterSpacing: '.02em',
          }}>{v.label}</div>
          <div style={{ color: 'var(--muted)', fontSize: 13, marginTop: 3 }}>{v.line}</div>
        </div>
      </div>

      {figures.length > 0 && (
        <div style={{ padding: '6px 22px 14px' }}>
          {figures.map((f, i) => {
            const ok = f.status === 'figure_matches'
            return (
              <div key={f.figure || i} style={{
                display: 'flex', alignItems: 'baseline', gap: 11, padding: '9px 0',
                borderBottom: i < figures.length - 1 ? '1px solid var(--border)' : 'none',
                fontSize: 13.5,
              }}>
                <span style={{
                  fontFamily: "'IBM Plex Mono', monospace", fontWeight: 600,
                  color: ok ? 'var(--accent-text)' : 'var(--red-text)',
                }}>{ok ? '✓' : '✗'}</span>
                <span style={{ fontFamily: "'IBM Plex Mono', monospace" }}>{f.figure}</span>
                <span style={{ marginLeft: 'auto', color: 'var(--muted)', fontSize: 12 }}>{f.detail}</span>
              </div>
            )
          })}
        </div>
      )}

      <div style={{
        padding: '13px 22px', borderTop: '1px solid var(--border)',
        color: 'var(--muted)', fontSize: 12.5, fontFamily: "'IBM Plex Mono', monospace",
      }}>{result.verdict_detail}</div>
    </Card>
  )
}

export default function Verify() {
  const [files, setFiles] = useState({ html: null, manifest: null })
  const [dragging, setDragging] = useState(false)
  const [result, setResult] = useState(null)
  const inputRef = useRef(null)
  const toast = useToast()
  const { mutate, isPending, error, reset } = useVerifyFile()

  const take = useCallback((list) => {
    const picked = classify(Array.from(list))
    setFiles((prev) => ({ html: picked.html || prev.html, manifest: picked.manifest || prev.manifest }))
    setResult(null)
    reset()
  }, [reset])

  const onDrop = useCallback((e) => {
    e.preventDefault(); setDragging(false)
    if (e.dataTransfer?.files?.length) take(e.dataTransfer.files)
  }, [take])

  const runVerify = useCallback(async () => {
    try {
      const [html, manifestText] = await Promise.all([read(files.html), read(files.manifest)])
      mutate({ html, manifest: manifestText }, {
        onSuccess: (data) => setResult(data),
        onError: (err) => toast(`Verification failed: ${err.message}`, 'error'),
      })
    } catch {
      toast('Could not read one of the files.', 'error')
    }
  }, [files, mutate, toast])

  const ready = files.html && files.manifest

  return (
    <>
      <PageTitle>Verify a file</PageTitle>
      <PageSub>
        Drop a report <code>.html</code> and its <code>.manifest.json</code> receipt.
        It re-hashes the data embedded in the file against the manifest — no model,
        no warehouse, no account. The data never leaves this machine.
      </PageSub>

      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        onClick={() => inputRef.current?.click()}
        style={{
          border: `2px dashed ${dragging ? 'var(--accent-text)' : 'var(--border-hl)'}`,
          borderRadius: 14, background: dragging ? 'var(--blue-lt)' : 'var(--card)',
          padding: '38px 24px', textAlign: 'center', cursor: 'pointer',
          transition: 'border-color .15s, background .15s', maxWidth: 640,
        }}
      >
        <svg width="38" height="38" viewBox="0 0 24 24" fill="none"
             style={{ color: 'var(--muted)', marginBottom: 10 }}>
          <path d="M12 16V4m0 0l-4 4m4-4l4 4M4 17v2a1 1 0 001 1h14a1 1 0 001-1v-2"
                stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        <div style={{ fontWeight: 600, fontSize: 16 }}>Drop a report and its receipt</div>
        <div style={{ color: 'var(--muted)', fontSize: 13, marginTop: 6 }}>
          or <span style={{ color: 'var(--accent-text)', textDecoration: 'underline' }}>choose files</span> —
          the <code>.html</code> and its <code>.manifest.json</code>
        </div>
        <input ref={inputRef} type="file" accept=".html,.htm,.json" multiple
               style={{ display: 'none' }}
               onChange={(e) => { take(e.target.files); e.target.value = '' }} />
      </div>

      {(files.html || files.manifest) && (
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginTop: 14, alignItems: 'center' }}>
          {files.html && <FileChip file={files.html} kind="html" />}
          {files.manifest && <FileChip file={files.manifest} kind="manifest" />}
          {!files.html && <span style={{ color: 'var(--amber-text)', fontSize: 12.5 }}>add the report <code>.html</code></span>}
          {!files.manifest && <span style={{ color: 'var(--amber-text)', fontSize: 12.5 }}>add its <code>.manifest.json</code></span>}
          <Btn onClick={runVerify} disabled={!ready || isPending} style={{ marginLeft: 'auto' }}>
            {isPending ? <><Spinner size={13} /> Verifying…</> : '✓ Verify offline'}
          </Btn>
        </div>
      )}

      {error && <div style={{ marginTop: 16 }}><ErrorDetail error={error} /></div>}
      {result && <Result result={result} />}
    </>
  )
}
