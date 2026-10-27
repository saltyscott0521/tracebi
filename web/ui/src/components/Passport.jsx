import { Link } from 'react-router-dom'

import { useRole, useStartPipelineRun, useTransforms, useWarehouses } from '../api'
import { count } from '../format'
import { movedWords } from '../words'
import { warehousePath } from '../nav'
import { ExportTo } from './DataGrid'
import { Btn, BtnLink, Chip, useToast } from './Shared'

// The passport: the same rows on every piece of the project, so a CSV, a CRM
// table, a transform, a warehouse table, a model and a report answer the same
// questions in the same words (design/control-tower.md). What it is (the
// head), then From · Read by (Writes for a transform, Written by for a
// warehouse table or group) · Last moved · Trust · Agents. The map shows one
// beside it; a source's page opens with the same rows.

// What each kind of node is called, as the passport's eyebrow says it.
export const KIND_WORD = {
  source: 'Source', file: 'Input file', source_table: 'Source table', transform: 'Transform',
  group: 'Warehouse group', table: 'Warehouse table', model: 'Model', report: 'Report',
}

// A state from the graph (ok · warn · bad · none) as the app's chip tone.
export const TONE = { ok: '', warn: 'warn', bad: 'bad', none: 'none' }

/** The second row's word: what a transform writes, who wrote a table, else who reads it. */
export function linksRow(kind) {
  if (kind === 'transform') return 'Writes'
  if (kind === 'group' || kind === 'table') return 'Written by'
  return 'Read by'
}

/** The five rows under the head, each `[term, value]`, in their order. */
export function PassportRows({ rows }) {
  return (
    <dl className="pass__rows">
      {rows.map(([dt, dd]) => (
        <div key={dt} className="pass__row" data-row={dt}>
          <dt>{dt}</dt><dd>{dd ?? <span className="pass__none">—</span>}</dd>
        </div>
      ))}
    </dl>
  )
}

/** A state and its words, as a chip (the text exactly as the graph gives it). */
export function StateChip({ state }) {
  if (!state?.text) return null
  return <Chip tone={TONE[state.state] ?? 'none'}>{state.text}</Chip>
}

// Other nodes, each a link that selects it on the map.
function NodeLinks({ ids, byId, onGo }) {
  return ids.map((id, i) => {
    const n = byId[id]
    return (
      <span key={id}>
        {i > 0 && ', '}
        <a href={`?node=${encodeURIComponent(id)}`} className="pass__go" data-go={id}
           onClick={e => { e.preventDefault(); onGo(id) }}>{n ? n.label : id}</a>
      </span>
    )
  })
}

// The warehouse browser's id for what *transform* wrote (<warehouse>:<contract>),
// the group Zoom to schema selects there.
function groupId(warehouses, transform) {
  for (const w of warehouses?.warehouses || []) {
    const wr = (w.writers || []).find(x => x.transform === transform)
    if (wr) return `${w.name}:${wr.contract}`
  }
  return null
}

// Refresh data: the pipeline that runs the transform, started here; an
// admin's action, as on the transform's own page.
function Refresh({ pipeline, name }) {
  const start = useStartPipelineRun()
  const toast = useToast()
  return (
    <Btn size="sm" variant="outline" disabled={start.isPending}
         onClick={() => start.mutate({ pipeline }, {
           onSuccess: () => toast?.(`Refreshing ${name}: its page shows the run`, 'success'),
           onError: e => toast?.(e.message || 'Refresh failed', 'error'),
         })}>
      {start.isPending ? 'Starting…' : 'Refresh data'}
    </Btn>
  )
}

// What can be done to the node from here, by kind: Open, Zoom to schema, and
// an admin's Setup…, Refresh data and Export to….
function Actions({ n, onSetup }) {
  const role = useRole()
  const admin = role === 'admin'
  const { data: warehouses } = useWarehouses()
  const { data: transforms } = useTransforms()
  let zoom = null
  if (n.kind === 'model') zoom = n.open
  if (n.kind === 'group') {
    const id = groupId(warehouses, n.name)
    zoom = id ? `${warehousePath()}?group=${encodeURIComponent(id)}` : n.open
  }
  const pipeline = n.kind === 'transform' && (transforms || []).find(t => t.name === n.name)?.pipelines?.[0]
  const holder = n.kind === 'table'
    && (warehouses?.warehouses || []).find(w => w.tables.some(t => t.name === n.name))?.name
  return (
    <div className="pass__acts">
      {zoom && <BtnLink size="sm" variant="primary" to={zoom}>Zoom to schema</BtnLink>}
      {n.open && n.open !== zoom && <BtnLink size="sm" variant={zoom ? 'outline' : 'primary'} to={n.open}>Open</BtnLink>}
      {n.kind === 'source' && admin && onSetup && <Btn size="sm" variant="outline" onClick={() => onSetup(n.name)}>Setup…</Btn>}
      {pipeline && admin && <Refresh pipeline={pipeline} name={n.name} />}
      {holder && <ExportTo source={holder} table={n.name} />}
    </div>
  )
}

/**
 * One node's passport: *n* a graph node, *byId* every node by id, *onGo(id)*
 * selects another (a reader or a writer), *onSetup(name)* opens a source's
 * Setup sheet. *from*, for a warehouse table, is the source tables and files
 * its columns come from (the graph's proven edges): From lists them.
 */
export function NodePassport({ n, byId, onGo, onSetup, from }) {
  const p = n.passport || {}
  const linked = n.kind === 'group' || n.kind === 'table' ? p.writers || [] : p.readers || []
  return (
    <div className="pass__body" data-passport={n.id}>
      <p className="pass__eyebrow">
        {KIND_WORD[n.kind] || n.kind}{n.chip && n.chip.toLowerCase() !== (KIND_WORD[n.kind] || '').toLowerCase() && ` · ${n.chip}`}
      </p>
      <h2 className="pass__name" title={n.name}>{n.label}</h2>
      {(n.gap || n.sub) && <p className="pass__sub">{n.gap ? <Chip tone="warn">{n.gap.reason}</Chip> : n.sub}</p>}
      <PassportRows rows={[
        ['From', from?.length ? <NodeLinks ids={from} byId={byId} onGo={onGo} />
          : p.origin ? <code>{p.origin}</code> : null],
        [linksRow(n.kind), linked.length
          ? <NodeLinks ids={linked} byId={byId} onGo={onGo} />
          : n.kind === 'report' ? 'People, and the share link' : <Chip tone="warn">Nobody · a gap</Chip>],
        ['Last moved', movedWords(p.moved, n.kind)],
        ['Trust', <StateChip state={p.trust} />],
        ['Agents', <StateChip state={p.agents} />],
      ]} />
      <Actions n={n} onSetup={onSetup} />
      {n.gap && <p className="pass__hint">A gap: wired on one side only. It stays amber until something reads it or it is removed.</p>}
    </div>
  )
}

// The project's rows, when nothing is selected: a count per lane, each a link
// that focuses that lane on the map, and the gaps, which open Coverage.
const PROJECT_ROWS = [
  ['Sources', 'sources', 'source'], ['Transforms', 'transforms', 'transform'], ['Tables', 'warehouse', 'table'],
  ['Models', 'models', 'model'], ['Reports', 'reports', 'report'],
]

/** The project's passport: *summary* from the graph, *focus(lane)* / *lens(name)* move the map. */
export function ProjectPassport({ summary, focus, coverage }) {
  return (
    <div className="pass__body" data-passport="project">
      <p className="pass__eyebrow">Project</p>
      <h2 className="pass__name">Everything, wired</h2>
      <p className="pass__sub">Select any piece for its passport: the same rows on every one.</p>
      <dl className="pass__rows">
        {PROJECT_ROWS.map(([dt, lane, word]) => (
          <div key={dt} className="pass__row" data-row={dt}>
            <dt>{dt}</dt>
            <dd><Link to={`?lane=${lane}`} onClick={e => { e.preventDefault(); focus(lane) }}>{count(summary[dt.toLowerCase()] ?? 0, word)}</Link></dd>
          </div>
        ))}
        <div className="pass__row" data-row="Gaps">
          <dt>Gaps</dt>
          <dd>
            {summary.gaps
              ? <Link to="?lens=coverage" className="pass__gaps" onClick={e => { e.preventDefault(); coverage() }}>{count(summary.gaps, 'gap')}</Link>
              : 'None: everything is wired on both sides'}
          </dd>
        </div>
      </dl>
    </div>
  )
}
