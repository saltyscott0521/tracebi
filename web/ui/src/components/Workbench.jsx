import { useState } from 'react'

import { useAddPin, useRemovePin } from '../api'
import { label as pointLabel } from '../pointMode'
import { Btn } from './Shared'

// The builder's side of the loop, next to the report: what you are pointing at,
// the pins you have left for the agent, what the agent has shown you, and any
// binding that is broken right now. Everything here is dev-state under
// .tracebi/workbench/<report>/ and is shared with the agent over MCP.

function Section({ title, count, children, empty }) {
  return (
    <section className="wb-section">
      <h3 className="wb-section__title">
        {title}
        {count != null && <span className="wb-section__count">{count}</span>}
      </h3>
      {children}
      {empty}
    </section>
  )
}

function Pointing({ name, pointed, onClear }) {
  const [note, setNote] = useState('')
  const add = useAddPin(name)
  if (!pointed) {
    return (
      <div className="point-note" role="status">
        Click a figure or an area in the report. Your agent will know what you mean
        by “this”. Esc clears.
      </div>
    )
  }
  const pin = () => {
    if (!note.trim()) return
    add.mutate(note.trim(), { onSuccess: () => setNote('') })
  }
  return (
    <div className="point-note point-note--picked" role="status">
      <div>
        <strong>Pointing at</strong> <code>{pointLabel(pointed)}</code>
      </div>
      <div className="wb-hint">
        Your agent sees this. Ask it in chat (“make this a line chart”), or leave it a note:
      </div>
      <textarea
        className="wb-note" rows={2} value={note}
        placeholder="What should change here?"
        aria-label="Note for the agent"
        onChange={e => setNote(e.target.value)}
        onKeyDown={e => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) pin() }}
      />
      <div className="wb-actions">
        <Btn size="sm" onClick={pin} disabled={!note.trim() || add.isPending}>Pin for the agent</Btn>
        <button type="button" className="wb-link" onClick={onClear}>Clear</button>
      </div>
      {add.error && <div className="wb-error">{add.error.message}</div>}
    </div>
  )
}

function Pins({ name, pins, resolved }) {
  const remove = useRemovePin(name)
  return (
    <Section title="Pins" count={pins.length}
             empty={!pins.length && !resolved.length && (
               <p className="wb-empty">Pins you leave appear here, and your agent resolves them.</p>)}>
      {pins.map(p => (
        <div key={p.id} className="wb-item">
          <div className="wb-item__head">
            <code>{p.target ? pointLabel(p.target) : p.id}</code>
            <button type="button" className="wb-link" onClick={() => remove.mutate(p.id)}>Unpin</button>
          </div>
          <div>{p.request || p.note || '—'}</div>
        </div>
      ))}
      {resolved.length > 0 && (
        <details className="wb-resolved">
          <summary>{resolved.length} resolved</summary>
          {[...resolved].reverse().map(p => (
            <div key={`${p.id}-${p.resolved_at}`} className="wb-item wb-item--done">
              <div className="wb-item__head"><code>{p.target ? pointLabel(p.target) : p.id}</code></div>
              <div>{p.note}</div>
              {p.resolved_note && <div className="wb-reply">Agent: {p.resolved_note}</div>}
            </div>
          ))}
        </details>
      )}
    </Section>
  )
}

function Exhibit({ ex }) {
  const rows = (ex.display?.length ? ex.display : ex.rows || []).slice(0, 5)
  const cols = ex.columns || (rows[0] ? Object.keys(rows[0]) : [])
  return (
    <div className={`wb-item${ex.changed ? ' wb-item--changed' : ''}`}>
      <div className="wb-item__head">
        <code>{ex.name || ex.kind}</code>
        {ex.shape && <span className="wb-meta">{ex.shape[0]} × {ex.shape[1]}</span>}
      </div>
      {ex.html
        // Pre-escaped markdown from the server (the workbench's own safe subset).
        ? <div className="wb-note-html" dangerouslySetInnerHTML={{ __html: ex.html }} />
        : (ex.note || ex.text) && <div>{ex.note || ex.text}</div>}
      {ex.kind === 'chart' && ex.recipe && (
        <div className="wb-meta">chart: {ex.recipe.chart} · {ex.recipe.x} by {[].concat(ex.recipe.y).join(', ')}</div>
      )}
      {rows.length > 0 && (
        <div className="wb-table-wrap">
          <table className="wb-table">
            <thead><tr>{cols.map(c => <th key={c}>{c}</th>)}</tr></thead>
            <tbody>{rows.map((r, i) => (
              <tr key={i}>{cols.map(c => <td key={c}>{String(r[c] ?? '')}</td>)}</tr>
            ))}</tbody>
          </table>
        </div>
      )}
    </div>
  )
}

export default function Workbench({ name, pointed, onClearPointing, state, previewError }) {
  const pins = state?.pins || []
  const resolved = state?.resolved || []
  const exhibits = state?.exhibits || []
  const broken = state?.broken || []
  return (
    <aside className="wb" aria-label="Workbench">
      <Pointing name={name} pointed={pointed} onClear={onClearPointing} />

      {(previewError || broken.length > 0) && (
        <Section title="Needs a look" count={broken.length + (previewError ? 1 : 0)}>
          {previewError && <div className="wb-item wb-item--bad">{previewError.message}</div>}
          {broken.map(b => (
            <div key={b.binding} className="wb-item wb-item--bad">
              <code>{b.binding}</code>
              <div>{b.error.split('\n')[0]}</div>
            </div>
          ))}
        </Section>
      )}

      <Pins name={name} pins={pins} resolved={resolved} />

      <Section title="From your agent" count={exhibits.length}
               empty={!exhibits.length && (
                 <p className="wb-empty">What your agent shows you while it works appears here.</p>)}>
        {exhibits.map(ex => <Exhibit key={ex.seq ?? ex.at} ex={ex} />)}
      </Section>

      <p className="wb-live">Live: refreshes when the report, its model or this feed changes.</p>
    </aside>
  )
}
