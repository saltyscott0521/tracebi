import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { pagePath } from '../nav'
import { ReactFlow, Background, Controls, Handle, Position, MarkerType } from '@xyflow/react'
import '@xyflow/react/dist/style.css'

import { Badge } from './Shared'
import { StorageLine } from './Storage'
import { layoutFlow, tracePath, NODE_W } from './lineageFlow'

// A report's lineage: where each number on the page came from, left to right.
// transform → stored tables → model → queries → figures. Select any node to
// light its path and read its detail underneath.

const KIND_LABEL = {
  transform: 'Transform', table: 'Stored table', model: 'Model',
  binding: 'Query', figures: 'Figures', unverified: 'Typed in',
}
const STATUS = {
  ok:      { stripe: '#16a34a', tint: 'var(--surface)' },
  warn:    { stripe: '#d97706', tint: 'var(--amber-lt)' },
  derived: { stripe: '#6d28d9', tint: 'var(--surface)' },
  muted:   { stripe: '#94a3b8', tint: 'var(--surface)' },
}
const MONO = 'Cascadia Code, Fira Code, monospace'

function FlowNode({ data }) {
  const st = STATUS[data.status] || STATUS.muted
  const dashed = data.status === 'derived' || data.kind === 'unverified'
  return (
    <div style={{
      width: NODE_W, boxSizing: 'border-box', background: st.tint, borderRadius: 10,
      border: `1.5px ${dashed ? 'dashed' : 'solid'} ${data.selected ? '#2563eb' : 'var(--border)'}`,
      borderLeft: `5px solid ${st.stripe}`, padding: '9px 12px', cursor: 'pointer',
      boxShadow: data.selected ? '0 0 0 2px #2563eb55' : 'var(--shadow-sm)',
      opacity: data.dim ? 0.28 : 1, transition: 'opacity .15s', height: data.height, overflow: 'hidden',
    }}>
      <Handle type="target" position={Position.Left} style={{ opacity: 0 }} />
      <div style={{ fontSize: 9, fontWeight: 700, letterSpacing: .6, textTransform: 'uppercase', color: 'var(--muted)' }}>
        {KIND_LABEL[data.kind]}
      </div>
      <div style={{ fontWeight: 700, fontSize: 12.5, color: 'var(--text)', margin: '2px 0', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {data.label}
      </div>
      <div style={{ fontSize: 10.5, color: 'var(--text-2)', fontFamily: data.kind === 'binding' ? MONO : undefined, lineHeight: 1.35,
        overflow: 'hidden', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' }}>
        {data.sub}
      </div>
      <Handle type="source" position={Position.Right} style={{ opacity: 0 }} />
    </div>
  )
}

function ColumnLabel({ data }) {
  return (
    <div style={{ width: NODE_W, fontSize: 10.5, fontWeight: 700, letterSpacing: .7, textTransform: 'uppercase',
      color: 'var(--muted)', borderBottom: '1px solid var(--border)', paddingBottom: 5 }}>
      {data.label}
    </div>
  )
}

const NODE_TYPES = { flowNode: FlowNode, colLabel: ColumnLabel }

// ── the graph ────────────────────────────────────────────────────────────────

function FlowGraph({ flow, selected, onSelect }) {
  const layout = useMemo(() => layoutFlow(flow), [flow])
  const path = useMemo(() => (selected ? tracePath(flow, selected) : null), [flow, selected])

  const nodes = useMemo(() => [
    ...layout.labels.map(l => ({
      id: l.id, type: 'colLabel', position: { x: l.x, y: 0 }, data: { label: l.label },
      draggable: false, selectable: false, focusable: false,
    })),
    ...layout.nodes.map(n => ({
      id: n.id, type: 'flowNode', position: n.position,
      data: { kind: n.kind, label: n.label, sub: n.sub, status: n.status, height: n.height,
              selected: n.id === selected, dim: !!path && !path.has(n.id) },
    })),
  ], [layout, selected, path])

  const edges = useMemo(() => flow.edges.map(e => {
    // An edge is on the path when both ends are — except the model's fan, which
    // is drawn from every table but only matters to the tables a query read.
    const on = !path || (path.has(e.source) && path.has(e.target))
    return {
      id: e.id, source: e.source, target: e.target, type: 'smoothstep',
      style: { stroke: on && path ? '#2563eb' : '#94a3b8', strokeWidth: on && path ? 2 : 1.3,
               strokeDasharray: e.dashed ? '5 4' : undefined, opacity: on ? 1 : 0.15 },
      markerEnd: { type: MarkerType.ArrowClosed, width: 11, height: 11, color: on && path ? '#2563eb' : '#94a3b8' },
    }
  }), [flow, path])

  return (
    <div className="erd-wrapper" style={{ height: Math.min(760, Math.max(380, layout.height * 0.8 + 40)) }}>
      <ReactFlow
        edgesFocusable={false}
        nodes={nodes} edges={edges} nodeTypes={NODE_TYPES}
        fitView fitViewOptions={{ padding: 0.06 }} minZoom={0.2}
        proOptions={{ hideAttribution: true }}
        nodesDraggable={false} nodesConnectable={false} elementsSelectable
        onNodeClick={(_, n) => { if (n.type === 'flowNode') onSelect(n.id === selected ? null : n.id) }}
        onPaneClick={() => onSelect(null)}
        onInit={f => setTimeout(() => f.fitView({ padding: 0.06 }), 350)}
      >
        <Background color="var(--flow-dots)" gap={30} size={1} />
        <Controls showInteractive={false} style={{ background: 'rgba(8,15,32,.9)', border: '1px solid var(--border)', borderRadius: 8 }} />
      </ReactFlow>
    </div>
  )
}

// ── detail ───────────────────────────────────────────────────────────────────

const H = { fontSize: 11, fontWeight: 600, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: .5, margin: '12px 0 6px' }
const short = h => (h ? `${h.slice(0, 12)}…` : '')

function Row({ label, children }) {
  return (
    <div style={{ display: 'flex', gap: 10, fontSize: 12.5, padding: '3px 0', alignItems: 'baseline' }}>
      <span style={{ width: 96, flexShrink: 0, color: 'var(--muted)' }}>{label}</span>
      <span style={{ minWidth: 0 }}>{children}</span>
    </div>
  )
}

function Detail({ node }) {
  const d = node.detail || {}
  return (
    <div className="fade-in" style={{ marginTop: 14, borderTop: '1px solid var(--border)', paddingTop: 12 }}>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
        <strong style={{ fontSize: 14 }}>{node.label}</strong>
        <Badge variant="gray">{KIND_LABEL[node.kind]}</Badge>
      </div>

      {node.kind === 'table' && (
        <>
          <Row label="Connector">{d.connector} <span style={{ color: 'var(--muted)' }}>({d.connector_type})</span></Row>
          <Row label="Stored at"><StorageLine storage={d.storage} /></Row>
          {d.rows != null && <Row label="Rows read">{d.rows}</Row>}
          {d.fingerprint && <Row label="Fingerprint"><code title={d.fingerprint} style={{ fontSize: 11.5 }}>{short(d.fingerprint)}</code></Row>}
          {d.contract && (
            <Row label="Written by">
              <code>{d.contract.transform}</code>{' '}
              <Badge variant={d.contract.status === 'satisfied' ? 'green' : 'amber'}>
                {d.contract.status === 'satisfied' ? 'sink satisfied its contract' : 'sink changed since'}
              </Badge>
            </Row>
          )}
        </>
      )}

      {node.kind === 'transform' && (
        <>
          <Row label="Wrote">{(d.tables || []).map(t => <Badge key={t} variant="gray" style={{ marginRight: 4 }}>{t}</Badge>)}</Row>
          <Row label="Sink">{d.sink} ({d.checks} check{d.checks !== 1 ? 's' : ''})</Row>
          {d.note && (
            <>
              <div style={H}>What the transform states</div>
              <div style={{ fontSize: 12.5, color: 'var(--text-2)', lineHeight: 1.55, maxWidth: '80ch' }}>{d.note}</div>
            </>
          )}
        </>
      )}

      {node.kind === 'model' && (
        <>
          <Row label="Facts">{(d.facts || []).map(f => <code key={f.table} style={{ marginRight: 8 }}>{f.table}</code>)}</Row>
          <Row label="Dimensions">{(d.dimensions || []).map(f => <code key={f.table} style={{ marginRight: 8 }}>{f.table}</code>)}</Row>
          {(d.joins || []).length > 0 && (
            <Row label="Joins">
              {d.joins.map(j => (
                <div key={`${j.from}${j.fromKey}${j.to}`} style={{ fontFamily: MONO, fontSize: 11.5 }}>
                  {j.from}.{j.fromKey} → {j.to}.{j.toKey}
                </div>
              ))}
            </Row>
          )}
          {d.sha256 && <Row label="Contract"><code title={d.sha256} style={{ fontSize: 11.5 }}>{short(d.sha256)}</code></Row>}
          <div style={{ marginTop: 8 }}>
            <Link to={pagePath('model', node.label)} style={{ fontSize: 12.5 }}>Open model →</Link>
          </div>
        </>
      )}

      {node.kind === 'binding' && (
        <>
          <Row label="Replayable">
            {d.verifiable
              ? <Badge variant="green">query-backed</Badge>
              : <Badge variant="purple">python-derived: cannot be replayed</Badge>}
          </Row>
          {d.rows != null && <Row label="Result">{d.rows} row{d.rows !== 1 ? 's' : ''} × {d.columns} column{d.columns !== 1 ? 's' : ''}</Row>}
          {d.query?.fact && <Row label="Fact"><code>{d.query.fact}</code></Row>}
          {d.query?.measures && <Row label="Measures"><code>{d.query.measures.join(', ')}</code></Row>}
          {d.query?.dimensions && <Row label="By"><code>{d.query.dimensions.join(', ')}</code></Row>}
          {d.query?.filters && <Row label="Filters"><code>{JSON.stringify(d.query.filters)}</code></Row>}
          {(d.tables || []).length > 0 && <Row label="Read">{d.tables.map(t => <Badge key={t} variant="gray" style={{ marginRight: 4 }}>{t}</Badge>)}</Row>}
          {(d.steps || []).length > 0 && (
            <>
              <div style={H}>Steps</div>
              <ol style={{ margin: 0, paddingLeft: 20, fontSize: 12, color: 'var(--text-2)', lineHeight: 1.7 }}>
                {d.steps.map((s, i) => (
                  <li key={i}><code style={{ fontSize: 11 }}>{s.operation}</code> {s.description}</li>
                ))}
              </ol>
            </>
          )}
        </>
      )}

      {(node.kind === 'figures' || node.kind === 'unverified') && (
        <div style={{ marginTop: 8, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {(d.figures || []).map(f => (
            <Badge key={f.id} variant="gray" title={f.note || f.cell || undefined}>
              {f.id} · {f.kind}{f.cell ? ` · ${f.cell}` : ''}{f.note ? ` · ${f.note}` : ''}
            </Badge>
          ))}
        </div>
      )}
    </div>
  )
}

// ── the tab ──────────────────────────────────────────────────────────────────

export function ReportLineage({ flow }) {
  const [selected, setSelected] = useState(null)
  const node = flow.nodes.find(n => n.id === selected)
  return (
    <div className="fade-in">
      <p style={{ fontSize: 12.5, color: 'var(--text-2)', margin: '0 0 10px', maxWidth: '78ch', lineHeight: 1.55 }}>
        Where each number on the page came from, read from this build's receipt.
        Select a node to trace it: its upstream and downstream light up.
      </p>
      <FlowGraph flow={flow} selected={selected} onSelect={setSelected} />
      {node
        ? <Detail node={node} />
        : <p style={{ fontSize: 11.5, color: 'var(--muted)', marginTop: 10 }}>
            {flow.summary.tables} stored table{flow.summary.tables !== 1 ? 's' : ''} · {flow.summary.queries} quer{flow.summary.queries !== 1 ? 'ies' : 'y'} · {flow.summary.figures} figure{flow.summary.figures !== 1 ? 's' : ''}
          </p>}
      {flow.notes.map(t => (
        <p key={t} style={{ fontSize: 11.5, color: 'var(--muted)', margin: '8px 0 0', maxWidth: '78ch' }}>{t}</p>
      ))}
    </div>
  )
}
