import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import {
  useConnectionTypes, useCredentials, useSaveConnection, useTestNewConnection, useUploadInput,
} from '../api'
import { MASK, buildUrl, parseUrl } from '../connectionUrl'
import { Btn, ErrorDetail, Segmented, Spinner } from './Shared'

// A whole-value ${NAME}: the person points a field at a variable instead of
// typing a value the server stores.
const REF = /^\$\{([A-Z_][A-Z0-9_]*)\}$/
const VAR = /^[A-Z_][A-Z0-9_]*$/
// The type cards' groups, in the order the sheet shows them.
const GROUPS = ['Databases', 'Warehouses', 'Files']

const secretName = (conn, field) => `TRACEBI_${(conn || 'NAME').toUpperCase()}_${field.toUpperCase()}`

// One plain field of the form, drawn from /api/connections/types: text, a
// number, a path, a choice, or a URL. A URL (which can carry a password) is
// masked, with Show beside it, and can instead name a variable; on an edit, a
// field the file keeps as ${NAME} reads empty and is kept unless something is
// typed.
function Field({ f, value, onChange, kept }) {
  const id = `conn-f-${f.name}`
  const [shown, setShown] = useState(false)
  const [variable, setVariable] = useState(false)
  const masked = f.kind === 'url'
  const bad = variable && value && !REF.test(value)
  const help = f.help && <p id={`${id}-help`} className="conn-field__help">{f.help}</p>
  if (f.kind === 'choice') {
    return (
      <div className="conn-field">
        <label htmlFor={id}>{f.label}{!f.required && <span className="conn-field__opt"> (optional)</span>}</label>
        <select id={id} value={value || ''} onChange={e => onChange(e.target.value)}
          aria-describedby={f.help ? `${id}-help` : undefined}>
          <option value="">{f.required ? 'Choose…' : 'Not set'}</option>
          {f.choices.map(c => <option key={c} value={c}>{c}</option>)}
        </select>
        {help}
      </div>
    )
  }
  return (
    <div className="conn-field">
      <label htmlFor={id}>{f.label}{!f.required && <span className="conn-field__opt"> (optional)</span>}</label>
      <div className="conn-field__row">
        <input
          id={id} value={value || ''} onChange={e => onChange(e.target.value)}
          type={masked && !shown && !variable ? 'password' : 'text'}
          inputMode={f.kind === 'number' ? 'numeric' : undefined}
          autoComplete="off" spellCheck={false}
          placeholder={variable ? '${TRACEBI_NAME}' : kept ? `Unchanged: ${kept}` : f.default || ''}
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
      {!variable && help}
      {variable && <p className="conn-field__help">The whole value, as <code>{'${NAME}'}</code>: set on the server, in its environment or <code>.env</code>.</p>}
    </div>
  )
}

// A secret (a password, a pasted service-account key): hidden, with Show,
// and **Save password**. On, the value goes to the workspace's encrypted store
// and the file names it; off, nothing is stored and the file names a
// variable the server sets in its environment or .env. On an edit an empty
// field keeps what is saved.
function Secret({ f, s, set, conn, kept }) {
  const id = `conn-f-${f.name}`
  const [shown, setShown] = useState(false)
  const what = f.name === 'password' ? 'password' : 'it in the store'
  const fallback = secretName(conn, f.name)
  const bad = !s.save && s.variable && !VAR.test(s.variable)
  return (
    <div className="conn-field conn-secret">
      <label htmlFor={id}>
        {s.save ? f.label : `${f.label}: variable name`}
        {!f.required && <span className="conn-field__opt"> (optional)</span>}
      </label>
      {s.save ? (
        <div className="conn-field__row">
          <input id={id} value={s.value} onChange={e => set({ value: e.target.value })}
            type={shown ? 'text' : 'password'} autoComplete="new-password" spellCheck={false}
            placeholder={kept ? `${MASK} unchanged` : ''} aria-describedby={`${id}-help`} />
          <Btn size="sm" variant="outline" onClick={() => setShown(v => !v)} aria-pressed={shown}>
            {shown ? 'Hide' : 'Show'}
          </Btn>
        </div>
      ) : (
        <div className="conn-field__row">
          <input id={id} value={s.variable} onChange={e => set({ variable: e.target.value.toUpperCase() })}
            placeholder={fallback} autoComplete="off" spellCheck={false}
            aria-describedby={`${id}-help`} aria-invalid={bad || undefined} />
        </div>
      )}
      <label className="conn-field__toggle">
        <input type="checkbox" checked={s.save} onChange={e => set({ save: e.target.checked })} />
        Save {what}
      </label>
      <p id={`${id}-help`} className="conn-field__help">
        {s.save
          ? <>{kept ? 'Left empty, the saved one is kept. ' : ''}Kept in the workspace&apos;s encrypted store; the file says <code>{`\${${kept || fallback}}`}</code>.</>
          : <>Nothing is saved: the file says <code>{`\${${s.variable || fallback}}`}</code>, and the server reads it from its environment or <code>.env</code>. Until it is set there, the connection&apos;s credentials read missing.</>}
      </p>
    </div>
  )
}

// The URL view of a connection's fields. It shows the password as ••• unless
// Show is on; typing a URL fills the fields, and a password in it moves to the
// password field and leaves the URL. Copy gives the URL with ${NAME} for the
// password, never the value. A URL the fields cannot say (another driver) is
// kept as one URL.
function UrlView({ type, fields, password, onFields, onPassword, raw, onRaw, refName }) {
  const [shown, setShown] = useState(false)
  const [text, setText] = useState(null)
  const [copied, setCopied] = useState(false)
  const pw = password.save ? password.value : ''
  // A saved password reads •••; one Save password leaves to the server, its ${NAME}.
  const said = !password.save ? `\${${refName}}` : pw ? (shown ? pw : MASK) : password.kept ? MASK : ''
  const derived = buildUrl(type, { ...fields, password: said })
  const shownText = text ?? raw ?? derived
  const change = v => {
    setText(v)
    const parsed = parseUrl(type, v)
    if (!parsed) { onRaw(v || null); return }
    onRaw(null)
    const { password: typed, ...rest } = parsed
    const ref = typed && REF.exec(typed)
    if (ref) onPassword({ save: false, variable: ref[1] })
    else if (typed && typed !== MASK) {
      onPassword({ save: true, value: typed })
      // The password leaves the URL shown: it is in the password field now,
      // and the URL is drawn from the fields again, masked.
      setShown(false)
      setText(null)
    }
    onFields(rest)
  }
  const copy = async () => {
    const url = raw || buildUrl(type, { ...fields, password: pw || password.kept || !password.save ? `\${${refName}}` : '' })
    try {
      await navigator.clipboard.writeText(url)
      setCopied(true)
      setTimeout(() => setCopied(false), 1600)
    } catch { /* no clipboard (an insecure origin): the URL is still selectable */ }
  }
  return (
    <div className="conn-field">
      <label htmlFor="conn-f-url">URL</label>
      {/* A textarea, so the whole URL reads at once, wrapped. */}
      <textarea id="conn-f-url" value={shownText} onChange={e => change(e.target.value.replace(/\s+/g, ''))}
        onBlur={() => setText(null)} autoComplete="off" spellCheck={false} rows={2}
        aria-describedby="conn-f-url-help" className="conn-url" />
      <div className="conn-field__row conn-url__actions">
        {!raw && pw && (
          <Btn size="sm" variant="outline" onClick={() => setShown(v => !v)} aria-pressed={shown}>
            {shown ? 'Hide' : 'Show'}
          </Btn>
        )}
        <Btn size="sm" variant="outline" onClick={copy}>{copied ? 'Copied' : 'Copy'}</Btn>
      </div>
      <p id="conn-f-url-help" className="conn-field__help">
        {raw
          ? <>The fields cannot say this URL (another driver, say), so it is saved as one URL; a password in it goes to the encrypted store.</>
          : <>The same connection as the fields: change either. A password typed here moves to the password field. Copy gives <code>{`\${${refName}}`}</code> in its place.</>}
      </p>
    </div>
  )
}

/**
 * Add a connection, or edit one (*editing*: its /api/connectors/{name} row).
 * A sheet over the page, in DBeaver's steps: Choose a database (the type
 * cards, grouped), then Connect: a SQL database as its fields or one URL, in
 * sync, a hidden password with Save password, Advanced folded, Test before
 * Save. A secret typed here is sent once: the server keeps it in the
 * workspace's encrypted store and the file holds ${NAME}. *onSaved(name)* opens
 * the saved connection on its tables.
 */
export default function ConnectionSheet({ editing, onClose, onSaved }) {
  const { data: types, isLoading } = useConnectionTypes()
  const { data: creds } = useCredentials()
  const save = useSaveConnection()
  const test = useTestNewConnection()
  const upload = useUploadInput()
  const [type, setType] = useState(editing?.connection_type || null)
  const [name, setName] = useState(editing?.name || '')
  const [label, setLabel] = useState(editing?.label || '')
  const [view, setView] = useState('fields')
  // A URL kept whole: one the fields cannot say, or the file's own ${NAME}.
  const [raw, setRaw] = useState(null)
  const [fields, setFields] = useState(() => {
    // An edit starts from the file's words; a ${NAME} reads empty (kept).
    const out = {}
    Object.entries(editing?.fields || {}).forEach(([k, v]) => { if (!REF.test(v)) out[k] = v })
    return out
  })
  // Each secret field's state: typed value, Save on or off, the variable.
  const [secrets, setSecrets] = useState(() => {
    const out = {}
    Object.entries(editing?.fields || {}).forEach(([k, v]) => {
      const ref = REF.exec(v)
      if (ref && k !== 'url') out[k] = { value: '', save: true, variable: ref[1], kept: ref[1] }
    })
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

  // On an edit, Save password starts as the file left it: on when the store
  // holds the value, off (naming the variable) when the server's environment
  // or .env is meant to.
  const stored = new Set((creds?.credentials || []).filter(c => c.source === 'store').map(c => c.name))
  const secretOf = f => {
    const s = secrets[f] || { value: '', save: true, variable: '' }
    return s.kept && s.touched === undefined ? { ...s, save: stored.has(s.kept) || !creds } : s
  }
  const setSecret = f => patch => setSecrets(all => ({ ...all, [f]: { ...secretOf(f), ...patch, touched: true } }))

  const spec = (types || []).find(t => t.type === type)
  const isUpload = type === 'upload'
  const urlForm = !!spec?.url_scheme
  const keptUrl = editing?.fields?.url && REF.test(editing.fields.url) ? editing.fields.url : null
  const kept = f => {
    const v = editing?.fields?.[f]
    return v && REF.test(v) ? v : null
  }
  // Which fields this type asks for now: a Snowflake password only with the
  // password sign-in, its key file only with key_pair, and then each one is
  // required.
  const auth = fields.authenticator || 'password'
  const asked = (spec?.fields || []).filter(f => type !== 'snowflake'
    || (f.name !== 'password' || auth === 'password')
    && (f.name !== 'private_key_path' || auth === 'key_pair'))
    .map(f => type === 'snowflake' && ['password', 'private_key_path'].includes(f.name) ? { ...f, required: true } : f)
  const said = f => {
    if (f.kind !== 'secret') return !!fields[f.name]
    const s = secretOf(f.name)
    return !!(s.value || s.kept || !s.save)
  }
  const structured = urlForm && type !== 'snowflake'
    && asked.some(f => f.kind !== 'secret' && fields[f.name])
  // A postgres or mysql URL saved whole: typed, or the file's own ${NAME}.
  const rawUrl = urlForm && type !== 'snowflake' && !structured && raw

  const body = () => {
    const out = {}
    asked.forEach(f => {
      if (f.kind === 'secret') {
        const s = secretOf(f.name)
        const v = s.save ? s.value : `\${${s.variable || secretName(name, f.name)}}`
        if (v || s.kept) out[f.name] = v
      } else if (fields[f.name] !== undefined) out[f.name] = fields[f.name]
    })
    if (rawUrl) return { name, type, label, fields: { url: rawUrl } }
    if (isUpload && file) out.file = `inputs/${file.name}`
    return { name, type, label, fields: out }
  }
  const submit = async e => {
    e.preventDefault()
    if (isUpload && file) await upload.mutateAsync({ file, replace: !!editing })
    save.mutate({ name: editing?.name, body: body() }, { onSuccess: res => onSaved(res?.name || name) })
  }
  const missing = rawUrl ? false : asked.some(f => f.required && !said(f) && !kept(f.name)
    && !(isUpload && f.name === 'file' && (file || fields.file))
    && !(urlForm && keptUrl && !structured))
  const busy = save.isPending || upload.isPending
  const refName = (() => {
    const s = secretOf('password')
    return s.save ? s.kept || secretName(name, 'password') : s.variable || secretName(name, 'password')
  })()

  const plain = asked.filter(f => !f.advanced && f.kind !== 'secret')
  const advanced = asked.filter(f => f.advanced)
  const fieldEl = f => f.kind === 'secret'
    ? <Secret key={f.name} f={f} s={secretOf(f.name)} set={setSecret(f.name)} conn={name} kept={kept(f.name) && secretOf(f.name).kept} />
    : isUpload && f.name === 'file' ? (
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
        onChange={v => { setRaw(null); setFields(s => ({ ...s, [f.name]: v })) }} />
    )
  // A generic SQL URL names its driver in its scheme: said beside it.
  const driver = type === 'sql' && /^([a-z0-9+]+):\/\//i.exec(fields.url || '')?.[1]
  const res = test.data
  const step = !spec ? 1 : 2

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
        {!editing && (
          <ol className="conn-steps" aria-label="Steps">
            <li aria-current={step === 1 ? 'step' : undefined}>Choose a database</li>
            <li aria-current={step === 2 ? 'step' : undefined}>Connect</li>
            <li>Tables</li>
          </ol>
        )}
        {isLoading ? <p className="src-quiet"><Spinner size={12} /> Reading the types…</p> : !spec ? (
          <>
            <p className="conn-sheet__lede">Where is the data? The app writes <code>connections/&lt;name&gt;.yaml</code>, as you would by hand.</p>
            {GROUPS.map(g => {
              const these = (types || []).filter(t => (t.group || 'Databases') === g)
              return these.length > 0 && (
                <section key={g} className="conn-group" aria-labelledby={`conn-g-${g}`}>
                  <h3 id={`conn-g-${g}`} className="conn-group__title">{g}</h3>
                  <ul className="conn-types">
                    {these.map(t => (
                      <li key={t.type}>
                        <button type="button" className="conn-type" data-type={t.type} onClick={() => setType(t.type)}>
                          <span className="conn-type__name">{t.label}</span>
                          <span className="conn-type__line">{t.line}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                </section>
              )
            })}
          </>
        ) : (
          <form onSubmit={submit} className="conn-form">
            <p className="conn-sheet__lede">
              {spec.label}{!editing && <> · <button type="button" className="conn-link" onClick={() => { setType(null); test.reset() }}>Change</button></>}
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
            {urlForm && (
              <Segmented panel="conn-view" label="Say the connection as" value={view} onChange={setView}
                options={[['fields', 'Fields'], ['url', 'URL']]} className="conn-view" />
            )}
            <div id="conn-view" role={urlForm ? 'tabpanel' : undefined} aria-labelledby={urlForm ? `conn-view-${view}` : undefined}
              className="conn-form__panel">
              {urlForm && view === 'url' ? (
                <UrlView type={type} fields={fields} password={secretOf('password')}
                  onFields={f => setFields(s => {
                    // The URL says every field it can: one it leaves out is cleared.
                    const next = { ...s }
                    asked.forEach(x => { if (x.kind !== 'secret') delete next[x.name] })
                    return { ...next, ...f }
                  })}
                  onPassword={setSecret('password')} raw={raw ?? (structured ? null : keptUrl)} onRaw={setRaw} refName={refName} />
              ) : (
                <>
                  {urlForm && keptUrl && !structured && (
                    <p className="conn-field__help conn-kept">This connection is one URL, kept as <code>{keptUrl}</code>. Fill the fields to say it as fields instead.</p>
                  )}
                  {plain.map(fieldEl)}
                  {driver && <p className="conn-field__help">Driver: <code>{driver}</code></p>}
                </>
              )}
              {asked.filter(f => f.kind === 'secret').map(fieldEl)}
              {advanced.length > 0 && !(urlForm && view === 'url') && (
                <details className="conn-advanced">
                  <summary>Advanced</summary>
                  <div className="conn-advanced__body">{advanced.map(fieldEl)}</div>
                </details>
              )}
            </div>
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
            {res?.ok && (
              <p className="conn-result" data-ok="true" role="status">
                Connected · {res.tables} {res.tables === 1 ? 'table' : 'tables'}{res.version && <> · {res.version}</>}
              </p>
            )}
            {res && !res.ok && <p className="conn-result" data-ok="false" role="status">Could not connect · {res.reason}</p>}
            <ErrorDetail error={test.error || upload.error || save.error} />
          </form>
        )}
      </div>
    </div>,
    document.body,
  )
}
