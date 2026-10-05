import { useId, useState } from 'react'
import { label as pointLabel } from '../pointMode'
import { summarize } from '../buildTimeline'
import { useLeaveNote, useProjectFeed } from '../api'
import { Btn, pressable } from './Shared'

// The builder's side of the loop, next to the report: what you are pointing at,
// the data the report reads and the checks on it, the pins and notes you have
// left for the agent, what the agent has shown you, and any binding that is
// broken right now. Everything here is dev-state under .tracebi/workbench/ and
// is shared with the agent over MCP.

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

// The note box: what you type is a pin the agent reads on its next pass (not
// live; it is not a chat).
function NoteBox({ name }) {
  const id = useId()
  const [text, setText] = useState('')
  const { mutate, isPending, error } = useLeaveNote(name)
  const submit = e => {
    e?.preventDefault()
    const note = text.trim()
    if (note) mutate(note, { onSuccess: () => setText('') })
  }
  return (
    <form className="wb-note-form" onSubmit={submit}>
      <label className="wb-hint" htmlFor={id}>
        Leave your agent a note. It reads notes on its next pass, not live.
      </label>
      <textarea id={id} rows={2} value={text} onChange={e => setText(e.target.value)}
                placeholder="e.g. split this by fund"
                onKeyDown={e => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) submit(e) }} />
      <div className="wb-actions">
        <Btn type="submit" size="sm" disabled={!text.trim() || isPending}>Leave note</Btn>
        {error && <span className="wb-error" role="alert">{error.message}</span>}
      </div>
    </form>
  )
}

function Pins({ pins, resolved, name }) {
  return (
    <Section title="Your notes" count={pins.length}>
      {pins.map(p => (
        <div key={p.id} className="wb-item">
          {/* A note is your own words; a pin on a figure names it. */}
          {p.kind !== 'message' && <div className="wb-item__head"><code>{p.id}</code></div>}
          <div>{(p.kind === 'message' ? p.note : p.request || p.note) || '—'}</div>
        </div>
      ))}
      {resolved.length > 0 && (
        <details className="wb-resolved">
          <summary>{resolved.length} resolved</summary>
          {[...resolved].reverse().map(p => (
            <div key={`${p.id}-${p.resolved_at}`} className="wb-item wb-item--done">
              {p.kind !== 'message' && <div className="wb-item__head"><code>{p.id}</code></div>}
              <div>{p.note}</div>
              {p.resolved_note && <div className="wb-reply">Agent: {p.resolved_note}</div>}
            </div>
          ))}
        </details>
      )}
      <NoteBox name={name} />
    </Section>
  )
}

// A few rows, as the report would write them. Shared by exhibits and the Data section.
function SampleTable({ cols, rows }) {
  if (!rows.length) return null
  return (
    <div className="wb-table-wrap">
      <table className="wb-table">
        <thead><tr>{cols.map(c => <th key={c}>{c}</th>)}</tr></thead>
        <tbody>{rows.map((r, i) => (
          <tr key={i}>{cols.map(c => <td key={c}>{String(r[c] ?? '')}</td>)}</tr>
        ))}</tbody>
      </table>
    </div>
  )
}

export function Exhibit({ ex }) {
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
      <SampleTable cols={cols} rows={rows} />
    </div>
  )
}

// What the report reads: each binding, the model it comes from, how big it is,
// the figures that use it, and a few rows.
function Data({ bindings }) {
  return (
    <Section title="Data" count={bindings.length}
             empty={!bindings.length && <p className="wb-empty">This report reads no data yet.</p>}>
      {bindings.map(b => (
        <div key={b.name} className="wb-item">
          <div className="wb-item__head">
            <code>{b.name}</code>
            {!b.error && <span className="wb-meta">{b.rows.toLocaleString()} × {b.columns.length}</span>}
          </div>
          <div className="wb-meta">
            {b.model ? `from ${b.model}` : 'computed in report.py'}
            {' · '}
            {b.used_by.length ? `used by ${b.used_by.join(', ')}` : 'no figure uses it'}
          </div>
          {b.error
            ? <div className="wb-item--bad">Not running: {b.error}</div>
            : b.sample.length > 0 && (
              <details className="wb-details">
                <summary>Sample rows</summary>
                <SampleTable cols={b.columns} rows={b.sample} />
              </details>
            )}
        </div>
      ))}
    </Section>
  )
}

// The lint the classic workbench ran, now beside the report. It points; the
// final build is what enforces.
function Checks({ checks }) {
  const { unbound_figures: unbound = [], unused_bindings: unused = [], numbers_outside_figures: loose = 0 } = checks || {}
  const found = [
    unbound.length > 0 && <>No data behind: <code>{unbound.join(', ')}</code></>,
    unused.length > 0 && <>No figure reads: <code>{unused.join(', ')}</code></>,
    loose > 0 && <>{loose} number{loose === 1 ? '' : 's'} typed in the text outside any figure</>,
  ].filter(Boolean)
  return (
    <Section title="Checks" count={found.length || null}
             empty={!found.length && (
               <p className="wb-empty">All clear: every figure has data behind it, every binding is
                 read, and no numbers are typed outside figures.</p>)}>
      {found.map((line, i) => <div key={i} className="wb-item">{line}</div>)}
      {found.length > 0 && <p className="wb-hint">These point; they do not block. The final build enforces.</p>}
    </Section>
  )
}

export default function Workbench({ pointed, onClearPointing, name, state, previewError, timeline }) {
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

      {state && <Checks checks={state.checks} />}
      {state && <Data bindings={state.bindings || []} />}

      <Pins pins={state?.pins || []} resolved={state?.resolved || []} name={name} />

      <Section title="From your agent" count={exhibits.length}
               empty={!exhibits.length && (
                 <p className="wb-empty">What your agent shows you while it works appears here.</p>)}>
        {exhibits.map(ex => <Exhibit key={ex.seq ?? ex.at} ex={ex} />)}
      </Section>

      <p className="wb-live">Live: refreshes when the report, its model or this feed changes.</p>
    </aside>
  )
}

// The same feed with no report open: what the agent shows you and the notes you
// leave it while it works on the transform and the model, before there is a
// report to build. Shown on the Reports page in dev mode.
export function ProjectFeed() {
  const { data } = useProjectFeed(true)
  const exhibits = data?.exhibits || []
  return (
    <div className="wb wb--project">
      <Pins pins={data?.pins || []} resolved={data?.resolved || []} name={null} />
      <Section title="From your agent" count={exhibits.length}
               empty={!exhibits.length && (
                 <p className="wb-empty">
                   What your agent shows you while it works appears here. A script it runs can
                   call <code>tracebi.workbench.show(df, note=…)</code> while this server is up.
                 </p>)}>
        {exhibits.map(ex => <Exhibit key={ex.seq ?? ex.at} ex={ex} />)}
      </Section>
    </div>
  )
}
