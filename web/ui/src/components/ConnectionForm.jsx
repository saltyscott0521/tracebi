import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { useConnectionTypes, useSaveConnection, useTestNewConnection, useUploadInput } from '../api'
import { Btn, ErrorDetail, Spinner } from './Shared'

// A whole-value ${NAME}: the person points a field at a variable instead of
// typing a value the server stores.
const REF = /^\$\{[A-Z_][A-Z0-9_]*\}$/
const MASKED = ['secret', 'url']

// One field of the form, drawn from /api/connections/types. A secret (and a
// URL, which can carry one) is masked, with Show beside it, and can instead
// name a variable; on an edit, a field the file keeps as ${NAME} reads empty
// and is kept unless something is typed.
function Field({ f, value, onChange, kept }) {
  const id = `conn-f-${f.name}`
  const [shown, setShown] = useState(false)
  const [variable, setVariable] = useState(false)
  const masked = MASKED.includes(f.kind)
  const bad = variable && value && !REF.test(value)
  return (
    <div className="conn-field">
      <label htmlFor={id}>{f.label}{!f.required && <span className="conn-field__opt"> (optional)</span>}</label>
      <div className="conn-field__row">
        <input
          id={id} value={value || ''} onChange={e => onChange(e.target.value)}
          type={masked && !shown && !variable ? 'password' : 'text'}
          autoComplete="off" spellCheck={false}
          placeholder={variable ? '${TRACEBI_NAME}' : kept ? `Unchanged: ${kept}` : ''}
          aria-describedby={f.help ? `${id}-help` : undefined}
          aria-invalid={bad || undefined}
        />
        {masked && !variable && (
          <Btn size="sm" variant="outline" onClick={() => setShown(v => !v)} aria-pressed={shown}>
            {shown ? 'Hide' : 'Show'}
          </Btn>
        )}
      </div>
      {masked && (
        <label className="conn-field__toggle">
          <input type="checkbox" checked={variable} onChange={e => { setVariable(e.target.checked); onChange('') }} />
          Read it from an environment variable instead
        </label>
      )}
      {f.help && !variable && <p id={`${id}-help`} className="conn-field__help">{f.help}</p>}
      {variable && <p className="conn-field__help">The whole value, as <code>{'${NAME}'}</code>: set on the server, in its environment or <code>.env</code>.</p>}
    </div>
  )
}

/**
 * Add a connection, or edit one (*editing*: its /api/connectors/{name} row).
 * A sheet over the page: pick a type (cards), fill the form drawn from the
 * type's fields, Test it before saving, Save. A secret typed here is sent
 * once: the server keeps it in the project's encrypted store and the file
 * holds ${NAME}. *onSaved(name)* opens the saved connection.
 */
export default function ConnectionSheet({ editing, onClose, onSaved }) {
  const { data: types, isLoading } = useConnectionTypes()
  const save = useSaveConnection()
  const test = useTestNewConnection()
  const upload = useUploadInput()
  const [type, setType] = useState(editing?.connection_type || null)
  const [name, setName] = useState(editing?.name || '')
  const [label, setLabel] = useState(editing?.label || '')
  const [fields, setFields] = useState(() => {
    // An edit starts from the file's words; a ${NAME} reads empty (kept).
    const out = {}
    Object.entries(editing?.fields || {}).forEach(([k, v]) => { if (!REF.test(v)) out[k] = v })
    return out
  })
  const [file, setFile] = useState(null)
  const panel = useRef(null)
  const close = useRef(onClose)
  close.current = onClose

  // Focus moves into the sheet once, when it opens; Escape closes it.
  useEffect(() => {
    const onKey = e => { if (e.key === 'Escape') close.current() }
    window.addEventListener('keydown', onKey)
    panel.current?.focus()
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const spec = (types || []).find(t => t.type === type)
  const isUpload = type === 'upload'
  const kept = f => {
    const v = editing?.fields?.[f]
    return v && REF.test(v) ? v : null
  }
  const body = () => ({
    name, type, label,
    fields: isUpload && file ? { ...fields, file: `inputs/${file.name}` } : fields,
  })
  const submit = async e => {
    e.preventDefault()
    if (isUpload && file) await upload.mutateAsync({ file, replace: !!editing })
    save.mutate({ name: editing?.name, body: body() }, { onSuccess: res => onSaved(res?.name || name) })
  }
  const missing = (spec?.fields || []).some(f => f.required && !fields[f.name] && !kept(f.name)
    && !(isUpload && f.name === 'file' && (file || fields.file)))
  const busy = save.isPending || upload.isPending

  // On document.body: a transformed ancestor (the page's fade-in) would
  // otherwise pin this fixed sheet to the content column, not the window.
  return createPortal(
    <div className="conn-sheet">
      <div className="conn-sheet__scrim" onClick={onClose} aria-hidden="true" />
      <div className="conn-sheet__panel fade-in" role="dialog" aria-modal="true" aria-labelledby="conn-sheet-title"
        tabIndex={-1} ref={panel}>
        <header className="conn-sheet__head">
          <h2 id="conn-sheet-title">{editing ? `Edit ${editing.label || editing.name}` : 'Add a connection'}</h2>
          <button type="button" className="dbx-close" onClick={onClose} aria-label="Close">×</button>
        </header>
        {isLoading ? <p className="src-quiet"><Spinner size={12} /> Reading the types…</p> : !spec ? (
          <>
            <p className="conn-sheet__lede">Where is the data? The app writes <code>connections/&lt;name&gt;.yaml</code>, as you would by hand.</p>
            <ul className="conn-types">
              {(types || []).map(t => (
                <li key={t.type}>
                  <button type="button" className="conn-type" data-type={t.type} onClick={() => setType(t.type)}>
                    <span className="conn-type__name">{t.label}</span>
                    <span className="conn-type__line">{t.line}</span>
                  </button>
                </li>
              ))}
            </ul>
          </>
        ) : (
          <form onSubmit={submit} className="conn-form">
            <p className="conn-sheet__lede">
              {spec.label}{!editing && <> · <button type="button" className="conn-link" onClick={() => setType(null)}>Change</button></>}
            </p>
            {!editing && (
              <div className="conn-field">
                <label htmlFor="conn-f-name">Name</label>
                <input id="conn-f-name" value={name} onChange={e => setName(e.target.value)} autoComplete="off"
                  spellCheck={false} pattern="[A-Za-z_][A-Za-z0-9_]*" required placeholder="crm"
                  aria-describedby="conn-f-name-help" />
                <p id="conn-f-name-help" className="conn-field__help">Letters, digits and underscores. A transform reads its tables as <code>{name || 'name'}.&lt;table&gt;</code>.</p>
              </div>
            )}
            <div className="conn-field">
              <label htmlFor="conn-f-label">Label<span className="conn-field__opt"> (optional)</span></label>
              <input id="conn-f-label" value={label} onChange={e => setLabel(e.target.value)} placeholder="CRM (Postgres)" />
            </div>
            {spec.fields.map(f => isUpload && f.name === 'file' ? (
              <div className="conn-field" key={f.name}>
                <label htmlFor="conn-f-upload">File</label>
                <input id="conn-f-upload" type="file" accept=".csv,.parquet" onChange={e => setFile(e.target.files?.[0] || null)} />
                <p className="conn-field__help">
                  {editing ? <>Now <code>{editing.fields?.file}</code>. Choose a file to replace it. </> : null}
                  A .csv or .parquet file, up to 50 MB. It is saved under <code>inputs/</code> and read as one table named after the file.
                </p>
              </div>
            ) : (
              <Field key={f.name} f={f} value={fields[f.name]} kept={kept(f.name)}
                onChange={v => setFields(s => ({ ...s, [f.name]: v }))} />
            ))}
            <div className="conn-form__foot">
              {!isUpload && (
                <Btn variant="outline" onClick={() => test.mutate(body())} disabled={test.isPending || missing}>
                  {test.isPending ? <Spinner size={12} /> : 'Test'}
                </Btn>
              )}
              <Btn type="submit" disabled={busy || missing || (!editing && !name)}>
                {busy ? <Spinner size={12} /> : editing ? 'Save changes' : 'Save'}
              </Btn>
              <Btn variant="outline" onClick={onClose}>Cancel</Btn>
            </div>
            {test.data?.ok && <p className="src-quiet" role="status">Connected · {test.data.tables} {test.data.tables === 1 ? 'table' : 'tables'}</p>}
            {test.data && !test.data.ok && <p className="src-quiet" role="status">Could not connect · {test.data.reason}</p>}
            <ErrorDetail error={test.error || upload.error || save.error} />
          </form>
        )}
      </div>
    </div>,
    document.body,
  )
}
