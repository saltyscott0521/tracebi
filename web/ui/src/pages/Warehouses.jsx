import { useEffect, useMemo } from 'react'
import { Link, useLocation, useSearchParams } from 'react-router-dom'

import { useModelDetails, useTables, useWarehouses } from '../api'
import { useModelLabel } from '../components/Scope'
import { ContractLine, ReadInput, groupContract } from '../components/Warehouse'
import DataBrowser, { InspectorSection, KindGlyph } from '../components/DataBrowser'
import { warehouseSchema } from '../components/modelGraph'
import { fmtBytes } from '../components/Storage'
import { TransformName, useTransformHome } from './Connectors'
import { count } from '../format'
import { dataPath, warehousePath } from '../nav'
import { Empty, ErrorDetail, SkeletonCard, Time } from '../components/Shared'

// Data's Warehouse tab (/data/warehouse): every warehouse table in the data
// browser, the tree grouped by the transform that wrote it (its certificate
// names it), the diagram drawn with the joins every model declares over them.
// A transform's group, selected, says once what that run read from outside
// the warehouse and what its checks say; a table, selected, is inspected as on
// a model's page. ?model=<m> keeps only that model's tables.

const TIER = { file: 'File', object: 'Object storage', remote: 'Remote database' }

// What a transform's group says: who wrote these tables, what that run read,
// its checks in their own words (never "verified"), then the tables.
function GroupView({ g, onSelect }) {
  const home = useTransformHome()
  const wr = g.writer
  const own = g.warehouse.tables.filter(t => g.tables.includes(t.name) || g.tables.includes(`${g.warehouse.name}.${t.name}`))
  const views = wr ? wr.tables.filter(n => g.warehouse.tables.find(t => t.name === n)?.kind === 'view').length : 0
  return (
    <div className="dbx-insp__summary" data-writer={wr ? wr.transform || wr.contract : ''}>
      <header className="dbx-insp__head">
        <div className="dbx-insp__title">
          <h2 className="dbx-insp__name">{wr ? (wr.transform || wr.contract) : 'Not written by a transform'}</h2>
        </div>
        {wr ? (
          <>
            <p className="whgroup__head dbx-insp__sub">
              {wr.transform ? <TransformName name={wr.transform} home={home} /> : <code>{wr.contract}</code>}
              {' · '}wrote {count(wr.tables.length - views, 'table')}{views > 0 && ` and ${count(views, 'view')}`}
              {wr.tables.length > own.length && ` (${own.length} shown)`}
              {wr.read.length > 0 && <> · read {wr.read.map((src, i) => (
                <span key={src.ref}>{i > 0 && ', '}<ReadInput src={src} /></span>))} on that run</>}
              {wr.at && <> · <Time iso={wr.at} /></>}
            </p>
            <ContractLine contract={groupContract(wr, own)} subject="A table it wrote" />
          </>
        ) : (
          <p className="dbx-insp__sub">
            No transform's checks cover {own.length === 1 ? 'this table' : `these ${count(own.length, 'table')}`},
            so who wrote {own.length === 1 ? 'it' : 'them'} is not recorded.
          </p>
        )}
      </header>
      <InspectorSection id="tables" title="Tables" aside={count(own.length, 'table')}>
        <ul className="dbx-picks">
          {g.tables.map(id => (
            <li key={id}>
              <button type="button" onClick={() => onSelect(id)}><code>{id}</code></button>
            </li>
          ))}
        </ul>
      </InspectorSection>
    </div>
  )
}

// The inspector with nothing selected: each warehouse, where it is and who reads it.
function Summary({ warehouses, schema, model }) {
  const labelOf = useModelLabel()
  return (
    <div className="dbx-insp__summary">
      {warehouses.map(w => {
        const facts = [TIER[w.tier] || w.tier, w.size != null && fmtBytes(w.size), w.engine_version && `DuckDB ${w.engine_version}`]
          .filter(Boolean)
        return (
          <header key={w.name} className="dbx-insp__head" id={`wh-${w.name}`}>
            <div className="dbx-insp__title"><h2 className="dbx-insp__name">{w.name}</h2></div>
            <p className="dbx-insp__sub"><code>{w.where}</code> · {facts.join(' · ')}</p>
            <p className="dbx-insp__sub">
              Read by {w.read_by.length
                ? w.read_by.map((m, i) => <span key={m}>{i > 0 && ', '}<Link to={dataPath(m)}>{labelOf(m)}</Link></span>)
                : 'no model'}
            </p>
            {!w.exists && <p className="dbx-quiet">Nothing is built here yet. Refresh the model that writes it, on its Transform tab.</p>}
            {w.error && <p className="dbx-quiet">Could not read the warehouse: {w.error}</p>}
            {w.hidden_framework_tables > 0 && (
              <p className="dbx-quiet" title="TraceBi's own tables (tracebi_*, alembic_version) are not shown as data.">
                {count(w.hidden_framework_tables, 'framework table')} hidden
              </p>
            )}
          </header>
        )
      })}
      <InspectorSection id="shape" title="What it holds">
        <p className="dbx-quiet">
          {count(schema.tables.length, 'table')}{model ? ` ${labelOf(model)} reads` : ''} · {count(schema.edges.length, 'join')} the models declare
          · {count(schema.groups.filter(g => g.writer).length, 'transform')} wrote them.
        </p>
        <p className="dbx-quiet">
          Select a transform in the tree for what its run read and what its checks say, or a table for its columns and rows.
          The kinds are the models': <KindGlyph role="fact" /> a fact, <KindGlyph role="dimension" /> a dimension.
          {warehouses.some(w => w.tables.some(t => t.kind === 'view')) && <> <KindGlyph view /> is a view a transform defined over warehouse tables.</>}
        </p>
      </InspectorSection>
    </div>
  )
}

export default function Warehouses() {
  const [params] = useSearchParams()
  const { hash } = useLocation()
  const model = params.get('model') || ''
  const { data, isLoading, error } = useWarehouses()
  const labelOf = useModelLabel()
  const warehouses = useMemo(() => data?.warehouses || [], [data])
  const readers = [...new Set(warehouses.flatMap(w => w.read_by))]
  // Every model over a warehouse, for its joins and its tables' columns.
  const models = useModelDetails(readers)
  const loaded = models.every(q => !q.isLoading)
  const payloads = models.map(q => q.data).filter(Boolean)
  // A table no model reads has its columns from the table API.
  const unread = warehouses.flatMap(w => w.tables.filter(t => !t.read_by.length).map(t => [w.name, t.name]))
  const extras = useTables(unread)
  const extra = Object.fromEntries(unread.map(([w, t], i) => [`${w}.${t}`, extras[i]?.data?.columns || []]))
  const extraKey = extras.map(q => q.dataUpdatedAt).join()
  const schema = useMemo(
    () => (loaded ? warehouseSchema(warehouses, payloads, extra, model) : null),
    [loaded, warehouses, payloads.length, extraKey, model], // eslint-disable-line react-hooks/exhaustive-deps
  )
  const infoOf = useMemo(() => t => t && { rows: t.listed.rows, exact: true, contract: t.listed.contract, view: t.listed.kind === 'view' }, [])

  // A link to one warehouse lands on it (#wh-<name>).
  useEffect(() => {
    if (schema && hash) document.getElementById(hash.slice(1))?.scrollIntoView()
  }, [schema, hash])

  if (error) return <ErrorDetail error={error} />
  if (isLoading || (warehouses.length && !schema)) return <SkeletonCard />
  if (!warehouses.length) {
    return <Empty message="No warehouse yet. A model's connector names one, and its transform writes it." />
  }
  return (
    <>
      {model && (
        <p className="scope-note">
          Only the tables {labelOf(model)} reads. <Link to={warehousePath()}>Show every table</Link>
        </p>
      )}
      {schema.tables.length === 0
        ? <Empty message="The warehouse holds no tables yet. Refresh a model on its Transform tab to write them." />
        : (
          <DataBrowser
            schema={schema} storeKey={`warehouse${model ? `-${model}` : ''}`} label="The warehouse's tables"
            infoOf={infoOf}
            summary={<Summary warehouses={warehouses} schema={schema} model={model} />}
            groupView={(g, onSelect) => <GroupView g={g} onSelect={onSelect} />}
          />
        )}
    </>
  )
}
