import { Fragment } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'

import { useConnectors, useCredentials, useModel, useTable, useTableProfile, useWarehouses } from '../api'
import DataGrid, { cellText } from '../components/DataGrid'
import { CredentialChip } from '../components/Credentials'
import { useModelLabel } from '../components/Scope'
import { CONTRACT } from '../components/Warehouse'
import { TransformName, useTransformHome } from './Connectors'
import { count } from '../format'
import { dataPath, libraryPath, reportPagePath, sourcesPath, tablePath, warehousePath } from '../nav'
import {
  BtnLink, Chip, Empty, ErrorDetail, PageSub, PageTitle, Segmented, SkeletonCard, SkeletonList, Time,
} from '../components/Shared'

// One table's page (/data/tables/<source>/<table>): wherever it lives (a
// warehouse, a connection, a file under inputs/), what it is, who wrote it,
// who reads it, and its rows. The view is in the address (?view=), and so is
// the grid's cut, so a sorted, filtered page of rows can be linked.

const VIEWS = [['data', 'Data'], ['columns', 'Columns'], ['used', 'Used by']]

// Sources with one connection (or inputs/) open, narrowed to *model* when known.
function sourceLink(source, model) {
  const to = sourcesPath(model)
  return `${to}${to.includes('?') ? '&' : '?'}source=${encodeURIComponent(source)}`
}

// "Data › Warehouse › fact_holdings", or "Data › Sources › crm › issuer_ratings".
function Crumb({ source, table, warehouse, model }) {
  const parts = warehouse === null ? []
    : warehouse ? [[warehousePath(model), 'Warehouse']]
    : [[sourcesPath(model), 'Sources'], [sourceLink(source, model), source === 'inputs' ? 'inputs/' : source]]
  return (
    <nav aria-label="Where this table is" className="rp__crumb tpage__crumb">
      <Link to="/data">Data</Link>
      {parts.map(([to, text]) => (
        <Fragment key={text}><span aria-hidden="true">›</span><Link to={to}>{text}</Link></Fragment>
      ))}
      <span aria-hidden="true">›</span>
      <span aria-current="page" className="tpage__crumb-here">{table}</span>
    </nav>
  )
}

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
      ? <Link to={tablePath(src.ref.slice(0, dot), src.ref.slice(dot + 1))}><code>{src.ref}</code></Link>
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

// One line of facts, each a link to where that fact lives.
function Facts({ t }) {
  const labelOf = useModelLabel()
  const home = useTransformHome()
  const first = t.read_by[0] || ''
  const facts = []
  if (t.kind === 'warehouse') {
    facts.push(
      <span key="w">
        Written by {t.written_by?.transform
          ? <>
              <TransformName name={t.written_by.transform} home={home} />
              {t.written_by.at && <> · <Time iso={t.written_by.at} /></>}
            </>
          : 'no recorded transform'}
      </span>,
    )
  }
  facts.push(
    <span key="r">
      Read by {t.read_by.length
        ? t.read_by.map((m, i) => <Fragment key={m}>{i > 0 && ', '}<Link to={dataPath(m)}>{labelOf(m)}</Link></Fragment>)
        : 'no model'}
    </span>,
  )
  facts.push(
    <span key="u">
      {t.used_by.length
        ? <Link to={libraryPath(first)}>Used by {count(t.used_by.length, 'report')}</Link>
        : 'Used by no report'}
    </span>,
  )
  if (t.transform_read?.length) {
    facts.push(<span key="f">The run that wrote it read <ReadOnRun items={t.transform_read} /></span>)
  }
  return <p className="tpage__facts">{facts}</p>
}

// The sink contract's words, folded under the header: what the transform
// said about the table it wrote (never "verified"), and its note.
function ContractFold({ c }) {
  if (!c || c.status === 'no_contract') return null
  return (
    <details className="wb-details tpage__contract">
      <summary>What its checks say</summary>
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
function NotConnected({ source, answer, model }) {
  const { data } = useCredentials()
  const row = (data?.credentials || []).find(r => r.name === answer.variable)
  return (
    <div className="tpage__off" data-connected="false">
      <p className="src-quiet">
        Not connected here · {answer.variable ? <>set <code>{answer.variable}</code></> : answer.reason}
        {row && <CredentialChip row={row} />}
      </p>
      {source !== 'inputs' && (
        <BtnLink size="sm" to={sourceLink(source, model)}>
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
              <td><code>{name}</code></td>
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
        <Link to={dataPath(model)}>{labelOf(model)}</Link>
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
                  <Link to={`${dataPath(model)}?view=measures`}>{m.description || m.name}</Link>
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

export default function TablePage() {
  const { source, '*': table } = useParams()
  const [params, setParams] = useSearchParams()
  const view = VIEWS.some(([v]) => v === params.get('view')) ? params.get('view') : 'data'
  const { data: t, isLoading, error } = useTable(source, table)
  // Whether an unreachable source is a warehouse (for the crumb): asked only then.
  const { data: warehouses } = useWarehouses(t?.connected === false)
  const { data: connectors } = useConnectors()

  // null while not known yet: the crumb then says only Data.
  const warehouse = t?.kind ? t.kind === 'warehouse'
    : warehouses ? warehouses.warehouses.some(w => w.name === source)
    : source === 'inputs' ? false : null
  // The model to narrow Sources and Warehouse to: one that reads the table,
  // else (a connection nothing models) one its readers name.
  const conn = (connectors || []).find(c => c.name === source)
  const model = t?.read_by?.[0] || conn?.read_by?.models?.[0] || conn?.used_by?.[0] || ''
  const setView = v => setParams(p => {
    const next = new URLSearchParams(p)
    if (v === 'data') next.delete('view'); else next.set('view', v)
    return next
  }, { replace: true })

  const crumb = <Crumb source={source} table={table} warehouse={warehouse} model={model} />
  if (isLoading) return <div className="tpage">{crumb}<PageTitle>{table}</PageTitle><SkeletonCard /></div>
  if (error?.status === 404) {
    return (
      <div className="tpage">
        {crumb}
        <PageTitle>Not a data table</PageTitle>
        <PageSub>
          There is no table named <code>{table}</code> in <code>{source}</code>, or it is one of TraceBi's
          own (<code>tracebi_*</code>, <code>alembic_version</code>), which are never shown as data.
        </PageSub>
        <Empty message="Every table the transforms wrote is listed on the Warehouse tab."
               action={<BtnLink to={warehousePath()}>Open the Warehouse</BtnLink>} />
      </div>
    )
  }
  if (error) return <div className="tpage">{crumb}<PageTitle>{table}</PageTitle><ErrorDetail error={error} /></div>

  if (t.connected === false) {
    return (
      <div className="tpage fade-in">
        {crumb}
        <header className="tpage__head">
          <h1 className="tpage__name">{table}</h1>
        </header>
        <NotConnected source={source} answer={t} model={model} />
      </div>
    )
  }

  const c = t.contract && (CONTRACT[t.contract.status] || CONTRACT.no_contract)
  return (
    <div className="tpage fade-in">
      {crumb}
      <header className="tpage__head">
        <h1 className="tpage__name">{table}</h1>
        <p className="tpage__shape">
          <span>{rowsText(t)} · {count(t.columns.length, 'column')}</span>
          {c && <Chip tone={c.tone} title={c.title}>{c.label}</Chip>}
        </p>
        <Facts t={t} />
        <ContractFold c={t.contract} />
      </header>
      <Segmented options={VIEWS} value={view} onChange={setView} label="Show" panel="table-view" />
      <div id="table-view" role="tabpanel" aria-labelledby={`table-view-${view}`}>
        {view === 'data' && (
          <DataGrid source={source} table={table} columns={t.columns} inAddress />
        )}
        {view === 'columns' && <ColumnsView source={source} table={table} />}
        {view === 'used' && <UsedBy t={t} />}
      </div>
    </div>
  )
}
