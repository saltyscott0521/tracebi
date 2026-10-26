import { Fragment, useEffect, useState } from 'react'
import { Link, Navigate, useLocation, useParams, useSearchParams } from 'react-router-dom'

import { useConnectors, useCredentials, useModel, useTable, useTableProfile, useWarehouses } from '../api'
import DataGrid, { cellText } from '../components/DataGrid'
import { CredentialChip } from '../components/Credentials'
import { useModelLabel } from '../components/Scope'
import { checksWords, reachWords } from '../words'
import { KindGlyph, TypeGlyph } from '../components/DataBrowser'
import { buildModelGraph } from '../components/modelGraph'
import { TransformName } from './Connectors'
import { DataFrame } from './Data'
import { count } from '../format'
import {
  modelPath, reportPagePath, sourcePath, sourceTablePath, sourcesPath, warehousePath, warehouseTablePath,
} from '../nav'
import {
  BtnLink, Chip, Empty, ErrorDetail, PageSub, PageTitle, Segmented, SkeletonCard, SkeletonList, Time,
} from '../components/Shared'

// One table's page, wherever it lives: a warehouse's (/data/warehouse/<table>),
// a connection's (/data/sources/<connection>/<table>) or a file under inputs/
// (/data/sources/inputs/<path>). What it is, who wrote it, who reads it, and
// its rows. The view is in the address (?view=), and so is
// the grid's cut, so a sorted, filtered page of rows can be linked.

const VIEWS = [['data', 'Data'], ['columns', 'Columns'], ['used', 'Used by']]

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

// One line of facts, each a link to where that fact lives: who wrote it,
// who uses it (one link to the Used by view, which names them; they are said
// once, there) and what the run that wrote it read.
function Facts({ t }) {
  const facts = []
  if (t.kind === 'warehouse') {
    facts.push(
      <span key="w">
        Written by {t.written_by?.transform
          ? <>
              <TransformName name={t.written_by.transform} />
              {t.written_by.at && <> · <Time iso={t.written_by.at} /></>}
            </>
          : 'no recorded transform'}
      </span>,
    )
  }
  facts.push(
    <span key="u">
      <Link to="?view=used">Used by {count(t.read_by.length, 'model')} · {count(t.used_by.length, 'report')}</Link>
    </span>,
  )
  if (t.transform_read?.length) {
    facts.push(<span key="f">The run that wrote it read <ReadOnRun items={t.transform_read} /></span>)
  }
  return <p className="tpage__facts">{facts}</p>
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

function ColumnsView({ source, table }) {
  const { data, isLoading, error } = useTableProfile(source, table)
  if (isLoading) return <SkeletonList />
  if (error) return <ErrorDetail error={error} />
  if (data.connected === false) return <p className="src-quiet">{data.reason}</p>
  if (data.note) return <p className="src-quiet">{data.note}</p>
  return (
    <div className="tpage__scroll">
      <table className="tb-list tpage__profile">
        <thead>
          <tr><th>Column</th><th>Type</th><th>Nulls</th><th>Distinct</th><th>Range or top values</th></tr>
        </thead>
        <tbody>
          {Object.entries(data.columns).map(([name, p]) => (
            <tr key={name}>
              <td><span className="tpage__col"><TypeGlyph type={p.type} /><code>{name}</code></span></td>
              <td className="tpage__type">{p.type}</td>
              <td className="grid__num" title={`${p.nulls.toLocaleString('en-US')} of ${count(data.rows, 'row')}`}>{share(p.null_share)}</td>
              <td className="grid__num">{p.distinct.toLocaleString('en-US')}</td>
              <td data-tb-data className="tpage__range">{rangeOf(name, p)}</td>
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
  const [params, setParams] = useSearchParams()
  const table = underWarehouse ? routed.table : routed['*']
  const view = VIEWS.some(([v]) => v === params.get('view')) ? params.get('view') : 'data'
  // Which warehouse holds it, and whether an unreachable source is one (for
  // the crumb): the listing, asked only then.
  const [listed, setListed] = useState(underWarehouse)
  const { data: warehouses, isLoading: whLoading } = useWarehouses(listed)
  const all = warehouses?.warehouses || []
  const holder = params.get('warehouse') || all.find(w => w.tables.some(x => x.name === table))?.name || all[0]?.name
  const source = underWarehouse ? holder : routed.source
  const { data: t, isLoading, error } = useTable(source, table)
  useEffect(() => { if (t?.connected === false) setListed(true) }, [t?.connected])
  const { data: connectors } = useConnectors()

  // The model whose data browser holds it: one that reads the table, else
  // (a connection nothing models) one its readers name.
  const conn = (connectors || []).find(c => c.name === source)
  const model = t?.read_by?.[0] || conn?.read_by?.models?.[0] || conn?.used_by?.[0] || ''
  // What that model calls it and its kind there (fact, dimension), for the
  // glyph the data browser draws.
  const { data: modelData } = useModel(model)
  const modelTable = (modelData?.tables || []).find(x => x.connector === source && x.source === table)
  const role = modelTable && buildModelGraph(modelData).nodes.find(n => n.name === modelTable.name)?.role
  const setView = v => setParams(p => {
    const next = new URLSearchParams(p)
    if (v === 'data') next.delete('view'); else next.set('view', v)
    return next
  }, { replace: true })

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

  if (t.connected === false) {
    return frame(
      <>
        <header className="tpage__head">
          <h1 className="tpage__name">{table}</h1>
        </header>
        <NotConnected source={source} answer={t} />
      </>,
    )
  }

  const c = t.contract && checksWords(t.contract)
  // The data browser it sits in: Warehouse for a warehouse table (the
  // browser's id names the warehouse when there are two), else the model that
  // reads it, with the table selected.
  const named = modelTable?.name
  const schemaId = all.length > 1 ? `${source}.${table}` : table
  const schemaLink = t.kind === 'warehouse' ? `${warehousePath()}?table=${encodeURIComponent(schemaId)}`
    : named ? `${modelPath(model)}?table=${encodeURIComponent(named)}` : null
  return frame(
    <>
      <header className="tpage__head">
        <div className="tpage__title">
          {(role || t.table_kind === 'view') && <KindGlyph role={role} view={t.table_kind === 'view'} />}
          <h1 className="tpage__name">{table}</h1>
          {schemaLink && <Link to={schemaLink} className="tpage__schema">Show in schema</Link>}
        </div>
        <p className="tpage__shape">
          <span>{rowsText(t)} · {count(t.columns.length, 'column')}</span>
          {c && <Chip tone={c.tone} title={c.title}>{c.text}</Chip>}
        </p>
        <Facts t={t} />
        <ContractFold c={t.contract} />
      </header>
      <Segmented options={VIEWS} value={view} onChange={setView} label="Show" panel="table-view" />
      <div id="table-view" role="tabpanel" aria-labelledby={`table-view-${view}`}>
        {view === 'data' && (
          <DataGrid source={source} table={table} columns={t.columns} inAddress exportTo={t.kind === 'warehouse'} />
        )}
        {view === 'columns' && <ColumnsView source={source} table={table} />}
        {view === 'used' && <UsedBy t={t} />}
      </div>
    </>,
  )
}
