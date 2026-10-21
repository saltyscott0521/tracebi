import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useConnectors, useConnectorTables, useInputs, usePipelines } from '../api'
import { StorageLine, sourceKind, fmtBytes } from '../components/Storage'
import { useModelLabel } from '../components/Scope'
import CodeView from '../components/CodeView'
import { stamp } from '../components/TheLine'
import { feedsModel, upstreamOf } from '../chain'
import { dataPath, pipelineModels, sourcesPath, warehousePath } from '../nav'
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
// line or a load_source call), the pipeline layers whose source it is, and
// the models that read it directly. Read from the files, so a source nothing
// names says so.
function ReadBy({ c }) {
  const labelOf = useModelLabel()
  const home = useTransformHome()
  const rb = c.read_by || { transforms: [], layers: [], models: c.used_by || [] }
  const lines = [
    ...rb.transforms.map(t => (
      <li key={`t-${t.name}`}>
        <TransformName name={t.name} home={home} /> ({t.tables.join(', ')})
      </li>
    )),
    ...rb.layers.map(l => (
      <li key={`l-${l.pipeline}-${l.layer}`}>the step <code>{l.layer}</code> of the pipeline <code>{l.pipeline}</code></li>
    )),
    ...rb.models.map(m => (
      <li key={`m-${m}`}><Link to={dataPath(m)}>{labelOf(m)}</Link>, which reads its tables</li>
    )),
  ]
  return lines.length
    ? <ul className="src-readby">{lines}</ul>
    : <p className="src-quiet">Nothing in this project reads it.</p>
}

// What the source holds, read when its detail opens. A connection whose
// variable is unset here, or that refuses, says so quietly: not an error.
function Tables({ name }) {
  const { data, isLoading, error } = useConnectorTables(name)
  if (isLoading) return <p className="src-quiet"><Spinner size={12} /> Reading what it holds…</p>
  if (error) return <ErrorDetail error={error} />
  if (!data.connected) {
    return (
      <p className="src-quiet" data-connected="false">
        Not connected here · {data.variable ? <>set <code>{data.variable}</code></> : data.reason}
      </p>
    )
  }
  if (!data.tables) return <p className="src-quiet">{data.reason}</p>
  if (!data.tables.length) return <p className="src-quiet">It holds no tables.</p>
  return (
    <div className="src-tables">
      {data.tables.map(t => (
        <details key={t.name} className="wb-details">
          <summary>
            <code>{t.name}</code>{' '}
            <span className="wb-meta">
              {[t.rows != null && `${t.rows.toLocaleString()} ${t.rows === 1 ? 'row' : 'rows'}`,
                `${t.columns.length} ${t.columns.length === 1 ? 'column' : 'columns'}`].filter(Boolean).join(' · ')}
            </span>
          </summary>
          <ul className="src-columns">
            {t.columns.map(col => <li key={col.name}><code>{col.name}</code> <span>{col.type}</span></li>)}
          </ul>
        </details>
      ))}
    </div>
  )
}

function ConnectorDetail({ c }) {
  const [code, setCode] = useState(false)
  if (!c) return (
    <Card>
      <Empty message="Select a source to see where its data is kept." />
    </Card>
  )
  const isWarehouse = c.type === 'DuckDBConnector' && c.storage?.kind === 'file'
  return (
    <Card className="fade-in">
      <CardTitle action={(
        <span style={{ display: 'inline-flex', gap: 6 }}>
          {isWarehouse && <Link className="btn src-open" to={`${warehousePath()}#wh-${c.name}`}>Open in Warehouse</Link>}
          <Btn size="sm" variant="outline" onClick={() => setCode(v => !v)}>{code ? 'Hide code' : '</> View code'}</Btn>
        </span>
      )}>{c.name}</CardTitle>
      <div style={{ display: 'flex', gap: 8, marginBottom: 18, flexWrap: 'wrap' }}>
        <Badge variant="gray" style={{ textTransform: 'none' }} title={c.type}>{sourceKind(c)}</Badge>
      </div>
      <Section label="Where the data lives"><StorageLine storage={c.storage} /></Section>
      <Section label="Read by"><ReadBy c={c} /></Section>
      <Section label="Tables"><Tables name={c.name} /></Section>
      {code && <div style={{ marginBottom: 18 }}><CodeView kind="connectors" name={c.name} /></div>}
    </Card>
  )
}

// The project's inputs/ folder: the files the transforms read, each with
// when it last changed and which transforms name it.
function InputsDetail({ files }) {
  const home = useTransformHome()
  return (
    <Card className="fade-in">
      <CardTitle>inputs/</CardTitle>
      <div style={{ display: 'flex', gap: 8, marginBottom: 18, flexWrap: 'wrap' }}>
        <Badge variant="gray" style={{ textTransform: 'none' }}>Files</Badge>
      </div>
      <Section label="Where the data lives"><code style={{ fontSize: 12 }}>inputs/</code></Section>
      <Section label="Files">
        {files.length === 0 ? <p className="src-quiet">The folder is empty.</p> : (
          <ul className="src-files">
            {files.map(f => (
              <li key={f.path}>
                <code>{f.path.replace(/^inputs\//, '')}</code>
                <span className="wb-meta">{fmtBytes(f.size)} · changed {stamp(f.modified)}</span>
                <span className="src-files__by">
                  {f.read_by.length
                    ? <>Read by {f.read_by.map((t, i) => <span key={t}>{i > 0 && ', '}<TransformName name={t} home={home} /></span>)}</>
                    : 'No transform names it'}
                </span>
              </li>
            ))}
          </ul>
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
 * (/data/sources), or with a model only what it is made from, its warehouse
 * and what its transform reads (?model=<m>, or *model* on its own Sources
 * tab). The open source is in the address (?source=<name>).
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
  const connectors = (data || []).filter(c => !model || feedsModel(c, model, up))
  const files = model ? up.files : (inputs?.files || [])
  const showInputs = !!inputs?.exists && (!model || files.length > 0)
  const q = query.toLowerCase()
  const filtered = connectors.filter(c =>
    c.name.toLowerCase().includes(q) || sourceKind(c).toLowerCase().includes(q))
  const inputsShown = showInputs && ('inputs files'.includes(q) || files.some(f => f.path.toLowerCase().includes(q)))
  // Open on the first source rather than a blank "select one" pane.
  const asked = params.get('source')
  const current = asked === INPUTS && showInputs ? INPUTS
    : (connectors.find(c => c.name === asked) || filtered[0])?.name || (inputsShown ? INPUTS : null)
  const select = name => setParams(p => { p.set('source', name); return p }, { replace: true })

  const readers = c => [
    ...(c.read_by?.transforms || []).map(t => <Badge key={`t-${t.name}`} variant="gray" style={{ textTransform: 'none' }}>{t.name}</Badge>),
    ...(c.used_by || []).map(m => <Badge key={`m-${m}`} variant="gray" style={{ textTransform: 'none' }}>{labelOf(m)}</Badge>),
  ]

  return (
    <>
      {model && !scoped && (
        <p className="scope-note">
          What {labelOf(model)} is made from: its warehouse, and what its transform reads.{' '}
          <Link to={sourcesPath()}>Show every source</Link>
        </p>
      )}
      {!isLoading && connectors.length === 0 && !showInputs ? (
        <Empty message={model
          ? 'This model reads no source, so its tables have no data behind them. Its file names one under connectors.'
          : 'No sources yet. Declare a connection with tracebi connect, or a model names its own.'} />
      ) : (
        <SplitLayout
          left={
            isLoading ? <SkeletonList /> : (
              <>
                <SearchInput value={query} onChange={setQuery} placeholder="Search sources…" />
                {filtered.length === 0 && !inputsShown
                  ? <Empty message="No matches." />
                  : (
                    <>
                      {filtered.map(c => (
                        <div key={c.name} data-source={c.name}>
                          <ListItem
                            selected={current === c.name}
                            onClick={() => select(c.name)}
                            name={c.name}
                            sub={sourceKind(c)}
                            meta={readers(c).length ? readers(c) : null}
                          />
                        </div>
                      ))}
                      {inputsShown && (
                        <div data-source={INPUTS}>
                          <ListItem
                            selected={current === INPUTS}
                            onClick={() => select(INPUTS)}
                            name="inputs/"
                            sub={`Files · ${files.length} ${files.length === 1 ? 'file' : 'files'}`}
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
    </>
  )
}
