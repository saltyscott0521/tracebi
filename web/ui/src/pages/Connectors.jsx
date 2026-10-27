import { Fragment, useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  useConnectors, useConnectorTables, useCredentials, useGraph, useInputs, useMe,
  useSaveConnection, useTestConnection, useWarehouses,
} from '../api'
import { StorageLine, sourceKind, fmtBytes } from '../components/Storage'
import { useModelLabel } from '../components/Scope'
import CodeView from '../components/CodeView'
import Credentials from '../components/Credentials'
import ConnectionSheet from '../components/ConnectionForm'
import { PassportRows, StateChip } from '../components/Passport'
import { stamp } from '../when'
import { count } from '../format'
import { movedWords, reachWords } from '../words'
import { modelPath, sourcePath, sourceTablePath, sourcesPath, transformPath, warehousePath } from '../nav'
import {
  Card, CardTitle, Badge, Btn, ErrorDetail, Spinner,
  Empty, ListItem, SplitLayout, SearchInput, SkeletonList, SkeletonCard,
} from '../components/Shared'

// The inputs/ folder's entry in the list: files, not a connection.
const INPUTS = 'inputs'

function Section({ label, children, sectionRef }) {
  return <div className="src-section" ref={sectionRef}><div className="src-label">{label}</div>{children}</div>
}

/**
 * A transform's name, wherever it appears: always a link to its page, which
 * every file in transforms/ has, whether or not a pipeline runs it.
 */
export function TransformName({ name }) {
  return <Link to={transformPath(name)}><code>{name}</code></Link>
}

// Who reads a source: the transforms that name its tables (in a `-- source:`
// line or a load_source call), the pipelines whose steps take it as their
// source (one line per pipeline, its steps named), and the models that read
// it directly. Read from the files, so a source nothing names says so. A
// pipeline's steps run no transform file (a Python medallion runner), so the
// pipeline is named plainly, its Python a chip, as the Models folder does.
function ReadBy({ c }) {
  const labelOf = useModelLabel()
  const rb = c.read_by || { transforms: [], layers: [], models: c.used_by || [] }
  const pipelines = {}
  rb.layers.forEach(l => { (pipelines[l.pipeline] ||= []).push(l.layer) })
  const lines = [
    ...rb.transforms.map(t => (
      <li key={`t-${t.name}`}>
        The transform <TransformName name={t.name} /> ({t.tables.join(', ')})
      </li>
    )),
    ...Object.entries(pipelines).map(([p, steps]) => (
      <li key={`p-${p}`}>
        The pipeline <code>{p}</code> <Badge>Python</Badge>: {count(steps.length, 'step')} ({steps.map((s, i) => <Fragment key={s}>{i > 0 && ', '}<code>{s}</code></Fragment>)})
      </li>
    )),
    ...rb.models.map(m => (
      <li key={`m-${m}`}>The model <Link to={modelPath(m)}>{labelOf(m)}</Link>, which reads its tables</li>
    )),
  ]
  return lines.length
    ? <ul className="src-readby">{lines}</ul>
    : <p className="src-quiet">Nothing in this project reads it.</p>
}

// A table's row count as the table API counts it: exact, the catalog's
// estimate (~), or blank where neither is cheap.
function rowsText(t) {
  if (t.rows == null) return ''
  return `${t.rows_exact === false ? '~' : ''}${Number(t.rows).toLocaleString('en-US')}`
}

// The connection's state here: reachable, or which variable it is waiting
// for (the credentials under it are where that is set).
function Reach({ name }) {
  const { data, isLoading } = useConnectorTables(name)
  if (isLoading) return <p className="src-quiet"><Spinner size={12} /> Connecting…</p>
  if (!data || data.connected) return null
  return <p className="src-quiet src-reach" data-connected="false">{reachWords(data).text}</p>
}

// Whether this person may add, change or delete connections here: a signed-in
// admin (the server's answer, can_change), and if not, why, in one sentence
// that names the command that does it on the server.
function useConnectionWrite() {
  const { data } = useCredentials()
  const { data: me } = useMe()
  const can = !!data?.can_change
  const why = can ? null
    : !me || me.sign_in === 'none'
      ? 'This server has no sign-in, so connections are set up on it'
      : 'Only a signed-in admin adds or changes connections'
  return { can, why }
}

// The tables agents may read: a tick per table, "All tables" above them. A
// connection file's `agents:` says it; saving writes it there. Without a file
// (a connector built in code) there is nothing to tick.
function useAllowlist(name, data) {
  const save = useSaveConnection()
  const initial = data?.agent_tables || []
  const [all, setAll] = useState(null)
  const [picked, setPicked] = useState(null)
  const isAll = all ?? initial[0] === '*'
  const chosen = picked ?? new Set((data?.tables || []).filter(t => t.agents).map(t => t.name))
  const dirty = all !== null || picked !== null
  const toggle = t => {
    const next = new Set(chosen)
    next.has(t) ? next.delete(t) : next.add(t)
    setPicked(next)
  }
  const commit = () => save.mutate(
    { name, body: { agents: isAll ? { tables: '*' } : { tables: [...chosen] } } },
    { onSuccess: () => { setAll(null); setPicked(null) } })
  return { isAll, chosen, dirty, toggle, setAll, commit, save, reset: () => { setAll(null); setPicked(null) } }
}

// What the source holds, read when its detail opens: one row per table, its
// name the link to the table page. A connection that is not reachable says so
// once, in its Connection section above. A connection file also says which
// tables agents may read, ticked in the last column.
function Tables({ name, declared, write }) {
  const { data, isLoading, error } = useConnectorTables(name)
  const allow = useAllowlist(name, data)
  if (isLoading) return <p className="src-quiet"><Spinner size={12} /> Reading what it holds…</p>
  if (error) return <ErrorDetail error={error} />
  if (!data.connected) return <p className="src-quiet">Its tables are listed once it connects.</p>
  if (!data.tables) return <p className="src-quiet">{data.reason}</p>
  // TraceBi's own tables (the state store's) are never listed as data.
  const n = data.hidden_framework_tables || 0
  const hidden = n > 0 && <p className="src-quiet" title="TraceBi's own tables (tracebi_*, alembic_version) are not shown as data.">{count(n, 'framework table')} hidden</p>
  if (!data.tables.length) return <><p className="src-quiet">It holds no tables.</p>{hidden}</>
  const locked = !write.can
  const tick = locked ? `${write.why}.` : undefined
  return (
    <>
      {declared && (
        <div className="conn-allow">
          <label className="conn-allow__all" title={tick}>
            <input type="checkbox" checked={allow.isAll} disabled={locked}
              onChange={e => allow.setAll(e.target.checked)} />
            Agents may read all its tables, and any added later
          </label>
          {allow.dirty && (
            <span className="conn-allow__save">
              <Btn size="sm" onClick={allow.commit} disabled={allow.save.isPending}>
                {allow.save.isPending ? <Spinner size={12} /> : 'Save'}
              </Btn>
              <Btn size="sm" variant="outline" onClick={allow.reset}>Cancel</Btn>
            </span>
          )}
        </div>
      )}
      <div className="whlist">
        <table className="tb-list">
          <thead>
            <tr>
              {/* First, so it stays in view on a phone, where the list scrolls sideways. */}
              {declared && <th scope="col" className="conn-allow__col">Agents may read</th>}
              <th scope="col">Table</th>
              <th scope="col" className="num">Rows</th>
              <th scope="col" className="num">Columns</th>
            </tr>
          </thead>
          <tbody>
            {data.tables.map(t => (
              <tr key={t.name} data-table={t.name}>
                {declared && (
                  <td className="conn-allow__col">
                    <input type="checkbox" aria-label={`Agents may read ${t.name}`} title={tick}
                      checked={allow.isAll || allow.chosen.has(t.name)} disabled={locked || allow.isAll}
                      onChange={() => allow.toggle(t.name)} />
                  </td>
                )}
                <td><Link to={sourceTablePath(name, t.name)}><code>{t.name}</code></Link></td>
                <td className="num" title={t.rows != null && t.rows_exact === false ? "The catalog's estimate" : undefined}>{rowsText(t)}</td>
                <td className="num">{t.columns.length}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {hidden}
      {declared && (
        <p className="src-quiet src-note">
          {allow.isAll || allow.chosen.size ? 'An agent reads only the ticked tables, through the gateway.'
            : 'Agents read none of its tables until one is ticked.'}
        </p>
      )}
      <ErrorDetail error={allow.save.error} />
    </>
  )
}

// What a signed-in admin does to a connection file: test it, edit it, delete
// it. Deleting asks once, and the server refuses while anything reads it,
// naming what does.
function ConnectionActions({ c, onEdit, onDeleted }) {
  const test = useTestConnection(c.name)
  const del = useSaveConnection()
  const [asking, setAsking] = useState(false)
  const res = test.data
  return (
    <div className="conn-actions">
      <div className="conn-actions__row">
        <Btn size="sm" variant="outline" onClick={() => test.mutate()} disabled={test.isPending}>
          {test.isPending ? <Spinner size={12} /> : 'Test'}
        </Btn>
        <Btn size="sm" variant="outline" onClick={onEdit}>Edit</Btn>
        {asking ? (
          <>
            <Btn size="sm" variant="red" disabled={del.isPending}
              onClick={() => del.mutate({ name: c.name, method: 'DELETE' }, { onSuccess: onDeleted })}>
              Delete {c.declared_in}
            </Btn>
            <Btn size="sm" variant="outline" onClick={() => { setAsking(false); del.reset() }}>Keep it</Btn>
          </>
        ) : <Btn size="sm" variant="outline" onClick={() => setAsking(true)}>Delete…</Btn>}
      </div>
      {res?.ok && <p className="src-quiet" role="status">Connected · {res.tables} {res.tables === 1 ? 'table' : 'tables'}</p>}
      {res && !res.ok && <p className="src-quiet" role="status">Could not connect · {res.reason}</p>}
      <ErrorDetail error={test.error || del.error} />
    </div>
  )
}

// The file's fields as it says them: a ${NAME} stays a name (where it is set
// is under Connection), and a literal is never a secret.
function Fields({ c }) {
  const entries = Object.entries(c.fields || {})
  if (!entries.length) return null
  return (
    <dl className="conn-fields">
      {entries.map(([k, v]) => <Fragment key={k}><dt>{k}</dt><dd><code>{v}</code></dd></Fragment>)}
    </dl>
  )
}

// A source's name for people, large, with its identifier small beside it.
function SourceName({ c }) {
  return c.label
    ? <>{c.label} <code className="src-id">{c.name}</code></>
    : <code className="src-id src-id--only">{c.name}</code>
}

// Where a source comes from, when the graph has not said: its file, or its
// kind and the variable that sets it (the name, never the value).
function originOf(c) {
  const st = c.storage || {}
  if (st.kind === 'file' || st.kind === 'directory') return st.where
  return st.variable ? `${sourceKind(c)} · set by ${st.variable}` : st.where || sourceKind(c)
}

// A source's passport rows: the graph's node when it is served, else the
// same facts read from the listings the page already has.
function SourceRows({ c, node }) {
  const { data: inputs } = useInputs()
  const { data: warehouses } = useWarehouses()
  const { data: tables } = useConnectorTables(c.name)
  const p = node?.passport
  const file = (inputs?.files || []).find(f => f.path === c.storage?.where)
  const snapshot = (warehouses?.warehouses || []).some(w => (w.writers || []).some(wr =>
    wr.read.some(r => r.connection === c.name && r.snapshot)))
  const listed = tables?.connected ? tables.tables || [] : null
  const ticked = listed ? listed.filter(t => t.agents).length : (c.agent_tables || []).length
  const agents = p?.agents || (listed
    ? { state: ticked ? 'ok' : 'none', text: `${ticked} of ${count(listed.length, 'table')}` }
    : { state: ticked ? 'ok' : 'none', text: ticked ? count(ticked, 'table') : 'No tables ticked' })
  return (
    <PassportRows rows={[
      ['From', <code>{p?.origin || originOf(c)}</code>],
      ['Read by', <ReadBy c={c} />],
      ['Last moved', p ? movedWords(p.moved, 'source') : file ? movedWords({ how: 'changed', at: file.modified }) : null],
      ['Trust', <StateChip state={p?.trust || (snapshot
        ? { state: 'warn', text: 'Read from snapshot' } : { state: 'none', text: 'Not a sink' })} />],
      ['Agents', <StateChip state={agents} />],
    ]} />
  )
}

/**
 * A source's Setup sheet: everything about reaching it, and nothing about
 * what it holds. Its fields (the url, the variable), whether it connects
 * here, the credentials it names and where they are set, where its data
 * lives; for a signed-in admin Test, Edit… (the connection sheet, where Save
 * password lives) and Delete…; for anyone else, the command that does it on
 * the server. The source's page and the map's passport open it.
 */
export function SetupSheet({ c, onClose, onSaved, onDeleted }) {
  const write = useConnectionWrite()
  const [editing, setEditing] = useState(false)
  const [code, setCode] = useState(false)
  const panel = useRef(null)
  const close = useRef(onClose)
  close.current = onClose
  const declared = !!c.connection_type
  useEffect(() => {
    if (editing) return undefined
    const onKey = e => { if (e.key === 'Escape') close.current() }
    window.addEventListener('keydown', onKey)
    panel.current?.focus()
    return () => window.removeEventListener('keydown', onKey)
  }, [editing])
  if (editing) {
    return <ConnectionSheet editing={c} onClose={onClose} onSaved={name => (onSaved ? onSaved(name) : onClose())} />
  }
  return createPortal(
    <div className="conn-sheet">
      <div className="conn-sheet__scrim" onClick={onClose} aria-hidden="true" />
      <div className="conn-sheet__panel fade-in" role="dialog" aria-modal="true" aria-labelledby="conn-setup-title"
        tabIndex={-1} ref={panel}>
        <header className="conn-sheet__head">
          <h2 id="conn-setup-title">Setup · {c.label || c.name}</h2>
          <button type="button" className="dbx-close" onClick={onClose} aria-label="Close">×</button>
        </header>
        <p className="conn-sheet__lede">
          {declared ? <>Kept in <code>{c.declared_in}</code>.</> : 'Built in code: shown here, never edited.'}
        </p>
        <Section label="Connection"><Fields c={c} /><Reach name={c.name} /><Credentials connection={c} /></Section>
        <Section label="Where the data lives"><StorageLine storage={c.storage} /></Section>
        {declared && write.can && (
          <ConnectionActions c={c} onEdit={() => setEditing(true)} onDeleted={() => { onClose(); onDeleted?.() }} />
        )}
        {!write.can && (
          <p className="src-quiet">
            {write.why}: <code>tracebi connect {c.name} --kind {c.connection_type || 'postgres'} --store secret</code>
          </p>
        )}
        <Btn size="sm" variant="outline" onClick={() => setCode(v => !v)}>{code ? 'Hide code' : '</> View code'}</Btn>
        {code && <div style={{ marginTop: 12 }}><CodeView kind="connectors" name={c.name} /></div>}
      </div>
    </div>,
    document.body,
  )
}

// One source, as the map's passport says it: the rows first, then what it
// holds (each table, and which agents may read), then Setup… for how it is
// reached, which is an admin's concern once and not what the page is for.
function ConnectorDetail({ c, write, onSetup, justSaved }) {
  const { data: graph } = useGraph()
  // The sheet's last step: a connection just saved opens on its tables, where
  // the person ticks what agents may read.
  const tables = useRef(null)
  useEffect(() => {
    if (justSaved) tables.current?.scrollIntoView({ block: 'start', behavior: 'smooth' })
  }, [justSaved])
  if (!c) return (
    <Card>
      <Empty message="Select a source to see what it holds." />
    </Card>
  )
  const declared = !!c.connection_type
  const node = (graph?.nodes || []).find(n => n.id === `source:${c.name}`)
  return (
    <Card className="fade-in">
      <CardTitle action={<Btn size="sm" variant="outline" onClick={onSetup}>Setup…</Btn>}><SourceName c={c} /></CardTitle>
      <div style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap' }}>
        <Badge variant="gray" title={c.type}>{sourceKind(c)}</Badge>
      </div>
      <SourceRows c={c} node={node} />
      <Section label="Tables" sectionRef={tables}>
        {justSaved && declared && (
          <p className="src-quiet conn-saved" role="status">Saved. Tick the tables agents may read, then Save.</p>
        )}
        <Tables name={c.name} declared={declared} write={write} />
      </Section>
    </Card>
  )
}

// One file under inputs/ as a row: its name (a data file's opens its table
// page), which transforms name it, its size and when it changed.
function InputRow({ f }) {
  const name = f.path.replace(/^inputs\//, '')
  return (
    <tr data-file={name}>
      <td>{f.table ? <Link to={sourceTablePath(INPUTS, name)}><code>{name}</code></Link> : <code>{name}</code>}</td>
      <td className="src-files__by">
        {f.read_by.length
          ? f.read_by.map((t, i) => <span key={t}>{i > 0 && ', '}<TransformName name={t} /></span>)
          : 'No transform names it'}
      </td>
      <td className="num">{fmtBytes(f.size)}</td>
      <td>{stamp(f.modified)}</td>
    </tr>
  )
}

function InputTable({ files }) {
  return (
    <div className="whlist">
      <table className="tb-list">
        <thead>
          <tr><th scope="col">File</th><th scope="col">Read by</th><th scope="col" className="num">Size</th><th scope="col">Changed</th></tr>
        </thead>
        <tbody>{files.map(f => <InputRow key={f.path} f={f} />)}</tbody>
      </table>
    </div>
  )
}

// The project's inputs/ folder, as a source: the same rows, then its files as
// the tables, data files first (the ones a transform reads as a table), the
// scripts, notes and database files folded under them. Nothing to set up.
function InputsDetail({ files }) {
  const data = files.filter(f => f.table)
  const other = files.filter(f => !f.table)
  const readers = [...new Set(files.flatMap(f => f.read_by))].sort()
  const newest = files.map(f => f.modified).filter(Boolean).sort().pop()
  return (
    <Card className="fade-in">
      <CardTitle><code className="src-id src-id--only">inputs/</code></CardTitle>
      <div style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap' }}>
        <Badge variant="gray">Files</Badge>
      </div>
      <PassportRows rows={[
        ['From', <code>inputs/</code>],
        ['Read by', readers.length
          ? readers.map((t, i) => <span key={t}>{i > 0 && ', '}<TransformName name={t} /></span>)
          : 'Nothing in this project reads it.'],
        ['Last moved', newest ? movedWords({ how: 'changed', at: newest }) : null],
        ['Trust', <StateChip state={{ state: 'none', text: 'Not a sink' }} />],
        ['Agents', <StateChip state={{ state: 'none', text: 'Files are never read by agents' }} />],
      ]} />
      <Section label="Tables">
        {files.length === 0 ? <p className="src-quiet">The folder is empty.</p> : (
          <>
            {data.length > 0
              ? <InputTable files={data} />
              : <p className="src-quiet">No file here reads as a table (CSV, Parquet or JSON).</p>}
            {other.length > 0 && (
              <details className="wb-details src-other">
                <summary>{count(other.length, 'other file')}</summary>
                <InputTable files={other} />
              </details>
            )}
          </>
        )}
        <p className="src-quiet src-note">
          Read by is found by reading each transform for a path into inputs/. A path
          built from a variable is not seen.
        </p>
      </Section>
    </Card>
  )
}

/**
 * Where the data comes from (/data/sources): every connection and the
 * inputs/ folder, a list with the open one beside it. The open one is the
 * address's (/data/sources/<name>, /data/sources/inputs); with none named the
 * first opens. A warehouse is not a source: it is under Warehouse, and one
 * line here says so.
 */
export default function Connectors() {
  const { name: asked } = useParams()
  const navigate = useNavigate()
  const { data, isLoading } = useConnectors()
  const { data: inputs } = useInputs()
  const labelOf = useModelLabel()
  const [query, setQuery] = useState('')
  const write = useConnectionWrite()
  // The Add sheet: null closed, {} adding. A source's Setup sheet is open
  // while *setup* names it.
  const [sheet, setSheet] = useState(null)
  const [setup, setSetup] = useState(null)
  // The connection the sheet just saved, opened on its tables.
  const [justSaved, setJustSaved] = useState(null)

  const connectors = (data || []).filter(c => !c.warehouse)
  const files = inputs?.files || []
  const showInputs = !!inputs?.exists
  const q = query.toLowerCase()
  const filtered = connectors.filter(c =>
    [c.name, c.label || '', sourceKind(c)].some(x => x.toLowerCase().includes(q)))
  const inputsShown = showInputs && ('inputs files'.includes(q) || files.some(f => f.path.toLowerCase().includes(q)))
  // Open on the first source rather than a blank "select one" pane.
  const current = asked === INPUTS && showInputs ? INPUTS
    : (connectors.find(c => c.name === asked) || filtered[0])?.name || (inputsShown ? INPUTS : null)
  const select = name => navigate(sourcePath(name))

  // Who reads it, each reader said as what it is: a transform, a pipeline, a model.
  const readers = c => {
    const rb = c.read_by || { transforms: [], layers: [], models: c.used_by || [] }
    const parts = [
      ...rb.transforms.map(t => `transform ${t.name}`),
      ...[...new Set(rb.layers.map(l => l.pipeline))].map(p => `pipeline ${p}`),
      ...rb.models.map(m => `model ${labelOf(m)}`),
    ]
    return parts.length ? <span className="src-li__by">Read by {parts.join(', ')}</span> : null
  }

  const add = write.can
    ? <Btn onClick={() => setSheet({})}>Add a connection</Btn>
    : null
  const saved = name => { setSheet(null); setJustSaved(name); select(name) }
  return (
    <>
      {add && (connectors.length > 0 || showInputs) && <div className="conn-bar">{add}</div>}
      {!isLoading && connectors.length === 0 && !showInputs ? (
        <Empty title="No sources yet"
               body="A source is where the data comes from: a database connection, or files under inputs/. Add a connection (its secret goes in the project's store), or drop a file in inputs/."
               command={add ? undefined : 'tracebi connect crm --kind postgres --store secret'}
               action={add} />
      ) : (
        <SplitLayout
          left={
            isLoading ? <SkeletonList /> : (
              <>
                <SearchInput value={query} onChange={setQuery} placeholder="Search sources…" />
                {filtered.length === 0 && !inputsShown
                  ? <Empty message="No source matches." />
                  : (
                    <>
                      {filtered.map(c => (
                        <div key={c.name} data-source={c.name}>
                          <ListItem
                            selected={current === c.name}
                            onClick={() => select(c.name)}
                            name={<SourceName c={c} />}
                            sub={sourceKind(c)}
                            meta={readers(c)}
                          />
                        </div>
                      ))}
                      {inputsShown && (
                        <div data-source={INPUTS}>
                          <ListItem
                            selected={current === INPUTS}
                            onClick={() => select(INPUTS)}
                            name={<code className="src-id src-id--only">inputs/</code>}
                            sub={`Files · ${count(files.length, 'file')}`}
                          />
                        </div>
                      )}
                    </>
                  )
                }
              </>
            )
          }
          right={isLoading ? <SkeletonCard />
            : current === INPUTS ? <InputsDetail files={files} />
            : <ConnectorDetail key={current} c={connectors.find(c => c.name === current)} write={write}
                justSaved={justSaved === current} onSetup={() => setSetup(current)} />}
        />
      )}
      {sheet && <ConnectionSheet editing={null} onClose={() => setSheet(null)} onSaved={saved} />}
      {setup && connectors.some(c => c.name === setup) && (
        <SetupSheet c={connectors.find(c => c.name === setup)} onClose={() => setSetup(null)}
                    onSaved={name => { setSetup(null); saved(name) }}
                    onDeleted={() => navigate(sourcesPath(), { replace: true })} />
      )}
      <p className="wb-meta src-pointer">
        The warehouse a transform writes is under <Link to={warehousePath()}>Warehouse</Link>.
      </p>
    </>
  )
}
