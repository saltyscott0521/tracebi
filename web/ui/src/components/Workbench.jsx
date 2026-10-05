import { label as pointLabel } from '../pointMode'
import { summarize } from '../buildTimeline'
import { pressable } from './Shared'

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

function Pointing({ pointed, onClear }) {
  if (!pointed) {
    return (
      <div className="point-note" role="status">
        Click a figure or an area in the report. Your agent will know what you mean
        by “this”. Esc clears.
      </div>
    )
  }
  return (
    <div className="point-note point-note--picked" role="status">
      <div><strong>Pointing at</strong> <code>{pointLabel(pointed)}</code></div>
      <div className="wb-hint">Your agent sees this. Ask it in chat: “make this a line chart”.</div>
      <div className="wb-actions"><button type="button" className="wb-link" onClick={onClear}>Clear</button></div>
    </div>
  )
}

const clock = at => new Date(at).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', second: '2-digit' })

// What each edit did, newest first. Pick a version to see the report as it was
// then; the latest is live.
function Timeline({ timeline }) {
  const { versions, viewed, view } = timeline
  const latest = versions.length ? versions[versions.length - 1].id : null
  return (
    <Section title="Changes" count={Math.max(versions.length - 1, 0)}
             empty={versions.length <= 1 && (
               <p className="wb-empty">When your agent changes the report, what changed appears here.</p>)}>
      {viewed && (
        <div className="wb-viewing" role="status">
          Showing the version from {clock(viewed.at)}.{' '}
          <button type="button" className="wb-link" onClick={() => view(null)}>Back to latest</button>
        </div>
      )}
      {[...versions].reverse().map((v, k, all) => {
        const first = k === all.length - 1
        const text = first ? 'Opened' : summarize(v.changes)
        const on = viewed ? viewed.id === v.id : v.id === latest
        return (
          <div key={v.id} className={`wb-item wb-version${on ? ' wb-version--on' : ''}`}
               {...pressable(() => view(v.id === latest ? null : v.id))}
               aria-current={on ? 'true' : undefined}>
            <div className="wb-item__head">
              <span>{text}</span>
              <span className="wb-meta">{clock(v.at)}{v.id === latest ? ' · latest' : ''}</span>
            </div>
          </div>
        )
      })}
    </Section>
  )
}

function Pins({ pins, resolved }) {
  if (!pins.length && !resolved.length) return null
  return (
    <Section title="Pins" count={pins.length}>
      {pins.map(p => (
        <div key={p.id} className="wb-item">
          <div className="wb-item__head"><code>{p.id}</code></div>
          <div>{p.request || p.note || '—'}</div>
        </div>
      ))}
      {resolved.length > 0 && (
        <details className="wb-resolved">
          <summary>{resolved.length} resolved</summary>
          {[...resolved].reverse().map(p => (
            <div key={`${p.id}-${p.resolved_at}`} className="wb-item wb-item--done">
              <div className="wb-item__head"><code>{p.id}</code></div>
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

export default function Workbench({ pointed, onClearPointing, state, previewError, timeline }) {
  const exhibits = state?.exhibits || []
  const broken = state?.broken || []
  return (
    <aside className="wb" aria-label="Workbench">
      <Pointing pointed={pointed} onClear={onClearPointing} />

      <Timeline timeline={timeline} />

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

      <Pins pins={state?.pins || []} resolved={state?.resolved || []} />

      <Section title="From your agent" count={exhibits.length}
               empty={!exhibits.length && (
                 <p className="wb-empty">What your agent shows you while it works appears here.</p>)}>
        {exhibits.map(ex => <Exhibit key={ex.seq ?? ex.at} ex={ex} />)}
      </Section>

      <p className="wb-live">Live: refreshes when the report, its model or this feed changes.</p>
    </aside>
  )
}
