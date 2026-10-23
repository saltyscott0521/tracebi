import { useEffect, useState } from 'react'
import { Link, useLocation, useSearchParams } from 'react-router-dom'

import { useWarehouses } from '../api'
import { useModelLabel } from '../components/Scope'
import { ByWriter } from '../components/Warehouse'
import { fmtBytes } from '../components/Storage'
import { count } from '../format'
import { dataPath, warehousePath } from '../nav'
import { Empty, ErrorDetail, SearchInput, SkeletonCard } from '../components/Shared'

// Data's Warehouse tab (/data/warehouse): every warehouse the project's
// connectors name, on its tier, and every table in it, grouped by the
// transform that wrote it (its certificate names it). A group says once what
// that transform's run read from outside the warehouse and what its checks
// say; a row is one table, its name the link to the table page, where its
// columns, profile and rows are. ?model=<m> keeps only that model's tables.

const TIER = { file: 'File', object: 'Object storage', remote: 'Remote database' }

function Section({ w }) {
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
      ) : w.all === 0 ? (
        <p className="src-quiet">It holds no tables yet.</p>
      ) : (
        <ByWriter w={w} tables={w.tables} />
      )}
      {w.hidden_framework_tables > 0 && (
        <p className="src-quiet" title="TraceBi's own tables (tracebi_*, alembic_version) are not shown as data.">
          {count(w.hidden_framework_tables, 'framework table')} hidden
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
  const [query, setQuery] = useState('')

  // A link to one warehouse lands on it (#wh-<name>).
  useEffect(() => {
    if (data && hash) document.getElementById(hash.slice(1))?.scrollIntoView()
  }, [data, hash])

  if (isLoading) return <SkeletonCard />
  if (error) return <ErrorDetail error={error} />
  const q = query.trim().toLowerCase()
  const sections = (data?.warehouses || [])
    .map(w => (model ? { ...w, tables: w.tables.filter(t => t.read_by.includes(model)) } : w))
    .filter(w => !model || w.read_by.includes(model) || w.tables.length)
    .map(w => ({ ...w, all: w.tables.length, tables: w.tables.filter(t => t.name.toLowerCase().includes(q)) }))
  const tables = sections.reduce((n, w) => n + w.all, 0)
  return (
    <>
      {model && (
        <p className="scope-note">
          Only the tables {labelOf(model)} reads. <Link to={warehousePath()}>Show every table</Link>
        </p>
      )}
      {sections.length === 0
        ? <Empty message="No warehouse yet. A model's connector names one, and its transform writes it." />
        : (
          <>
            {tables > 0 && (
              <div className="whfilter">
                <SearchInput value={query} onChange={setQuery} placeholder="Filter tables…" label="Filter tables"
                             style={{ padding: 0, borderBottom: 0 }} />
              </div>
            )}
            {sections.map(w => <Section key={w.name} w={w} />)}
          </>
        )}
    </>
  )
}
