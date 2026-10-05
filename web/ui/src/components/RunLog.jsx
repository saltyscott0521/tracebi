import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'

import { useRunLog } from '../api'
import { reportPagePath } from '../nav'
import { when } from './Attention'
import { Badge, Btn, Spinner } from './Shared'

// A pipeline's runs, and the output of the one you pick, as it is printed:
// every line the steps print, each stamped with the time since the run began.
// A run still going is followed; a finished one is read from the file it left.

const SHOWN = 3000            // lines drawn; Copy takes all of them
const LINE = /^(\d\d:\d\d\.\d)  (.*)$/

const STATUS = {
  running:   { variant: 'amber', label: 'Running' },
  succeeded: { variant: 'green', label: 'Succeeded' },
  failed:    { variant: 'red',   label: 'Failed' },
}

// "12.4s", "1m 04s"; a run still going has no end yet.
function took(run) {
  const ms = Date.parse(run.finished_at) - Date.parse(run.started_at)
  if (!(ms >= 0)) return run.status === 'running' ? '…' : '—'
  const s = ms / 1000
  return s < 60 ? `${s.toFixed(1)}s` : `${Math.floor(s / 60)}m ${String(Math.floor(s % 60)).padStart(2, '0')}s`
}

// Who ran it, and from where: a run from the command line says so.
const byWhom = run => `${run.actor ? `${run.actor} · ` : ''}${run.actor_role === 'cli' ? 'CLI' : 'app'}`

function tone(text) {
  if (/✗|^Run failed|\bTraceback\b|\bError\b/.test(text)) return 'bad'
  if (/✓|^Run succeeded/.test(text)) return 'ok'
  return ''
}

function Lines({ text }) {
  const rows = useMemo(() => {
    const all = text ? text.replace(/\n$/, '').split('\n') : []
    return { hidden: Math.max(all.length - SHOWN, 0), lines: all.slice(-SHOWN) }
  }, [text])
  return (
    <>
      {rows.hidden > 0 && <div className="runlog__note">{rows.hidden.toLocaleString()} earlier lines not shown. Copy has them all.</div>}
      {rows.lines.map((raw, i) => {
        const m = LINE.exec(raw)
        const body = m ? m[2] : raw
        return (
          <div key={i} className={`runlog__line ${tone(body) ? `runlog__line--${tone(body)}` : ''}`}>
            <span className="runlog__t">{m ? m[1] : ''}</span>
            <span className="runlog__text">{body || ' '}</span>
          </div>
        )
      })}
    </>
  )
}

function RunStatus({ status }) {
  const shown = STATUS[status]
  if (!shown) return <Badge variant="gray">…</Badge>
  return (
    <Badge variant={shown.variant}>
      {shown.variant === 'amber' && <><Spinner size={10} />{' '}</>}{shown.label}
    </Badge>
  )
}

/** The pipeline's runs, newest first, from the app and the command line alike. */
export function RunList({ runs, runId, onPick }) {
  return (
    <ul className="runlist" aria-label="Runs">
      {runs.map(r => {
        const selected = r.run_id === runId
        return (
          <li key={r.run_id}>
            <button type="button" onClick={() => onPick(r.run_id)}
              aria-current={selected ? 'true' : undefined}
              className={selected ? 'runlist__row' : 'runlist__row list-item-hover'}>
              <span><RunStatus status={r.status} /></span>
              <span>{when(r.started_at) || '—'}</span>
              <span className="runlist__took">{took(r)}</span>
              <span className="runlist__by">{byWhom(r)}</span>
              <span className="runlist__steps">{r.layers.join(' → ')}</span>
            </button>
          </li>
        )
      })}
    </ul>
  )
}

export default function RunLog({ pipeline, runs, runId, models, onDone }) {
  const log = useRunLog(pipeline, runId)
  const run = (runs || []).find(r => r.run_id === runId)
  const box = useRef(null)
  const [follow, setFollow] = useState(true)
  const [copied, setCopied] = useState(false)

  // Stay at the bottom while lines arrive, unless the reader scrolled up.
  useEffect(() => {
    const el = box.current
    if (el && follow) el.scrollTop = el.scrollHeight
  }, [log.text, follow])
  useEffect(() => { setFollow(true) }, [runId])
  useEffect(() => { if (log.done) onDone?.() }, [log.done])        // eslint-disable-line react-hooks/exhaustive-deps

  const onScroll = () => {
    const el = box.current
    if (el) setFollow(el.scrollHeight - el.scrollTop - el.clientHeight < 24)
  }
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(log.text)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch { /* clipboard blocked: the log is selectable */ }
  }

  if (!runId) {
    return (
      <p className="wb-empty" style={{ margin: 0 }}>
        Nothing has run yet. Run the pipeline or one of its steps, here or with
        tracebi run-pipeline, and each run appears here with its output.
      </p>
    )
  }

  return (
    <>
      <div className="runlog-wrap">
        <div className="runlog__bar">
          <RunStatus status={log.status || run?.status} />
          <span className="runlog__meta">
            {run ? `started ${when(run.started_at) || '—'} · ${byWhom(run)}` : ''}
          </span>
          <span style={{ marginLeft: 'auto' }}>
            <Btn size="sm" variant="outline" onClick={copy} disabled={!log.text}>{copied ? 'Copied' : 'Copy'}</Btn>
          </span>
        </div>

        {run?.error?.message && log.done && (
          <div className="runlog__error" role="alert">{run.error.message.split('\n')[0]}</div>
        )}
        {log.error && (
          <div className="runlog__error" role="alert">
            {log.error.status === 403
              ? 'Reading a run’s log needs the analyst role.'
              : `Could not read the log: ${log.error.message}`}
          </div>
        )}

        <div className="runlog" ref={box} onScroll={onScroll} role="log" aria-live="off" aria-label="Run output" tabIndex={0}>
          {log.expired
            ? <div className="runlog__note">This run’s log is no longer kept. The newest 30 runs of a pipeline are.</div>
            : log.text ? <Lines text={log.text} />
              : <div className="runlog__note">{log.done ? 'This run printed nothing.' : 'Waiting for output…'}</div>}
        </div>
        {!follow && (
          <button type="button" className="runlog__jump" onClick={() => { setFollow(true) }}>Jump to latest</button>
        )}
      </div>

      {run?.reports?.length > 0 && (
        <div className="runlog__reports">
          <span>Rebuilt</span>
          {run.reports.map(name => (
            <Link key={name} to={reportPagePath(name, models)} title={name}>{name.split('/').pop()}</Link>
          ))}
        </div>
      )}
    </>
  )
}
