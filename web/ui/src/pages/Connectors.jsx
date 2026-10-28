import { Fragment, useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import {
  useConnectors, useConnectorTables, useCredentials, useGraph, useInputs, useMe,
  useRole, useSaveConnection, useTables, useTestConnection, useWarehouses,
} from '../api'
import { StorageLine, sourceKind, fmtBytes } from '../components/Storage'
import { useModelLabel } from '../components/Scope'
import CodeView from '../components/CodeView'
import Credentials from '../components/Credentials'
import ConnectionSheet from '../components/ConnectionForm'
import { StateChip } from '../components/Passport'
import ResourceTable, { DropMenu, NameCell, StatusPill, TypeChip } from '../components/ResourceTable'
import ResourcePage, { ActivityList, Details, Links } from '../components/ResourcePage'
import { DataFrame } from './Data'
import { stamp } from '../when'
import { count } from '../format'
import { movedWords, reachWords, statusWords } from '../words'
import {
  lineagePath, modelPath, sourcePath, sourceTablePath, sourcesPath, transformPath, warehousePath,
} from '../nav'
import {
  Btn, BtnLink, ErrorDetail, Spinner, Empty, SkeletonList, SkeletonCard, Time, useToast,
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
    : <p className="src-quiet">Nothing in this workspace reads it.</p>
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
export function useConnectionWrite() {
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

// What the source holds, read when its Tables tab opens: one row per table,
// its name the link to the table page, the transforms that read it and the
// warehouse tables that run wrote (the graph's edges, *nodes* by table name).
// A connection that is not reachable says so once, in its title. A connection
// file also says which tables agents may read, ticked in the first column.
function Tables({ name, declared, write, nodes = {}, byId = {} }) {
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
              <th scope="col">Read by</th>
              <th scope="col">Became</th>
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
                <td><NodeNames ids={(nodes[t.name]?.passport?.readers || []).filter(id => id.startsWith('transform:'))} byId={byId} /></td>
                <td><NodeNames ids={(nodes[t.name]?.passport?.readers || []).filter(id => id.startsWith('table:'))} byId={byId} code /></td>
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

/**
 * Everything about reaching a source, and nothing about what it holds: its
 * fields (the url, the variable), whether it connects here, the credentials
 * it names and where they are set, where its data lives; for a signed-in
 * admin Test, Edit… (the connection sheet, where Save password lives) and
 * Delete…; for anyone else, the command that does it on the server. A source
 * page's Settings tab, and the Setup sheet.
 */
function SetupBody({ c, onEdit, onDeleted }) {
  const write = useConnectionWrite()
  const [code, setCode] = useState(false)
  const declared = !!c.connection_type
  return (
    <>
      <p className="conn-sheet__lede">
        {declared ? <>Kept in <code>{c.declared_in}</code>.</> : 'Built in code: shown here, never edited.'}
      </p>
      <Section label="Connection"><Fields c={c} /><Reach name={c.name} /><Credentials connection={c} /></Section>
      <Section label="Where the data lives"><StorageLine storage={c.storage} /></Section>
      {declared && write.can && <ConnectionActions c={c} onEdit={onEdit} onDeleted={onDeleted} />}
      {!write.can && (
        <p className="src-quiet">
          {write.why}: <code>tracebi connect {c.name} --kind {c.connection_type || 'postgres'} --store secret</code>
        </p>
      )}
      <Btn size="sm" variant="outline" onClick={() => setCode(v => !v)}>{code ? 'Hide code' : '</> View code'}</Btn>
      {code && <div style={{ marginTop: 12 }}><CodeView kind="connectors" name={c.name} /></div>}
    </>
  )
}

/**
 * A source's Setup sheet: SetupBody over the page. The Data home's Setup on
 * an unreachable source opens it where the person is.
 */
export function SetupSheet({ c, onClose, onSaved, onDeleted }) {
  const [editing, setEditing] = useState(false)
  const panel = useRef(null)
  const close = useRef(onClose)
  close.current = onClose
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
        <SetupBody c={c} onEdit={() => setEditing(true)} onDeleted={() => { onClose(); onDeleted?.() }} />
      </div>
    </div>,
    document.body,
  )
}

// Graph nodes by id, as their names, each a link to its page: a transform
// that reads a table, a warehouse table a run wrote.
function NodeNames({ ids, byId, code = false }) {
  const items = ids.map(id => byId[id]).filter(Boolean).map(n => ({ key: n.id, to: n.open, label: n.label, code }))
  return <Links items={items} none={<span className="pass__none">—</span>} />
}

// Where a source comes from, when the graph has not said: its file, or its
// kind and the variable that sets it (the name, never the value).
function originOf(c) {
  const st = c.storage || {}
  if (st.kind === 'file' || st.kind === 'directory') return st.where
  return st.variable ? `${sourceKind(c)} · set by ${st.variable}` : st.where || sourceKind(c)
}

// Every read of a connection the certificates record: which transform's run
// read which of its tables, how, when, and whether a snapshot stood in.
function readsOf(name, warehouses) {
  return (warehouses?.warehouses || []).flatMap(w => (w.writers || []).flatMap(wr =>
    (wr.read || []).filter(r => r.connection === name).map(r => ({ ...r, transform: wr.transform }))))
}

// ── The list ─────────────────────────────────────────────────────────────────

/**
 * Sources (/data/sources): every connection and every data file under inputs/
 * in one list, the console's: Name · Type · Status · Tables (a file: its rows)
 * · Read by · Agents · Last activity · ⋯. The warehouse is not a source: it is
 * under Warehouse, and one line here says so.
 */
function SourceList() {
  const navigate = useNavigate()
  const { data, isLoading } = useConnectors()
  const { data: inputs } = useInputs()
  const { data: graph } = useGraph()
  const write = useConnectionWrite()
  const admin = useRole() === 'admin'
  const [sheet, setSheet] = useState(false)
  const byId = Object.fromEntries((graph?.nodes || []).map(n => [n.id, n]))
  const connectors = (data || []).filter(c => !c.warehouse)
  const files = (inputs?.files || []).filter(f => f.table)
  // A file's rows, read through the table API (each one cached for its page).
  const counted = useTables(files.map(f => ['inputs', f.path.replace(/^inputs\//, '')]))

  const rows = [
    ...connectors.map(c => {
      const node = byId[`source:${c.name}`]
      const tables = (graph?.nodes || []).filter(n => n.parent === `source:${c.name}`).length
      return {
        key: `source:${c.name}`, name: c.name, label: c.label || c.name, kind: 'connection', node, c,
        type: node?.chip || sourceKind(c), status: statusWords(node), n: node ? tables : null,
        readers: (node?.passport?.readers || []).filter(id => id.startsWith('transform:')),
        fallbackReaders: (c.read_by?.transforms || []).map(t => t.name),
        agents: node?.passport?.agents?.text || '', agentsOk: node?.passport?.agents?.state === 'ok',
        moved: node?.passport?.moved || null, to: sourcePath(c.name),
      }
    }),
    ...files.map((f, i) => {
      const name = f.path.replace(/^inputs\//, '')
      const node = byId[`file:${f.path}`]
      return {
        key: `file:${f.path}`, name, label: name, kind: 'file', node,
        type: node?.chip || name.split('.').pop().toUpperCase(),
        status: node ? statusWords(node) : f.read_by.length ? { text: 'Read', tone: 'ok' } : { text: 'Nobody reads it', tone: 'warn' },
        n: counted[i]?.data?.rows ?? null, readers: [], fallbackReaders: f.read_by,
        agents: '', agentsOk: false, moved: node?.passport?.moved || { how: 'changed', at: f.modified },
        to: sourceTablePath('inputs', name),
      }
    }),
  ]
  const readers = r => (r.readers.length
    ? <NodeNames ids={r.readers} byId={byId} />
    : <Links items={r.fallbackReaders.map(t => ({ key: t, to: transformPath(t), label: t }))} none={<span className="pass__none">—</span>} />)
  const add = write.can ? <Btn size="sm" onClick={() => setSheet(true)}>Add a connection</Btn> : null
  return (
    <DataFrame folder="sources" actions={<>
      {inputs?.exists && <BtnLink size="sm" to={sourcePath('inputs')}>The inputs/ folder</BtnLink>}
      {add}
    </>}>
      {isLoading ? <SkeletonList /> : !rows.length ? (
        <Empty title="No sources yet"
               body="A source is where the data comes from: a database connection, or files under inputs/. Add a connection (its secret goes in the workspace's store), or drop a file in inputs/."
               command={add ? undefined : 'tracebi connect crm --kind postgres --store secret'}
               action={add} />
      ) : (
        <ResourceTable
          label="Sources" placeholder="Find a source or file" rows={rows} defaultSort="name"
          search={r => `${r.name} ${r.label} ${r.type}`}
          filters={[
            { key: 'all', label: 'All' },
            { key: 'connections', label: 'Connections', test: r => r.kind === 'connection' },
            { key: 'files', label: 'Files', test: r => r.kind === 'file' },
            { key: 'unreachable', label: 'Unreachable', test: r => r.status.text === 'Unreachable' },
            { key: 'agents', label: 'Agents may read', test: r => r.agentsOk },
          ]}
          count={(n, of) => `${n === of ? '' : `${n} of `}${count(connectors.length, 'connection')} · ${count(files.length, 'file')}`}
          rowProps={r => ({ 'data-source': r.kind === 'connection' ? r.name : `inputs/${r.name}` })}
          columns={[
            { key: 'name', label: 'Name', sort: r => r.label.toLowerCase(),
              render: r => <NameCell to={r.to} label={r.label} id={r.kind === 'connection' ? r.name : null} /> },
            { key: 'type', label: 'Type', sort: r => r.type, render: r => <TypeChip>{r.type}</TypeChip> },
            { key: 'status', label: 'Status', sort: r => r.status.text, render: r => <StatusPill status={r.status} /> },
            { key: 'n', label: 'Tables', num: true, sort: r => r.n,
              render: r => (r.n == null ? <span className="pass__none">—</span> : r.kind === 'file' ? count(r.n, 'row') : r.n) },
            { key: 'readers', label: 'Read by', wrap: true, render: readers },
            { key: 'agents', label: 'Agents', render: r => <span className="wb-meta">{r.kind === 'file' ? '—' : r.agents || '—'}</span> },
            { key: 'moved', label: 'Last activity', sort: r => r.moved?.at || '', render: r => <span className="wb-meta">{movedWords(r.moved, r.node?.kind)}</span> },
          ]}
          menu={r => [
            { label: 'Open', to: r.to },
            r.kind === 'connection' && { label: 'Tables', to: `${r.to}?tab=tables` },
            r.kind === 'connection' && { label: 'Settings', to: `${r.to}?tab=settings` },
            r.node && { label: 'View lineage', to: lineagePath(r.node.id) },
            r.kind === 'connection' && admin && r.c.connection_type && { label: 'Edit connection…', to: `${r.to}?tab=settings` },
          ]}
        />
      )}
      {sheet && <ConnectionSheet editing={null} onClose={() => setSheet(false)}
                                 onSaved={name => { setSheet(false); navigate(`${sourcePath(name)}?tab=tables&saved=1`) }} />}
      <p className="wb-meta src-pointer">
        The warehouse a transform writes is under <Link to={warehousePath()}>Warehouse</Link>.
      </p>
    </DataFrame>
  )
}

// ── One source ───────────────────────────────────────────────────────────────

// Test, top right: open the connection, count its tables, close it; the
// answer in a toast. An admin's (it opens the server's connection).
function TestButton({ name }) {
  const test = useTestConnection(name)
  const toast = useToast()
  return (
    <Btn size="sm" variant="outline" disabled={test.isPending}
         onClick={() => test.mutate(undefined, {
           onSuccess: res => toast(res.ok ? `Connected · ${count(res.tables, 'table')}` : `Could not connect · ${res.reason}`,
             res.ok ? 'info' : 'error'),
           onError: e => toast(e.message || 'Could not test it', 'error'),
         })}>
      {test.isPending ? <Spinner size={12} /> : 'Test'}
    </Btn>
  )
}

// The Agents tab: what the gateway may read of the source, in the allowlist's
// words, and where to tick it.
function AgentsTab({ name, node, declared }) {
  const { data } = useConnectorTables(name)
  const ticked = (data?.tables || []).filter(t => t.agents).map(t => t.name)
  return (
    <div className="rsection">
      <p className="rsection__lede">
        <StateChip state={node?.passport?.agents} />{' '}
        An agent reads a source table only when it is ticked here, through the gateway; it never reads a file,
        and it never writes the warehouse.
      </p>
      {ticked.length > 0 && (
        <p className="wb-meta">Ticked: <Links items={ticked.map(t => ({ key: t, to: sourceTablePath(name, t), label: t, code: true }))} /></p>
      )}
      {declared
        ? <BtnLink size="sm" to="?tab=tables">Tick tables for agents</BtnLink>
        : <p className="src-quiet">A connector built in code has no allowlist to tick: declare it in connections/ (tracebi connect).</p>}
    </div>
  )
}

/**
 * One connection's page (/data/sources/<name>): the console's page. Overview
 * is the passport's rows and the connection's own facts; Tables what it holds
 * and which agents may read; Activity what the recorded runs read of it;
 * Settings how it is reached (an admin's concern once).
 */
function SourcePage({ c }) {
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()
  const { data: graph } = useGraph()
  const { data: warehouses } = useWarehouses()
  const write = useConnectionWrite()
  const admin = useRole() === 'admin'
  const [editing, setEditing] = useState(false)
  const byId = Object.fromEntries((graph?.nodes || []).map(n => [n.id, n]))
  const node = byId[`source:${c.name}`]
  const p = node?.passport
  const declared = !!c.connection_type
  const kids = (graph?.nodes || []).filter(n => n.parent === `source:${c.name}`)
  const tableNodes = Object.fromEntries(kids.map(n => [n.id.slice(`source_table:${c.name}.`.length), n]))
  const became = [...new Set(kids.flatMap(n => (n.passport?.readers || []).filter(id => id.startsWith('table:'))))]
  const reads = readsOf(c.name, warehouses).sort((a, b) => String(b.loaded_at).localeCompare(String(a.loaded_at)))
  const last = reads[0]
  const status = node ? statusWords(node) : { text: reachWords(null).short, tone: 'warn' }
  const reach = p?.reach?.connected === false ? reachWords(p.reach).text : null
  const origin = p?.origin || originOf(c)
  // The sheet's last step: a connection just saved opens on its Tables tab,
  // where the person ticks what agents may read.
  const justSaved = params.get('saved') === '1'

  const overview = () => (
    <Details items={[
      ['Type', sourceKind(c)],
      ['From', <code>{origin}</code>],
      ['Status', reach || status.text],
      ['Read by', <ReadBy c={c} />],
      ['Last read', last ? <><Time iso={last.loaded_at} /> · <TransformName name={last.transform} />{last.method && ` · ${last.method}`}{last.snapshot && ' · snapshot'}</> : null],
      ['Became', <NodeNames ids={became} byId={byId} code />],
      ['Last moved', p ? movedWords(p.moved, 'source') : null],
      ['Trust', <StateChip state={p?.trust || { state: 'none', text: 'Not a sink' }} />],
      ['Agents', <StateChip state={p?.agents} />],
      ['Declared in', c.declared_in ? <code>{c.declared_in}</code> : 'Built in code'],
    ]} />
  )
  return (
    <>
      <ResourcePage
        trail={[[sourcesPath(), 'Sources']]} here={c.label || c.name}
        title={c.label || c.name} id={c.name} type={node?.chip || sourceKind(c)} typeTitle={c.type}
        status={status}
        sub={<><code>{c.name}</code> · {origin}{node?.sub && <> · {node.sub}</>}</>}
        node={`source:${c.name}`}
        actions={<>
          {admin && declared && <TestButton name={c.name} />}
          <DropMenu variant="button" label="Setup" items={[
            declared && write.can && { label: 'Edit connection…', onClick: () => setEditing(true) },
            { label: 'Settings', onClick: () => setParams({ tab: 'settings' }) },
            { label: 'Tables agents may read', onClick: () => setParams({ tab: 'tables' }) },
          ]}>Setup <span aria-hidden="true">▾</span></DropMenu>
        </>}
        tabs={[
          { key: 'overview', label: 'Overview', render: overview },
          { key: 'tables', label: 'Tables', count: kids.length || undefined, render: () => (
            <div className="rsection">
              {justSaved && declared && <p className="src-quiet conn-saved" role="status">Saved. Tick the tables agents may read, then Save.</p>}
              <Tables name={c.name} declared={declared} write={write} nodes={tableNodes} byId={byId} />
            </div>
          ) },
          reads.length > 0 && { key: 'activity', label: 'Activity', render: () => (
            <ActivityList empty="No recorded run read it." items={reads.map((r, i) => ({
              key: `${r.transform}-${r.ref}-${i}`,
              status: r.snapshot ? { text: 'Snapshot read', tone: 'warn', title: `The committed file ${r.snapshot} stood in` } : { text: 'Read', tone: 'ok' },
              what: r.transform, to: transformPath(r.transform), sub: [r.ref, r.method].filter(Boolean).join(' · '), at: r.loaded_at,
            }))} />
          ) },
          { key: 'agents', label: 'Agents', render: () => <AgentsTab name={c.name} node={node} declared={declared} /> },
          { key: 'settings', label: 'Settings', render: () => (
            <div className="rsection rsection--setup">
              <SetupBody c={c} onEdit={() => setEditing(true)} onDeleted={() => navigate(sourcesPath(), { replace: true })} />
            </div>
          ) },
        ]}
      />
      {editing && <ConnectionSheet editing={c} onClose={() => setEditing(false)}
                                   onSaved={name => { setEditing(false); navigate(`${sourcePath(name)}?tab=tables&saved=1`) }} />}
    </>
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

/**
 * The workspace's inputs/ folder as a source page: the same Overview rows, then
 * its files as the Tables tab, data files first (the ones a transform reads
 * as a table), the scripts, notes and database files folded under them.
 * Nothing to set up.
 */
function InputsPage({ files }) {
  const data = files.filter(f => f.table)
  const other = files.filter(f => !f.table)
  const readers = [...new Set(files.flatMap(f => f.read_by))].sort()
  const newest = files.map(f => f.modified).filter(Boolean).sort().pop()
  const unread = data.filter(f => !f.read_by.length).length
  return (
    <ResourcePage
      trail={[[sourcesPath(), 'Sources']]} here="inputs/" code
      title="inputs/" type="Files"
      status={unread ? { text: `${unread} nobody reads`, tone: 'warn' } : { text: 'Read', tone: 'ok' }}
      sub={<>{count(files.length, 'file')} · {count(data.length, 'data file')} · read by {readers.length ? readers.join(', ') : 'nothing'}</>}
      tabs={[
        { key: 'overview', label: 'Overview', render: () => (
          <Details items={[
            ['From', <code>inputs/</code>],
            ['Read by', <Links items={readers.map(t => ({ key: t, to: transformPath(t), label: t }))} none="Nothing in this workspace reads it." />],
            ['Last moved', newest ? movedWords({ how: 'changed', at: newest }) : null],
            ['Trust', <StateChip state={{ state: 'none', text: 'Not a sink' }} />],
            ['Agents', <StateChip state={{ state: 'none', text: 'Files are never read by agents' }} />],
            ['Files', `${count(data.length, 'data file')} · ${count(other.length, 'other file')}`],
          ]} />
        ) },
        { key: 'tables', label: 'Tables', count: data.length, render: () => (
          <div className="rsection">
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
          </div>
        ) },
      ]}
    />
  )
}

/**
 * Sources: the list (/data/sources), one connection's page
 * (/data/sources/<name>) or the inputs/ folder's (/data/sources/inputs).
 */
export default function Connectors() {
  const { name } = useParams()
  const { data, isLoading } = useConnectors()
  const { data: inputs, isLoading: inputsLoading } = useInputs()
  if (!name) return <SourceList />
  const loading = <DataFrame trail={[[sourcesPath(), 'Sources']]} here={name}><SkeletonCard /></DataFrame>
  if (name === INPUTS) {
    if (inputsLoading) return loading
    return <InputsPage files={inputs?.files || []} />
  }
  if (isLoading) return loading
  const c = (data || []).find(x => x.name === name && !x.warehouse)
  if (!c) {
    return (
      <DataFrame trail={[[sourcesPath(), 'Sources']]} here={name}>
        <Empty title="No such source"
               body={<>There is no connection named <code>{name}</code>. <Link to={sourcesPath()}>Every source</Link></>} />
      </DataFrame>
    )
  }
  return <SourcePage key={c.name} c={c} />
}
