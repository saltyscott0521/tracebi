import { Fragment, useEffect, useState } from 'react'
import { Link, Navigate, useLocation, useParams, useSearchParams } from 'react-router-dom'

import {
  useConnectors, useCredentials, useGraph, useInputs, useModel, useTable, useTableProfile, useWarehouses,
} from '../api'
import DataGrid, { ExportTo, cellText, copyText, cutSql } from '../components/DataGrid'
import { CredentialChip } from '../components/Credentials'
import { useModelLabel } from '../components/Scope'
import { StateChip } from '../components/Passport'
import ResourcePage, { ActivityList, Details, Links } from '../components/ResourcePage'
import { checksWords, movedWords, reachWords, statusWords } from '../words'
import { TypeGlyph } from '../components/DataBrowser'
import { buildModelGraph } from '../components/modelGraph'
import { TransformName } from './Connectors'
import { DataFrame } from './Data'
import { count } from '../format'
import {
  modelPath, reportPagePath, sourcePath, sourceTablePath, sourcesPath, transformPath, warehousePath, warehouseTablePath,
} from '../nav'
import {
  Btn, BtnLink, Chip, Empty, ErrorDetail, PageSub, PageTitle, SkeletonCard, SkeletonList, Time, useToast,
} from '../components/Shared'

// One table's page, wherever it lives: a warehouse's (/data/warehouse/<table>),
// a connection's (/data/sources/<connection>/<table>) or a file under inputs/
// (/data/sources/inputs/<path>), in the console's page shape: Overview (what
// it is, who wrote it, who reads it), Data (its rows), Columns (its profile,
// and From: where a SQL transform's column came from), Used by, Lineage,
// Activity. The tab is in the address (?tab=; the older ?view= still opens
// its tab), and so is the grid's cut, so a sorted, filtered page of rows can
// be linked.

// The older ?view= of this page, as the tab it is now.
const VIEW_TAB = { data: 'data', columns: 'columns', used: 'used' }

function rowsText(t) {
  if (t.rows == null) return 'Rows not counted'
  return `${t.rows_exact ? '' : '~'}${count(t.rows, 'row')}`
}

// What the run that wrote it read from outside the warehouse: each connection
// table (its own page) and whether a committed snapshot stood in for it.
function ReadOnRun({ items }) {
  return items.map((src, i) => {
    const dot = src.ref.indexOf('.')
    const ref = dot > 0
      ? <Link to={sourceTablePath(src.ref.slice(0, dot), src.ref.slice(dot + 1))}><code>{src.ref}</code></Link>
      : <code>{src.ref}</code>
    return (
      <Fragment key={src.ref}>
        {i > 0 && ', '}{ref}{' '}
        {src.snapshot
          ? <span title={`The committed file ${src.snapshot} stood in for the connection on that run.`}>(snapshot)</span>
          : <span title={src.fingerprint ? `fingerprint ${src.fingerprint}` : undefined}>(live)</span>}
      </Fragment>
    )
  })
}

// What a source table became, as its passport says it: where it comes from,
// each transform that read it (as what, how, when its last run read it, and
// whether a committed snapshot stood in), and the warehouse tables that run
// wrote. A source table is read by transforms; the models read what they wrote.
// With no recorded run, the transforms whose text names it.
export function sourceReads({ source, table, warehouses, connectors, inputs }) {
  const reads = []
  for (const w of warehouses?.warehouses || []) {
    for (const wr of w.writers || []) {
      const fileRead = source === 'inputs'
        && (inputs?.files || []).some(f => f.path === `inputs/${table}` && f.read_by.includes(wr.transform))
      const r = fileRead ? { ref: `inputs/${table}` } : wr.read.find(x => x.connection === source && x.table === table)
      if (r) reads.push({ transform: wr.transform, ref: r.ref, method: r.method, at: r.loaded_at, snapshot: r.snapshot, became: wr.tables })
    }
  }
  if (reads.length) return reads
  const named = source === 'inputs'
    ? (inputs?.files || []).find(f => f.path === `inputs/${table}`)?.read_by || []
    : ((connectors || []).find(c => c.name === source)?.read_by?.transforms || []).filter(t => t.tables.includes(table)).map(t => t.name)
  return named.map(transform => ({ transform, ref: source === 'inputs' ? `inputs/${table}` : `${source}.${table}`, named: true, became: [] }))
}

// The sink contract's words, folded under the header: what the transform
// said about the table it wrote (never "verified"), and its note. Its title
// is the chip's words (checksWords), with what opening it shows.
function ContractFold({ c }) {
  if (!c || c.status === 'no_contract') return null
  return (
    <details className="wb-details tpage__contract">
      <summary>{checksWords(c).text}: the checks and the transform's note</summary>
      <p className="wb-meta">
        {c.status === 'satisfied'
          ? <>The sink satisfied its contract: {count(c.checks || 0, 'check')} in <code>{c.file}</code>
              {c.checked_at && <>, checked <Time iso={c.checked_at} /></>}.</>
          : <>This table changed after the checks in <code>{c.file}</code> last passed
              {c.checked_at && <> (<Time iso={c.checked_at} />)</>}. Re-run its transform to check it again.</>}
      </p>
      {c.note && <p className="tpage__note">{c.note}</p>}
    </details>
  )
}

// The source is not reachable from here: say which variable, how it is set
// now, and where its Connection section is (the credential lives there).
function NotConnected({ source, answer }) {
  const { data } = useCredentials()
  const row = (data?.credentials || []).find(r => r.name === answer.variable)
  return (
    <div className="tpage__off" data-connected="false">
      <p className="src-quiet">
        {reachWords(answer).text}
        {row && <CredentialChip row={row} />}
      </p>
      {source !== 'inputs' && (
        <BtnLink size="sm" to={sourcePath(source)}>
          {data?.can_change && row && !row.set ? 'Set it on its connection' : 'Open its connection'}
        </BtnLink>
      )}
    </div>
  )
}

// ── Columns: the profile as a list ───────────────────────────────────────────

const share = s => (s ? `${(s * 100).toFixed(s < 0.001 ? 2 : 1)}%` : '0%')

function rangeOf(name, p) {
  const col = { name, type: p.type }
  if (p.min != null || p.max != null) {
    return `${cellText(p.min, col).text} to ${cellText(p.max, col).text}`
  }
  if (p.top?.length) return p.top.map(x => `${x.value} (${x.count.toLocaleString('en-US')})`).join(', ')
  return '—'
}

// One base column a SQL transform's column came from, as the certificate
// names it (tracebi/lineage_sql.py), linked to the page of the table it lives
// in: <connection>.<table>.<column> a source table, inputs/<path>.<column> a
// file, <table>.<column> another warehouse table.
function BaseLink({ base, connections }) {
  const cut = base.lastIndexOf('.')
  const where = base.slice(0, cut)
  const conn = connections.find(c => where.startsWith(`${c}.`))
  const to = conn ? sourceTablePath(conn, where.slice(conn.length + 1))
    : where.startsWith('inputs/') ? sourceTablePath('inputs', where.slice('inputs/'.length))
    : cut > 0 && !where.includes('/') && !where.includes('.') ? warehouseTablePath(where)
    : null
  return to ? <Link to={to}><code>{base}</code></Link> : <code>{base}</code>
}

// Where a column comes from: its bases, "computed from no column", or the
// reason the parse could not follow it.
function ColumnFrom({ entry, connections }) {
  if (!entry) return <span className="pass__none">—</span>
  if (entry.from === null) return <span className="tpage__unresolved">{entry.reason}</span>
  if (!entry.from.length) return <span className="tpage__unresolved">computed from no column</span>
  return (
    <span className="tpage__from" title={entry.via?.length ? `through ${entry.via.join(', ')}` : undefined}>
      from {entry.from.map((b, i) => <Fragment key={b}>{i > 0 && ', '}<BaseLink base={b} connections={connections} /></Fragment>)}
    </span>
  )
}

function ColumnsView({ source, table, from }) {
  const { data, isLoading, error } = useTableProfile(source, table)
  const { data: connectors } = useConnectors()
  if (isLoading) return <SkeletonList />
  if (error) return <ErrorDetail error={error} />
  if (data.connected === false) return <p className="src-quiet">{data.reason}</p>
  if (data.note) return <p className="src-quiet">{data.note}</p>
  // Longest first, so a connection named like another's prefix matches whole.
  const connections = (connectors || []).filter(c => !c.warehouse).map(c => c.name)
    .sort((a, b) => b.length - a.length)
  return (
    <div className="tpage__scroll">
      <table className="tb-list tpage__profile">
        <thead>
          <tr><th>Column</th><th>Type</th><th>Nulls</th><th>Distinct</th><th>Range or top values</th>{from && <th>From</th>}</tr>
        </thead>
        <tbody>
          {Object.entries(data.columns).map(([name, p]) => (
            <tr key={name}>
              <td><span className="tpage__col"><TypeGlyph type={p.type} /><code>{name}</code></span></td>
              <td className="tpage__type">{p.type}</td>
              <td className="grid__num" title={`${p.nulls.toLocaleString('en-US')} of ${count(data.rows, 'row')}`}>{share(p.null_share)}</td>
              <td className="grid__num">{p.distinct.toLocaleString('en-US')}</td>
              <td data-tb-data className="tpage__range">{rangeOf(name, p)}</td>
              {from && <td className="tpage__fromcell"><ColumnFrom entry={from[name]} connections={connections} /></td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ── Used by: models, the measures that name a column, reports ────────────────

const words = { sum: 'sum', avg: 'average', mean: 'average', count: 'count', min: 'minimum', max: 'maximum' }

// How a measure names a column, in a few words: "sum of fair_value".
function definition(m) {
  if (m.kind === 'simple') return `${words[m.agg] || m.agg} of ${m.column}`
  if (m.kind === 'expression') return `${words[m.agg] || m.agg} of ${m.expr}`
  return m.kind
}

// The measures of *fact* whose own definition names one of *columns*.
function measuresOver(model, fact, columns) {
  const runnable = new Set(fact?.runnable_measures || [])
  return (model.measures || []).filter(m => runnable.has(m.name) && (
    (m.kind === 'simple' && columns.has(m.column)) ||
    (m.kind === 'expression' && (String(m.expr).match(/[A-Za-z_][A-Za-z0-9_]*/g) || []).some(w => columns.has(w)))))
}

function ModelUse({ model, source, table, columns }) {
  const labelOf = useModelLabel()
  const { data, isLoading } = useModel(model)
  if (isLoading || !data) return <li className="tpage__use"><SkeletonCard /></li>
  const mine = (data.tables || []).filter(t => t.connector === source && t.source === table).map(t => t.name)
  const names = new Set(columns.map(c => c.name))
  const facts = (data.facts || []).filter(f => mine.includes(f.table) || mine.includes(f.name))
  const dims = (data.dimensions || []).filter(d => mine.includes(d.table) || mine.includes(d.name))
  const measures = facts.flatMap(f => measuresOver(data, f, names))
  return (
    <li className="tpage__use">
      <p className="tpage__use-head">
        <Link to={modelPath(model)}>{labelOf(model)}</Link>
        <span className="wb-meta">
          {facts.length ? ' reads it as a fact' : dims.length ? ' reads it as a dimension' : ' reads it'}
          {mine.some(n => n !== table) && <> (as <code>{mine.join(', ')}</code>)</>}
        </span>
      </p>
      {dims.map(d => (
        <p key={d.name} className="wb-meta">
          Dimension <code>{d.name}</code>: key <code>{d.key}</code>
          {d.attributes?.length > 0 && <>, attributes {d.attributes.map((a, i) => <Fragment key={a}>{i > 0 && ', '}<code>{a}</code></Fragment>)}</>}
        </p>
      ))}
      {measures.length > 0 && (
        <table className="tb-list tpage__measures">
          <thead><tr><th>Measure</th><th>Names</th></tr></thead>
          <tbody>
            {measures.map(m => (
              <tr key={m.name}>
                <td>
                  <Link to={`${modelPath(model)}?view=measures`}>{m.description || m.name}</Link>
                  {m.description && <span className="dlist__id"> {m.name}</span>}
                </td>
                <td><code>{definition(m)}</code></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {facts.length > 0 && measures.length === 0 && <p className="wb-meta">No measure names one of its columns.</p>}
    </li>
  )
}

function UsedBy({ t }) {
  return (
    <div className="tpage__used">
      <section aria-labelledby="used-models">
        <h2 id="used-models">Models</h2>
        {t.read_by.length
          ? <ul className="tpage__uses">
              {t.read_by.map(m => <ModelUse key={m} model={m} source={t.source} table={t.table} columns={t.columns} />)}
            </ul>
          : <p className="src-quiet">No model reads this table.</p>}
      </section>
      <section aria-labelledby="used-reports">
        <h2 id="used-reports">Reports</h2>
        {t.used_by.length
          ? <ul className="tpage__reports">
              {t.used_by.map(r => <li key={r.report}><Link to={reportPagePath(r.report)}>{r.display_name || r.report}</Link></li>)}
            </ul>
          : <p className="src-quiet">No report reads a model over this table.</p>}
      </section>
    </div>
  )
}

// ── The page ──────────────────────────────────────────────────────────────────

// The address names no data table: none by that name, or one of TraceBi's own.
function NotATable({ source, table }) {
  return (
    <>
      <PageTitle>Not a data table</PageTitle>
      <PageSub>
        There is no table named <code>{table}</code> in <code>{source}</code>, or it is one of TraceBi's
        own (<code>tracebi_*</code>, <code>alembic_version</code>), which are never shown as data.
      </PageSub>
      <Empty message="Every table the transforms wrote is under Warehouse."
             action={<BtnLink to={warehousePath()}>Open the Warehouse</BtnLink>} />
    </>
  )
}

// Copy SQL, top right: the table's whole SELECT, to take to a notebook.
function CopySql({ source, table, columns }) {
  const toast = useToast()
  return (
    <Btn size="sm" variant="outline"
         onClick={() => copyText(cutSql(source, table, columns, { where: [], q: '', sort: '' }))
           .then(ok => toast(ok ? 'Copied the SQL' : 'Could not copy', ok ? 'info' : 'error'))}>
      Copy SQL
    </Btn>
  )
}

/**
 * One table's page. Under Warehouse (*warehouse*) the address names only the
 * table, and the warehouse that holds it is found from the listing (?warehouse=
 * picks one when two hold that name); under Sources it names the connection
 * (or inputs) and the table. A table reached under Sources that the API says
 * is a warehouse's moves to its address under Warehouse.
 */
export default function TablePage({ warehouse: underWarehouse = false }) {
  const routed = useParams()
  const { search } = useLocation()
  const [params] = useSearchParams()
  const table = underWarehouse ? routed.table : routed['*']
  // Which warehouse holds it, and whether an unreachable source is one (for
  // the crumb): the listing, asked only then.
  const [listed, setListed] = useState(underWarehouse)
  const { data: warehouses, isLoading: whLoading } = useWarehouses(listed || !underWarehouse)
  const all = warehouses?.warehouses || []
  const holder = params.get('warehouse') || all.find(w => w.tables.some(x => x.name === table))?.name || all[0]?.name
  const source = underWarehouse ? holder : routed.source
  const { data: t, isLoading, error } = useTable(source, table)
  useEffect(() => { if (t?.connected === false) setListed(true) }, [t?.connected])
  const { data: connectors } = useConnectors()
  const { data: inputs } = useInputs()
  const { data: graph } = useGraph()
  const labelOf = useModelLabel()
  const reads = underWarehouse ? [] : sourceReads({ source, table, warehouses, connectors, inputs })
  // The source table's last run read a committed file instead: its rows stand in
  // when the connection is not reachable here.
  const snapshot = reads.find(r => r.snapshot)?.snapshot

  // The model whose data browser holds it: one that reads the table, else
  // (a connection nothing models) one its readers name.
  const conn = (connectors || []).find(c => c.name === source)
  const model = t?.read_by?.[0] || conn?.read_by?.models?.[0] || conn?.used_by?.[0] || ''
  // What that model calls it and its kind there (fact, dimension).
  const { data: modelData } = useModel(model)
  const modelTable = (modelData?.tables || []).find(x => x.connector === source && x.source === table)
  const role = modelTable && buildModelGraph(modelData).nodes.find(n => n.name === modelTable.name)?.role

  if (underWarehouse && (whLoading || !source)) {
    return (
      <DataFrame trail={[[warehousePath(), 'Warehouse']]} here={table} code>
        <div className="tpage">{whLoading ? <SkeletonCard /> : <NotATable source="the warehouse" table={table} />}</div>
      </DataFrame>
    )
  }
  // A warehouse's table has its address under Warehouse; the grid's cut comes along.
  const isWarehouse = t?.kind ? t.kind === 'warehouse' : all.some(w => w.name === source)
  if (!underWarehouse && isWarehouse) {
    const many = all.filter(w => w.tables.some(x => x.name === table)).length > 1
    const q = new URLSearchParams(search)
    if (many) q.set('warehouse', source)
    return <Navigate to={`${warehouseTablePath(table)}${q.toString() ? `?${q}` : ''}`} replace />
  }

  const trail = underWarehouse ? [[warehousePath(), 'Warehouse']]
    : [[sourcesPath(), 'Sources'], [sourcePath(source), source === 'inputs' ? 'inputs/' : source]]
  const frame = body => <DataFrame trail={trail} here={table} code><div className="tpage fade-in">{body}</div></DataFrame>
  if (isLoading || (!t && !error)) return frame(<><PageTitle>{table}</PageTitle><SkeletonCard /></>)
  if (error?.status === 404) return frame(<NotATable source={source} table={table} />)
  if (error) return frame(<><PageTitle>{table}</PageTitle><ErrorDetail error={error} /></>)

  // The table's graph node: a warehouse table, a source table or an input file.
  const byId = Object.fromEntries((graph?.nodes || []).map(n => [n.id, n]))
  const nodeId = t.kind === 'warehouse' ? `table:${source}.${table}`
    : source === 'inputs' ? `file:inputs/${table}` : `source_table:${source}.${table}`
  const node = byId[nodeId]
  const p = node?.passport
  const off = t.connected === false
  const status = node ? statusWords(node, byId[node.parent])
    : off ? { text: 'Unreachable', tone: 'warn', title: reachWords(t).text }
      : t.contract ? { text: checksWords(t.contract).text, tone: checksWords(t.contract).tone || 'ok' } : null
  const became = [...new Set(reads.flatMap(r => r.became))]
  const kind = t.table_kind === 'view' ? 'view' : role === 'fact' ? 'fact' : role === 'dimension' ? 'dim'
    : source === 'inputs' ? (table.split('.').pop() || '').toUpperCase() : node?.chip || 'table'
  const file = snapshot?.replace(/^inputs\//, '')
  const keep = ['warehouse']
  const asked = params.get('tab') ? null : VIEW_TAB[params.get('view')]

  const overview = () => (
    <>
      {off && <NotConnected source={source} answer={t} />}
      <Details items={t.kind === 'warehouse' ? [
        ['Kind', t.table_kind === 'view' ? `View${t.view?.bases?.length ? ` over ${t.view.bases.join(', ')}` : ''}` : role || 'Table'],
        ['Shape', `${rowsText(t)} · ${count(t.columns.length, 'column')}`],
        ['Written by', t.written_by?.transform
          ? <><TransformName name={t.written_by.transform} />{t.written_by.at && <> · <Time iso={t.written_by.at} /></>}</>
          : 'No recorded transform'],
        ['From', t.transform_read?.length ? <ReadOnRun items={t.transform_read} /> : p?.origin ? <code>{p.origin}</code> : null],
        ['Read by', <Links items={t.read_by.map(m => ({ key: m, to: modelPath(m), label: labelOf(m) }))}
                           none={<Chip tone="warn">Nobody reads it</Chip>} />],
        ['Used by', count(t.used_by.length, 'report')],
        ['Last moved', p ? movedWords(p.moved, 'table') : null],
        ['Trust', p ? <StateChip state={p.trust} /> : t.contract ? checksWords(t.contract).text : null],
        ['Agents', <StateChip state={p?.agents} />],
      ] : [
        ['From', <Link to={sourcePath(source)}>{source === 'inputs' ? 'inputs/' : conn?.label || source}</Link>],
        ['Shape', off ? 'Not reachable here' : `${rowsText(t)} · ${count(t.columns.length, 'column')}`],
        ['Read by', reads.length
          ? reads.map((r, i) => (
            <Fragment key={r.transform}>
              {i > 0 && '; '}<TransformName name={r.transform} /> as <code>{r.ref}</code>
              {r.method && <> · {r.method}</>}{r.named && <> · named in the file; no recorded run read it</>}
            </Fragment>))
          : <Chip tone="warn">No transform reads it</Chip>],
        ['Last read', reads.find(r => r.at) ? <Time iso={reads.find(r => r.at).at} /> : null],
        ['Became', <Links items={became.map(b => ({ key: b, to: warehouseTablePath(b), label: b, code: true }))} />],
        ['Last moved', p ? movedWords(p.moved, node.kind) : null],
        ['Trust', p ? <StateChip state={p.trust} /> : null],
        ['Agents', <StateChip state={p?.agents} />],
        ['Snapshot', snapshot ? <code>{snapshot}</code> : null],
      ]} />
      <ContractFold c={t.contract} />
    </>
  )
  const data = () => (off
    ? (file
      ? (
        <section className="tpage__snap" aria-label="Snapshot">
          <p className="tpage__shape">
            <Chip tone="warn" title="The committed file the last run read in place of the connection.">Read from snapshot · {snapshot}</Chip>
          </p>
          <DataGrid source="inputs" table={file} inAddress />
        </section>
      )
      : <NotConnected source={source} answer={t} />)
    : <DataGrid source={source} table={table} columns={t.columns} inAddress />)
  const activity = []
  if (t.written_by?.at) {
    activity.push({ key: 'written', status: { text: 'Written', tone: 'ok' }, what: t.written_by.transform || 'a run',
      to: t.written_by.transform ? transformPath(t.written_by.transform) : null, at: t.written_by.at })
  }
  if (t.contract?.checked_at) {
    const c = checksWords(t.contract)
    activity.push({ key: 'checked', status: { text: c.text, tone: c.tone || 'ok', title: c.title }, what: t.contract.file, at: t.contract.checked_at })
  }
  reads.filter(r => r.at).forEach(r => activity.push({
    key: `read-${r.transform}`, status: r.snapshot ? { text: 'Snapshot read', tone: 'warn' } : { text: 'Read', tone: 'ok' },
    what: r.transform, to: transformPath(r.transform), sub: r.method, at: r.at,
  }))
  activity.sort((a, b) => String(b.at).localeCompare(String(a.at)))

  return (
    <ResourcePage
      trail={trail} here={table} code
      title={table} type={kind} status={status}
      sub={<>
        {off ? 'Not counted: its source is not reachable here' : `${rowsText(t)} · ${count(t.columns.length, 'column')}`}
        {t.written_by?.transform && <> · written by {t.written_by.transform}</>}
        {t.read_by?.length > 0 && <> · read by {t.read_by.map(labelOf).join(', ')}</>}
        {t.used_by?.length > 0 && <> · used by {count(t.used_by.length, 'report')}</>}
      </>}
      node={nodeId} keep={keep} tab={asked}
      actions={!off && <>
        <CopySql source={source} table={table} columns={t.columns} />
        {t.kind === 'warehouse' && <ExportTo source={source} table={table} />}
      </>}
      tabs={[
        { key: 'overview', label: 'Overview', render: overview },
        { key: 'data', label: 'Data', render: data },
        !off && { key: 'columns', label: 'Columns', count: t.columns.length, render: () => <ColumnsView source={source} table={table} from={t.columns_from} /> },
        (t.kind === 'warehouse' || t.read_by?.length > 0) && { key: 'used', label: 'Used by', count: t.read_by.length + t.used_by.length, render: () => <UsedBy t={t} /> },
        activity.length > 0 && { key: 'activity', label: 'Activity', render: () => <ActivityList items={activity} /> },
      ]}
    />
  )
}
