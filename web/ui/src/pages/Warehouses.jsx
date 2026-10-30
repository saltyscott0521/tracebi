import { useEffect, useMemo } from 'react'
import { Link, useLocation, useSearchParams } from 'react-router-dom'

import { useGraph, useModelDetails, usePipelines, useTables, useWarehouses } from '../api'
import { useModelLabel } from '../components/Scope'
import { ContractLine, ReadInput, groupContract } from '../components/Warehouse'
import DataBrowser, { InspectorSection, KindGlyph } from '../components/DataBrowser'
import ResourceTable, { NameCell, StatusPill, TypeChip } from '../components/ResourceTable'
import { Links } from '../components/ResourcePage'
import { warehouseSchema } from '../components/modelGraph'
import { fmtBytes } from '../components/Storage'
import { TransformName } from './Connectors'
import { transformOf } from '../chain'
import { count } from '../format'
import { checksWords, statusWords, tierWords } from '../words'
import { lineagePath, modelPath, transformPath, transformsPath, warehouseTablePath } from '../nav'
import { Empty, ErrorDetail, Segmented, SkeletonCard, Time } from '../components/Shared'

// Data's Warehouse folder (/data/warehouse): every warehouse table, as the
// console's list (?view=table, the default: kind, checks, rows, who wrote it,
// who reads it, when) or in the data browser (?view=schema): the tree grouped
// by the transform that wrote it (its certificate names it), the diagram
// drawn with the joins every model declares over them. A transform's group,
// selected, says once what that run read from outside the warehouse and what
// its checks say; a table, selected, has a short card in the inspector. Every
// table has its own page (/data/warehouse/<table>).

const VIEWS = [['table', 'Table'], ['schema', 'Schema']]
const KIND_WORD = { fact: 'fact', dimension: 'dim', bridge: 'bridge', table: 'table' }

// The list: one row per table, in the console's columns.
function TableView({ schema, warehouses }) {
  const { data: graph } = useGraph()
  const labelOf = useModelLabel()
  const byId = Object.fromEntries((graph?.nodes || []).map(n => [n.id, n]))
  const many = warehouses.length > 1
  const rows = schema.tables.map(t => {
    const node = byId[`table:${t.connector}.${t.name}`]
    const kind = t.listed.kind === 'view' ? 'view' : KIND_WORD[t.role] || 'table'
    const c = t.listed.contract
    return {
      key: t.id, label: t.name, t, node, kind,
      status: node ? statusWords(node) : c ? { text: checksWords(c).text, tone: checksWords(c).tone || 'ok' } : { text: 'No checks', tone: 'none' },
      to: warehouseTablePath(t.name, many ? t.connector : ''),
    }
  })
  return (
    <ResourceTable
      label="Warehouse tables" placeholder="Find a table" rows={rows} defaultSort="name"
      search={r => `${r.label} ${r.t.listed.written_by?.transform || ''}`}
      filters={[
        { key: 'all', label: 'All' },
        { key: 'facts', label: 'Facts', test: r => r.kind === 'fact' },
        { key: 'dims', label: 'Dimensions', test: r => r.kind === 'dim' },
        { key: 'views', label: 'Views', test: r => r.kind === 'view' },
        { key: 'unread', label: 'Nobody reads it', test: r => !r.t.listed.read_by?.length },
        { key: 'changed', label: 'Changed since checked', test: r => r.t.listed.contract?.status === 'stale' },
      ]}
      count={(n, of) => `${n === of ? '' : `${n} of `}${count(of, 'table')}`}
      rowProps={r => ({ 'data-table': r.label })}
      columns={[
        { key: 'name', label: 'Name', sort: r => r.label, render: r => <NameCell to={r.to} label={r.label} code /> },
        { key: 'kind', label: 'Kind', sort: r => r.kind, render: r => <TypeChip>{r.kind}</TypeChip> },
        { key: 'status', label: 'Status', sort: r => r.status.text, render: r => <StatusPill status={r.status} /> },
        { key: 'rows', label: 'Rows', num: true, sort: r => r.t.listed.rows, render: r => (r.t.listed.rows == null ? '—' : r.t.listed.rows.toLocaleString('en-US')) },
        { key: 'writer', label: 'Written by', sort: r => r.t.listed.written_by?.transform || '',
          render: r => (r.t.listed.written_by?.transform
            ? <Link to={transformPath(r.t.listed.written_by.transform)}><code>{r.t.listed.written_by.transform}</code></Link>
            : <span className="pass__none">—</span>) },
        { key: 'readers', label: 'Read by', wrap: true, render: r => (
          <Links items={(r.t.listed.read_by || []).map(m => ({ key: m, to: modelPath(m), label: labelOf(m) }))}
                 none={<StatusPill status={{ text: 'Nobody reads it', tone: 'warn' }} />} />
        ) },
        { key: 'at', label: 'Last written', sort: r => r.t.listed.written_by?.at || '',
          render: r => <Time iso={r.t.listed.written_by?.at} relative fallback="—" /> },
      ]}
      menu={r => [
        { label: 'Open', to: r.to },
        { label: 'Columns', to: `${r.to}${r.to.includes('?') ? '&' : '?'}tab=columns` },
        { label: 'Export…', to: `${r.to}${r.to.includes('?') ? '&' : '?'}tab=data` },
        { label: 'Show in schema', to: `?view=schema&table=${encodeURIComponent(r.key)}` },
        r.node && { label: 'View lineage', to: lineagePath(r.node.id) },
      ]}
    />
  )
}

// What a transform's group says: who wrote these tables, what that run read,
// its checks in their own words (never "verified"), then the tables.
function GroupView({ g, onSelect }) {
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
              {wr.transform ? <TransformName name={wr.transform} /> : <code>{wr.contract}</code>}
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
function Summary({ warehouses, schema }) {
  const labelOf = useModelLabel()
  const { data: pipelines } = usePipelines()
  // What writes a warehouse that holds nothing yet: the transform the
  // pipeline of a model over it runs.
  const writerOf = w => w.read_by.map(m => transformOf(pipelines, m)).find(Boolean)
  return (
    <div className="dbx-insp__summary">
      {warehouses.map(w => {
        const facts = [tierWords(w.tier), w.size != null && fmtBytes(w.size), w.engine_version && `DuckDB ${w.engine_version}`]
          .filter(Boolean)
        return (
          <header key={w.name} className="dbx-insp__head" id={`wh-${w.name}`}>
            <div className="dbx-insp__title"><h2 className="dbx-insp__name">{w.name}</h2></div>
            <p className="dbx-insp__sub"><code>{w.where}</code> · {facts.join(' · ')}</p>
            <p className="dbx-insp__sub">
              Read by {w.read_by.length
                ? w.read_by.map((m, i) => <span key={m}>{i > 0 && ', '}<Link to={modelPath(m)}>{labelOf(m)}</Link></span>)
                : 'no model'}
            </p>
            {!w.exists && (
              <p className="dbx-quiet">
                Nothing is built here yet. {writerOf(w)
                  ? <>Its transform, <TransformName name={writerOf(w)} />, writes it.</>
                  : <>A transform writes it: see <Link to={transformsPath()}>Transforms</Link>.</>}
              </p>
            )}
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
          {count(schema.tables.length, 'table')} · {count(schema.edges.length, 'join')} the models declare
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
  const { hash } = useLocation()
  const [params, setParams] = useSearchParams()
  // A table or a group named alone (an older link, the passport's Zoom to
  // schema) is the browser's selection: it opens Schema.
  const view = params.get('view') === 'schema' || (!params.get('view') && (params.get('table') || params.get('group')))
    ? 'schema' : 'table'
  const setView = v => setParams(v === 'schema' ? { view: 'schema' } : {})
  const { data, isLoading, error } = useWarehouses()
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
    () => (loaded ? warehouseSchema(warehouses, payloads, extra) : null),
    [loaded, warehouses, payloads.length, extraKey], // eslint-disable-line react-hooks/exhaustive-deps
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
      {schema.tables.length > 0 && (
        <Segmented options={VIEWS} value={view} onChange={setView} label="Show the warehouse as" className="rview" />
      )}
      {schema.tables.length === 0
        ? <Empty title="The warehouse holds no tables yet" body="A transform writes them when it runs."
                 action={<Link to={transformsPath()}>See the transforms</Link>} />
        : view === 'table' ? <TableView schema={schema} warehouses={warehouses} /> : (
          <DataBrowser
            schema={schema} storeKey="warehouse" label="The warehouse's tables"
            infoOf={infoOf} opensOnGroup
            summary={<Summary warehouses={warehouses} schema={schema} />}
            groupView={(g, onSelect) => <GroupView g={g} onSelect={onSelect} />}
          />
        )}
    </>
  )
}
