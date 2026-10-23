import { useState } from 'react'
import { useConnectors, useCredentials, usePipelines, useSaveCredential, useTestConnection } from '../api'
import { stamp } from './TheLine'
import { Btn, Chip, ErrorDetail, Spinner } from './Shared'

// Where a credential is set, in the words the Sources page uses. The app
// never has a value to show: the API answers with these and nothing more.
function stateOf(row) {
  if (row.problem) return { label: 'Cannot be read', tone: 'warn', title: row.problem }
  if (!row.set) return { label: 'Missing', tone: 'warn', title: 'Set nowhere: not in the environment, .env or the store.' }
  return {
    environment: { label: 'Set · environment', title: "From the server's environment; it wins over anything saved here." },
    dotenv: { label: 'Set · .env', title: "From the project's .env file." },
    store: { label: 'Set here', title: "Saved in the project's encrypted store." },
    default: { label: 'Set · default', title: "Not set anywhere, so the file's own default is used." },
  }[row.source] || { label: 'Set' }
}

export function CredentialChip({ row }) {
  const s = stateOf(row)
  return <Chip tone={s.tone} title={s.title}>{s.label}</Chip>
}

// The rows a connection's file references, each with the fields it fills there.
function rowsFor(credentials, name) {
  return (credentials || [])
    .map(r => ({ ...r, fields: r.used_by.filter(u => u.kind === 'connection' && u.name === name).map(u => u.field) }))
    .filter(r => r.fields.length)
}

const INPUT = {
  flex: '1 1 220px', minWidth: 0, padding: '8px 10px',
  border: '1px solid var(--border-strong)', borderRadius: 'var(--radius-sm)',
  background: 'var(--surface)', color: 'var(--text)', fontSize: 13, fontFamily: 'inherit',
}

// Set or replace one value. The typed value lives only in this form's state
// and is cleared on save or cancel; nothing echoes it back.
function SetForm({ row, onDone }) {
  const save = useSaveCredential()
  const [value, setValue] = useState('')
  const [shown, setShown] = useState(false)
  const id = `cred-${row.name}`
  const submit = e => {
    e.preventDefault()
    save.mutate({ name: row.name, value }, {
      onSuccess: () => { setValue(''); onDone(true) },
    })
  }
  return (
    <form onSubmit={submit} style={{ flexBasis: '100%', marginTop: 6 }}>
      <label htmlFor={id} style={{ display: 'block', fontSize: 12, fontWeight: 600, marginBottom: 4 }}>
        Value for <code>{row.name}</code> (saved encrypted on the server; never shown again)
      </label>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
        <input id={id} type={shown ? 'text' : 'password'} value={value} autoComplete="off"
          spellCheck={false} onChange={e => setValue(e.target.value)} style={INPUT} autoFocus />
        <Btn size="sm" variant="outline" onClick={() => setShown(v => !v)} aria-pressed={shown}>
          {shown ? 'Hide' : 'Show'}
        </Btn>
        <Btn size="sm" type="submit" disabled={!value || save.isPending}>
          {save.isPending ? <Spinner size={12} /> : 'Save'}
        </Btn>
        <Btn size="sm" variant="outline" onClick={() => { setValue(''); onDone(false) }}>Cancel</Btn>
      </div>
      {save.error && <div style={{ marginTop: 8 }}><ErrorDetail error={save.error} /></div>}
    </form>
  )
}

function TestConnection({ name }) {
  const test = useTestConnection(name)
  const res = test.data
  return (
    <p className="src-quiet" style={{ marginTop: 8 }}>
      <Btn size="sm" variant="outline" onClick={() => test.mutate()} disabled={test.isPending}>
        {test.isPending ? <Spinner size={12} /> : 'Test connection'}
      </Btn>
      {res?.ok && <span>Connected · {res.tables} {res.tables === 1 ? 'table' : 'tables'}</span>}
      {res && !res.ok && <span>Could not connect · {res.reason}</span>}
      {test.error && <span>{test.error.message}</span>}
    </p>
  )
}

/**
 * The credentials a connection's file references (`${NAME}`), each with where
 * it is set. A signed-in admin can set, replace or remove one here; everyone
 * else sees the states. *connection* is the /api/connectors/{name} row.
 */
export default function Credentials({ connection }) {
  const { data, isLoading, error } = useCredentials()
  const save = useSaveCredential()
  const [editing, setEditing] = useState(null)
  const [saved, setSaved] = useState(false)
  if (isLoading) return <p className="src-quiet"><Spinner size={12} /> Reading its credentials…</p>
  if (error) return <ErrorDetail error={error} />
  const rows = rowsFor(data.credentials, connection.name)
  if (!rows.length) {
    return <p className="src-quiet">It needs no credentials: nothing in its file is a <code>{'${NAME}'}</code>.</p>
  }
  const can = data.can_change
  const missing = rows.filter(r => !r.set).map(r => r.name)
  return (
    <div>
      <ul className="src-files">
        {rows.map(r => (
          <li key={r.name}>
            <code>{r.name}</code>
            <CredentialChip row={r} />
            <span className="wb-meta">fills {r.fields.join(', ')}</span>
            {can && editing !== r.name && (
              <span style={{ display: 'inline-flex', gap: 6, marginLeft: 'auto' }}>
                <Btn size="sm" variant="outline" onClick={() => setEditing(r.name)}>
                  {r.stored ? 'Replace…' : 'Set…'}
                </Btn>
                {r.stored && (
                  <Btn size="sm" variant="outline" disabled={save.isPending}
                    onClick={() => save.mutate({ name: r.name, value: null })}>Remove</Btn>
                )}
              </span>
            )}
            {(r.problem || r.updated_at) && (
              <span className="src-files__by">
                {r.problem || <>Saved here{r.updated_by ? ` by ${r.updated_by}` : ''} · {stamp(r.updated_at)}
                  {r.stored && r.source !== 'store' && r.set ? ' · the value above wins' : ''}</>}
              </span>
            )}
            {editing === r.name && (
              <SetForm row={r} onDone={ok => { setEditing(null); if (ok) setSaved(true) }} />
            )}
          </li>
        ))}
      </ul>
      {save.error && <ErrorDetail error={save.error} />}
      {!can && missing.length > 0 && (
        <p className="src-quiet src-note">
          Set on the server: <code>tracebi secret set {missing[0]}</code>, or in its environment.
        </p>
      )}
      {can && saved && <TestConnection name={connection.name} />}
    </div>
  )
}

/**
 * The Transform tab's line for what the transform reads: each connection it
 * names in a `-- source:` line, with its credentials' state, so "why did the
 * snapshot stand in?" has an answer where the question arises.
 */
export function SourceCredentials({ pipeline }) {
  const { data: pipelines } = usePipelines()
  const { data: connectors } = useConnectors()
  const { data } = useCredentials()
  const transform = (pipelines || []).find(p => p.pipeline === pipeline)?.transform
  const read = (connectors || []).filter(c => c.read_by?.transforms?.some(t => t.name === transform))
  const items = read.flatMap(c => rowsFor(data?.credentials, c.name).map(r => ({ c, r })))
  if (!transform || !items.length) return null
  return (
    <p className="src-quiet" style={{ marginBottom: 10 }}>
      Reads {items.map(({ c, r }) => (
        <span key={`${c.name}-${r.name}`} style={{ display: 'inline-flex', gap: 6, alignItems: 'center' }}>
          <code>{c.name}</code> <CredentialChip row={r} />
        </span>
      ))}
    </p>
  )
}
