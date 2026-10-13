// Build mode: a timeline of what the agent's edits did to the report.
//
// Each time the working render changes, the figures in it are read back out of
// the preview (the report runtime sends them when asked, once it has filled
// them in; the frame is sandboxed), compared with the version before, and the
// ones that changed flash in the report. Every version is kept (in memory, for this visit), so you can flip back to what it
// looked like before the agent's last change. Nothing here is saved or sent
// anywhere: it is a view.

import { useCallback, useEffect, useRef, useState } from 'react'
import { listenToFrame, tellFrame } from './frameBridge'

const KEEP = 8                 // versions kept (each is a whole page)
const SETTLE_MS = 450          // let the runtime fill the figures in before reading them

/** What differs between two snapshots: {changed: [{id, from, to}], added, removed}. */
export function diffFigures(prev, next) {
  const changed = []
  const added = []
  const removed = []
  for (const id of Object.keys(next)) {
    if (!(id in prev)) added.push(id)
    else if (prev[id].sig !== next[id].sig) changed.push({ id, kind: next[id].kind, from: prev[id].text, to: next[id].text })
  }
  for (const id of Object.keys(prev)) if (!(id in next)) removed.push(id)
  return { changed, added, removed }
}

/** One line for the person: what the edit did. */
export function summarize(changes) {
  const parts = []
  const { changed = [], added = [], removed = [] } = changes || {}
  for (const c of changed.slice(0, 2)) {
    parts.push(c.kind === 'value' && c.from && c.to ? `${c.id}: ${c.from} → ${c.to}` : `${c.id} changed`)
  }
  if (changed.length > 2) parts.push(`${changed.length - 2} more changed`)
  if (added.length) parts.push(`+${added.length} figure${added.length > 1 ? 's' : ''}`)
  if (removed.length) parts.push(`−${removed.length} figure${removed.length > 1 ? 's' : ''}`)
  if (!parts.length) parts.push('Re-rendered; no figure changed')
  return parts.join(' · ')
}

/**
 * Track the working render. Give it the current html (the latest preview) and
 * the preview frame; get back the versions seen, which one is on screen, and how
 * to look at an earlier one.
 */
export function useBuildTimeline({ html, frameRef, enabled }) {
  const [versions, setVersions] = useState([])     // oldest first: {id, at, html, snapshot, changes}
  const [viewedId, setViewedId] = useState(null)   // null = the latest
  const lastHtml = useRef(null)

  // A new render is a new version.
  useEffect(() => {
    if (!enabled || !html || html === lastHtml.current) return
    lastHtml.current = html
    setVersions(vs => [...vs, { id: vs.length ? vs[vs.length - 1].id + 1 : 1, at: Date.now(), html, snapshot: null, changes: null }]
      .slice(-KEEP))
  }, [enabled, html])

  // Once the latest version is on screen and settled, read its figures back out,
  // work out what changed since the version before, and flash those figures.
  const latestId = versions.length ? versions[versions.length - 1].id : null
  useEffect(() => {
    if (!enabled || latestId == null || viewedId != null) return undefined
    const frame = frameRef.current
    if (!frame) return undefined
    let timer
    // Ask once the page says it is up (or now, if it already was), after a beat.
    const ask = () => {
      clearTimeout(timer)
      timer = setTimeout(() => tellFrame(frame, { type: 'snapshot' }), SETTLE_MS)
    }
    const stop = listenToFrame(frame, m => {
      if (m.type === 'ready') { ask(); return }
      if (m.type !== 'snapshot') return
      const snapshot = m.figures || {}
      setVersions(vs => {
        const i = vs.findIndex(v => v.id === latestId)
        if (i < 0 || vs[i].snapshot) return vs
        const prev = vs[i - 1]
        const changes = prev?.snapshot ? diffFigures(prev.snapshot, snapshot) : null
        if (changes) tellFrame(frame, { type: 'flash', ids: [...changes.changed.map(c => c.id), ...changes.added] })
        const next = vs.slice()
        next[i] = { ...vs[i], snapshot, changes }
        return next
      })
    })
    ask()
    return () => { clearTimeout(timer); stop() }
  }, [enabled, latestId, viewedId, frameRef])

  const view = useCallback(id => setViewedId(id), [])
  const reset = useCallback(() => {
    lastHtml.current = null
    setVersions([])
    setViewedId(null)
  }, [])

  const viewed = viewedId == null ? null : versions.find(v => v.id === viewedId) || null

  return {
    versions,
    viewed,
    isLatest: !viewed,
    shownHtml: viewed ? viewed.html : html,
    view,
    reset,
  }
}
