import { useEffect, useState } from 'react'
import { Link, useLocation, useSearchParams } from 'react-router-dom'

import { useConnectorWarehouse, useWarehouses } from '../api'
import { useModelLabel } from '../components/Scope'
import { CONTRACT, ContractLine, Profile } from '../components/Warehouse'
import { fmtBytes } from '../components/Storage'
import { stamp } from '../components/TheLine'
import { TransformName, useTransformHome } from './Connectors'
import { dataPath, warehousePath } from '../nav'
import { Chip, Empty, ErrorDetail, SkeletonCard, Spinner } from '../components/Shared'

// Data's Warehouse tab (/data/warehouse): every warehouse the project's
// connectors name, on its tier, and every table in it with who wrote it (the
// transform its certificate names, and when), which models read it, whether
// it still matches the checks it passed, and the outside sources the
// transform read on that run. The contract chip is what the sink said about
// itself; it colours nothing else. ?model=<m> keeps only that model's tables.

const TIER = { file: 'File', object: 'Object storage', remote: 'Remote database' }

const plural = (n, one, many = `${one}s`) => `${n.toLocaleString()} ${n === 1 ? one : many}`

const short = fp => (fp ? `${fp.slice(0, 8)}…` : '')

// Where a table's outside input came from on the run that wrote it: the
// connection and its fingerprint, or the committed snapshot that stood in.
function FedFrom({ src }) {
  return (
    <span className="whrow__fed">
      <code>{src.ref}</code>
      {src.snapshot
        ? <> · snapshot <code>{src.snapshot}</code></>
        : <> · fingerprint <code title={src.fingerprint}>{short(src.fingerprint)}</code>{src.loaded_at && <> · read {stamp(src.loaded_at)}</>}</>}
    </span>
  )
}

// The columns and the checks, read when the row is opened (the connector's
// own warehouse view, which profiles every column).
function Opened({ warehouse, table }) {
  const { data, isLoading, error } = useConnectorWarehouse(warehouse)
  if (isLoading) return <p className="src-quiet"><Spinner size={12} /> Reading the table…</p>
  if (error) return <ErrorDetail error={error} />
  const t = (data?.tables || []).find(x => x.name === table)
  if (!t) return <p className="src-quiet">The table is not there any more.</p>
  return (
    <>
      <ContractLine contract={t.contract || { status: 'no_contract' }} />
      <Profile table={t} />
    </>
  )
}

function TableRow({ warehouse, t, home }) {
  const labelOf = useModelLabel()
  const [open, setOpen] = useState(false)
  const c = CONTRACT[t.contract?.status] || CONTRACT.no_contract
  const by = t.written_by
  return (
    <li className="whrow" data-table={t.name}>
      <div className="whrow__top">
        <span className="whrow__main">
          <code className="whrow__name">{t.name}</code>
          <span className="wb-meta">{plural(t.rows, 'row')} · {plural(t.columns, 'column')}</span>
        </span>
        <Chip tone={c.tone} title={c.title}>{c.label}</Chip>
      </div>
      <p className="whrow__facts">
        <span>
          Written by {by
            ? <>{by.transform ? <TransformName name={by.transform} home={home} /> : <code>{by.contract}</code>}{by.at && ` · ${stamp(by.at)}`}</>
            : 'not recorded (no checks cover it)'}
        </span>
        <span>
          Read by {t.read_by.length
            ? t.read_by.map((m, i) => <span key={m}>{i > 0 && ', '}<Link to={dataPath(m)}>{labelOf(m)}</Link></span>)
            : 'no model'}
        </span>
        {t.fed_from.length > 0 && (
          <span>Fed from {t.fed_from.map((src, i) => <span key={src.ref}>{i > 0 && ', '}<FedFrom src={src} /></span>)}</span>
        )}
      </p>
      <details className="wb-details" onToggle={e => setOpen(e.currentTarget.open)}>
        <summary>Columns and checks</summary>
        {open && <div className="whrow__open"><Opened warehouse={warehouse} table={t.name} /></div>}
      </details>
    </li>
  )
}

function Section({ w, home }) {
  const labelOf = useModelLabel()
  const facts = [TIER[w.tier] || w.tier, w.size != null && fmtBytes(w.size), w.engine_version && `DuckDB ${w.engine_version}`]
    .filter(Boolean)
  return (
    <section className="whs" id={`wh-${w.name}`} aria-labelledby={`wh-${w.name}-h`}>
      <header className="whs__head">
        <h2 id={`wh-${w.name}-h`}>{w.name}</h2>
        <p className="whs__facts">
          <code>{w.where}</code> · {facts.join(' · ')}
        </p>
        <p className="whs__facts">
          Read by {w.read_by.length
            ? w.read_by.map((m, i) => <span key={m}>{i > 0 && ', '}<Link to={dataPath(m)}>{labelOf(m)}</Link></span>)
            : 'no model'}
        </p>
      </header>
      {!w.exists ? (
        <p className="src-quiet">Nothing is built here yet. Refresh the model that writes it, on its Transform tab.</p>
      ) : w.error ? (
        <p className="src-quiet">Could not read the warehouse: {w.error}</p>
      ) : w.tables.length === 0 ? (
        <p className="src-quiet">It holds no tables yet.</p>
      ) : (
        <ul className="whs__tables">
          {w.tables.map(t => <TableRow key={t.name} warehouse={w.name} t={t} home={home} />)}
        </ul>
      )}
      {w.hidden_framework_tables > 0 && (
        <p className="src-quiet" title="TraceBi's own tables (tracebi_*, alembic_version) are not shown as data.">
          {plural(w.hidden_framework_tables, 'framework table')} hidden
        </p>
      )}
    </section>
  )
}

export default function Warehouses() {
  const [params] = useSearchParams()
  const { hash } = useLocation()
  const model = params.get('model') || ''
  const { data, isLoading, error } = useWarehouses()
  const labelOf = useModelLabel()
  const home = useTransformHome()

  // The Sources tab's "Open in Warehouse" lands on that warehouse (#wh-<name>).
  useEffect(() => {
    if (data && hash) document.getElementById(hash.slice(1))?.scrollIntoView()
  }, [data, hash])

  if (isLoading) return <SkeletonCard />
  if (error) return <ErrorDetail error={error} />
  const sections = (data?.warehouses || [])
    .map(w => (model ? { ...w, tables: w.tables.filter(t => t.read_by.includes(model)) } : w))
    .filter(w => !model || w.read_by.includes(model) || w.tables.length)
  return (
    <>
      {model && (
        <p className="scope-note">
          Only the tables {labelOf(model)} reads. <Link to={warehousePath()}>Show every table</Link>
        </p>
      )}
      {sections.length === 0
        ? <Empty message="No warehouse yet. A model's connector names one, and its transform writes it." />
        : sections.map(w => <Section key={w.name} w={w} home={home} />)}
    </>
  )
}
