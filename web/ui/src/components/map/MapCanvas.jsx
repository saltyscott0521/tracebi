import { Fragment } from 'react'

import { useConnectorWarehouse } from '../../api'
import { Flag, LineNode } from '../TheLine'
import { Verdict } from '../Shared'
import { NEVER, splitGlyph, tableLive, warehouseState } from './states'
import { count } from '../../format'
import './map.css'

// Draws a layout: edges in one SVG layer, nodes as absolutely positioned HTML
// above it. A node is the line's LineNode, so the Map and a model's line look
// alike and mark the same things the same way: a report's verdict chip, a flag
// for a failed transform or a table past its checks. A node that does
// something is a <button>; one that only says something is a labelled group,
// so a reader is never offered a control that does nothing.

function Chevron() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" aria-hidden="true">
      <path d="M9 6l6 6-6 6" />
    </svg>
  )
}

function Edges({ edges, width, height }) {
  return (
    <svg className="map-edges" width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-hidden="true" focusable="false">
      {edges.map((e, i) => (
        <g key={i} className={`map-edge map-edge--${e.tone}`}>
          <path d={e.d} fill="none" strokeWidth={e.width} />
          {e.heads.map((h, j) => (
            <polygon key={j} stroke="none" points={`${h.x - 7},${h.y - 5} ${h.x},${h.y} ${h.x - 7},${h.y + 5}`} />
          ))}
        </g>
      ))}
    </svg>
  )
}

// A state's tone, as the line's flag: failed, needs a look, not built.
const FLAG = { bad: 'bad', warn: 'warn', ghost: 'none' }

function MapNode({ node, label = node.label || '', tone = node.tone || 'quiet', onActivate }) {
  const { glyph, words } = splitGlyph(label)
  const note = node.note || ''
  const said = [words, note].filter(Boolean).join(', ')
  const aria = `${node.role}: ${node.name}${said ? ` (${said})` : ''}`
  const flag = !node.verdict && FLAG[tone] && words
  const marks = node.verdict ? [<Verdict key="v" state={node.verdict} detail={node.detail} size="sm" />]
    : flag ? [<Flag key="f" flag={{ kind: FLAG[tone], glyph, text: words }} />] : []
  return (
    <LineNode shape={node.shape} name={node.name} sans={node.sans} title={node.title} fact={!node.verdict && !flag ? words : null} marks={marks} note={note}
              tone={['hot', 'unused'].includes(tone) ? tone : ''} className="map-node" label={aria}
              style={{ left: node.x, top: node.y, width: node.w, height: node.h }}
              pressed={node.pressed} onClick={node.action ? () => onActivate(node) : undefined} />
  )
}

// The file a model reads, as a pill. The warehouse says whether it has been
// built and whether its sink checks still describe it; that arrives after the
// picture, so the pill leaves room for it.
function WarehouseNode({ node, onActivate }) {
  const { data } = useConnectorWarehouse(node.connector)
  const state = node.missing ? NEVER : warehouseState(data)
  const shared = node.others.length ? `shared with ${node.others.join(', ')}` : ''
  return <MapNode node={node} label={state ? state.label : shared} tone={state?.tone || 'quiet'} onActivate={onActivate} />
}

function TableNode({ node, onActivate }) {
  const { data } = useConnectorWarehouse(node.connector)
  const { rows, state } = tableLive(data, node.source)
  const counted = rows == null ? '' : count(rows, 'row')
  return <MapNode node={node} label={state ? state.label : counted} tone={state?.tone || (node.lit ? 'hot' : 'quiet')} onActivate={onActivate} />
}

const NODE = { warehouse: WarehouseNode, table: TableNode }

export default function MapCanvas({ layout, label, onActivate, onOpen }) {
  const { width, height } = layout
  const drawn = n => {
    const Node = NODE[n.role] || MapNode
    return <Node key={n.id} node={n} onActivate={onActivate} />
  }
  return (
    <div className="map-frame" role="region" aria-label={label}>
      <div className="map-level" key={layout.level} style={{ width, height }}>
        {layout.headers.map(h => (
          <div key={h.label} className="map-colh" style={{ left: h.x, top: h.y ?? 6 }}>
            {h.n && <span className="map-colh__n">{h.n}</span>}{h.label}
          </div>
        ))}

        {layout.bands?.map(b => (
          <div key={b.model} className={`map-band${b.tinted ? ' map-band--tinted' : ''}`}
               style={{ left: b.x, top: b.y, width: b.w, height: b.h }} />
        ))}
        {layout.card && (
          <div role="group" aria-label={`model: ${layout.card.label}`} className="map-modelcard"
               style={{ left: layout.card.x, top: layout.card.y, width: layout.card.w, height: layout.card.h }}>
            <div className="map-colh map-colh--in"><span className="map-colh__n">2</span>Model</div>
            <div className="map-modelcard__name" title={layout.card.name}>{layout.card.label}</div>
            {layout.card.empty && <p className="map-modelcard__empty">{layout.card.empty}</p>}
          </div>
        )}

        <Edges edges={layout.edges} width={width} height={height} />

        {layout.bands
          ? layout.bands.map(b => (
            <Fragment key={b.model}>
              <button type="button" className={`map-open${b.tinted ? ' map-open--tinted' : ''}`}
                      style={{ left: 22, top: b.y + 10 }} title={b.model} onClick={() => onOpen(b.model)}>
                <span><span className="sr-only">Open </span>{b.label}</span><Chevron />
              </button>
              {layout.nodes.filter(n => n.band === b.model).map(n => drawn(n))}
            </Fragment>
          ))
          : layout.nodes.map(n => drawn(n))}

        {[...(layout.bands || []).map(b => b.empty), layout.empty].filter(Boolean).flatMap(group => (
          Object.entries(group).filter(([, e]) => e).map(([key, e]) => (
            <p key={`${key}:${e.x}:${e.y}`} className="map-empty" style={{ left: e.x, top: e.y, width: e.w }}>{e.text}</p>
          ))
        ))}
      </div>
    </div>
  )
}
