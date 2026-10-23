import { Fragment, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useConnectors, useConnectorTables, useInputs, usePipelines } from '../api'
import { StorageLine, sourceKind, fmtBytes } from '../components/Storage'
import { useModelLabel } from '../components/Scope'
import CodeView from '../components/CodeView'
import Credentials from '../components/Credentials'
import { stamp } from '../when'
import { feedsModel, upstreamOf } from '../chain'
import { count } from '../format'
import { dataPath, pipelineModels, sourcesPath, tablePath, warehousePath } from '../nav'
import {
  Card, CardTitle, Badge, Btn, ErrorDetail, Spinner,
  Empty, ListItem, SplitLayout, SearchInput, SkeletonList, SkeletonCard,
} from '../components/Shared'

// The inputs/ folder's entry in the list: files, not a connection.
const INPUTS = 'inputs'

function Section({ label, children }) {
  return <div className="src-section"><div className="src-label">{label}</div>{children}</div>
}

/** transform name → the model page whose Transform tab runs it (the pipeline that names it). */
export function useTransformHome() {
  const { data: pipelines } = usePipelines()
  return name => {
    const p = (pipelines || []).find(x => x.transform === name)
    const model = p && pipelineModels(p)[0]
    return model ? dataPath(model, 'transform') : null
  }
}

export function TransformName({ name, home }) {
  const to = home(name)
  return to ? <Link to={to}><code>{name}</code></Link> : <code>{name}</code>
}

// Who reads a source: the transforms that name its tables (in a `-- source:`
// line or a load_source call), the pipelines whose steps take it as their
// source (one line per pipeline, its steps named), and the models that read
// it directly. Read from the files, so a source nothing names says so.
function ReadBy({ c }) {
  const labelOf = useModelLabel()
  const home = useTransformHome()
  const rb = c.read_by || { transforms: [], layers: [], models: c.used_by || [] }
  const pipelines = {}
  rb.layers.forEach(l => { (pipelines[l.pipeline] ||= []).push(l.layer) })
  const lines = [
    ...rb.transforms.map(t => (
      <li key={`t-${t.name}`}>
        The transform <TransformName name={t.name} home={home} /> ({t.tables.join(', ')})
      </li>
    )),
    ...Object.entries(pipelines).map(([p, steps]) => (
      <li key={`p-${p}`}>
        The pipeline <code>{p}</code>: {count(steps.length, 'step')} ({steps.map((s, i) => <Fragment key={s}>{i > 0 && ', '}<code>{s}</code></Fragment>)})
      </li>
    )),
    ...rb.models.map(m => (
      <li key={`m-${m}`}>The model <Link to={dataPath(m)}>{labelOf(m)}</Link>, which reads its tables</li>
    )),
  ]
  return lines.length
    ? <ul className="src-readby">{lines}</ul>
    : <p className="src-quiet">Nothing in this project reads it.</p>
}

// A table's row count as the table API counts it: exact, the catalog's
// estimate (~), or not counted where neither is cheap.
function rowsText(t) {
  if (t.rows == null) return 'not counted'
  return `${t.rows_exact === false ? '~' : ''}${Number(t.rows).toLocaleString('en-US')}`
}

// The connection's state here: reachable, or which variable it is waiting
// for (the credentials under it are where that is set).
function Reach({ name }) {
  const { data, isLoading } = useConnectorTables(name)
  if (isLoading) return <p className="src-quiet"><Spinner size={12} /> Connecting…</p>
  if (!data || data.connected) return null
  return (
    <p className="src-quiet src-reach" data-connected="false">
      Not connected here · {data.variable ? <>set <code>{data.variable}</code></> : data.reason}
    </p>
  )
}

// What the source holds, read when its detail opens: one row per table, its
// name the link to the table page. A connection that is not reachable says so
// once, in its Connection section above.
function Tables({ name }) {
  const { data, isLoading, error } = useConnectorTables(name)
  if (isLoading) return <p className="src-quiet"><Spinner size={12} /> Reading what it holds…</p>
  if (error) return <ErrorDetail error={error} />
  if (!data.connected) return <p className="src-quiet">Its tables are listed once it connects.</p>
  if (!data.tables) return <p className="src-quiet">{data.reason}</p>
  // TraceBi's own tables (the state store's) are never listed as data.
  const n = data.hidden_framework_tables || 0
  const hidden = n > 0 && <p className="src-quiet" title="TraceBi's own tables (tracebi_*, alembic_version) are not shown as data.">{count(n, 'framework table')} hidden</p>
  if (!data.tables.length) return <><p className="src-quiet">It holds no tables.</p>{hidden}</>
  return (
    <>
      <div className="whlist">
        <table className="tb-list">
          <thead>
            <tr>
              <th scope="col">Table</th>
              <th scope="col" className="num">Rows</th>
              <th scope="col" className="num">Columns</th>
            </tr>
          </thead>
          <tbody>
            {data.tables.map(t => (
              <tr key={t.name} data-table={t.name}>
                <td><Link to={tablePath(name, t.name)}><code>{t.name}</code></Link></td>
                <td className="num" title={t.rows != null && t.rows_exact === false ? "The catalog's estimate" : undefined}>{rowsText(t)}</td>
                <td className="num">{t.columns.length}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {hidden}
    </>
  )
}

// A source's name for people, large, with its identifier small beside it.
function SourceName({ c }) {
  return c.label
    ? <>{c.label} <code className="src-id">{c.name}</code></>
    : <code className="src-id src-id--only">{c.name}</code>
}

function ConnectorDetail({ c }) {
  const [code, setCode] = useState(false)
  if (!c) return (
    <Card>
      <Empty message="Select a source to see where its data is kept." />
    </Card>
  )
  return (
    <Card className="fade-in">
      <CardTitle action={(
        <Btn size="sm" variant="outline" onClick={() => setCode(v => !v)}>{code ? 'Hide code' : '</> View code'}</Btn>
      )}><SourceName c={c} /></CardTitle>
      <div style={{ display: 'flex', gap: 8, marginBottom: 18, flexWrap: 'wrap' }}>
        <Badge variant="gray" title={c.type}>{sourceKind(c)}</Badge>
      </div>
      <Section label="Where the data lives"><StorageLine storage={c.storage} /></Section>
      <Section label="Connection"><Reach name={c.name} /><Credentials connection={c} /></Section>
      <Section label="Read by"><ReadBy c={c} /></Section>
      <Section label="Tables"><Tables name={c.name} /></Section>
      {code && <div style={{ marginBottom: 18 }}><CodeView kind="connectors" name={c.name} /></div>}
    </Card>
  )
}

// One file under inputs/: its name (a data file's opens its table page), size,
// when it changed and which transforms name it.
function InputFile({ f, home }) {
  const name = f.path.replace(/^inputs\//, '')
  return (
    <li data-file={name}>
      {f.table ? <Link to={tablePath(INPUTS, name)}><code>{name}</code></Link> : <code>{name}</code>}
      <span className="wb-meta">{fmtBytes(f.size)} · changed {stamp(f.modified)}</span>
      <span className="src-files__by">
        {f.read_by.length
          ? <>Read by {f.read_by.map((t, i) => <span key={t}>{i > 0 && ', '}<TransformName name={t} home={home} /></span>)}</>
          : 'No transform names it'}
      </span>
    </li>
  )
}

// The project's inputs/ folder: its data files first (the ones a transform
// reads as a table), each with when it last changed and which transforms name
// it; scripts, notes and database files folded under them.
function InputsDetail({ files }) {
  const home = useTransformHome()
  const data = files.filter(f => f.table)
  const other = files.filter(f => !f.table)
  return (
    <Card className="fade-in">
      <CardTitle><code className="src-id src-id--only">inputs/</code></CardTitle>
      <div style={{ display: 'flex', gap: 8, marginBottom: 18, flexWrap: 'wrap' }}>
        <Badge variant="gray">Files</Badge>
      </div>
      <Section label="Where the data lives"><code style={{ fontSize: 12 }}>inputs/</code></Section>
      <Section label="Data files">
        {files.length === 0 ? <p className="src-quiet">The folder is empty.</p> : (
          <>
            {data.length > 0
              ? <ul className="src-files">{data.map(f => <InputFile key={f.path} f={f} home={home} />)}</ul>
              : <p className="src-quiet">No file here reads as a table (CSV, Parquet or JSON).</p>}
            {other.length > 0 && (
              <details className="wb-details src-other">
                <summary>{count(other.length, 'other file')}</summary>
                <ul className="src-files">{other.map(f => <InputFile key={f.path} f={f} home={home} />)}</ul>
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
 * Where the data comes from: every connection and the inputs/ folder
 * (/data/sources), or with a model only what its transform reads (?model=<m>,
 * or *model* on its own Sources tab). A warehouse is not a source: it is
 * under Warehouse, and one line here says so. The open source is in the
 * address (?source=<name>).
 */
export default function Connectors({ model: scoped }) {
  const [params, setParams] = useSearchParams()
  const model = scoped || params.get('model') || ''
  const { data, isLoading } = useConnectors()
  const { data: inputs } = useInputs()
  const { data: pipelines } = usePipelines()
  const labelOf = useModelLabel()
  const [query, setQuery] = useState('')

  const up = upstreamOf({ model, pipelines, connectors: data, inputs })
  const connectors = (data || []).filter(c => !c.warehouse && (!model || feedsModel(c, model, up)))
  const files = model ? up.files : (inputs?.files || [])
  const showInputs = !!inputs?.exists && (!model || files.length > 0)
  const q = query.toLowerCase()
  const filtered = connectors.filter(c =>
    [c.name, c.label || '', sourceKind(c)].some(x => x.toLowerCase().includes(q)))
  const inputsShown = showInputs && ('inputs files'.includes(q) || files.some(f => f.path.toLowerCase().includes(q)))
  // Open on the first source rather than a blank "select one" pane.
  const asked = params.get('source')
  const current = asked === INPUTS && showInputs ? INPUTS
    : (connectors.find(c => c.name === asked) || filtered[0])?.name || (inputsShown ? INPUTS : null)
  const select = name => setParams(p => { p.set('source', name); return p }, { replace: true })

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

  return (
    <>
      {model && !scoped && (
        <p className="scope-note">
          What {labelOf(model)} is made from: what its transform reads.{' '}
          <Link to={sourcesPath()}>Show every source</Link>
        </p>
      )}
      {!isLoading && connectors.length === 0 && !showInputs ? (
        <Empty message={model
          ? 'Its transform reads no connection or input file. The tables it is built on are under Warehouse.'
          : 'No sources yet. Declare a connection with tracebi connect, or put files under inputs/.'} />
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
            : <ConnectorDetail key={current} c={connectors.find(c => c.name === current)} />}
        />
      )}
      <p className="wb-meta src-pointer">
        The warehouse a transform writes is under <Link to={warehousePath(model)}>Warehouse</Link>.
      </p>
    </>
  )
}
