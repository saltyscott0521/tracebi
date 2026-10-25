// The app's side of the report frame.
//
// A report runs custom script, so every frame that shows one is sandboxed with
// an opaque origin: no cookies, no app API, no way to reach window.parent's
// DOM. That also means the app cannot read the frame's DOM. The report runtime
// (tracebi.js, "Host bridge") and the app talk by postMessage instead, and only
// about presentation: how tall the report is, which figures it holds, which
// one the reader clicked (`figure`, its id only: the trace beside the page
// follows it), what the person pointed at, what its selection is, and what the
// app's check says of it.
//
// A message counts only if it came from this frame's own window (its origin is
// "null", so the origin is no use) and carries the bridge tag.

/** What a report frame may do: run its own script, and save a CSV. Nothing else:
 *  not same-origin, not popups, not top navigation, not forms. */
export const FRAME_SANDBOX = 'allow-scripts allow-downloads'

/** Call handler(message) for each bridge message from *frame*. Returns a stop function. */
export function listenToFrame(frame, handler) {
  const on = e => {
    const m = e.data
    if (e.source !== frame.contentWindow || !m || m.tracebiFrame !== 1) return
    handler(m)
  }
  window.addEventListener('message', on)
  return () => window.removeEventListener('message', on)
}

/**
 * Follow a live report's selection. The page recomputes its own figures from
 * the data it carries (tracebi.js, "The live page"); it tells the app the state
 * after every change, so the header can say so. *handler* gets
 * `{ selection: {field: [values]}, local, authored, figures }`.
 */
export function followSelection(frame, handler) {
  return listenToFrame(frame, m => {
    if (m.type === 'tracebi-selection' && m.payload && typeof m.payload === 'object') handler(m.payload)
  })
}

/** Set the selection of the live report in *frame* (`{}` is the authored view). */
export function setFrameSelection(frame, selection) {
  tellFrame(frame, { type: 'tracebi-set-selection', selection })
}

/** Send a command to the report running in *frame*. */
export function tellFrame(frame, message) {
  // An opaque origin cannot be named as a target; the command carries nothing secret.
  frame?.contentWindow?.postMessage({ ...message, tracebiFrame: 1 }, '*')
}

// The states a report's chip can be told. Draft and Never built are the app's
// own words for a page that is not a build.
const TOLD = new Set(['reproduces', 'needs-a-look', 'does-not-reproduce', 'not-checked'])

/**
 * Tell the report in *frame* the app's verdict on the build it shows, now and
 * each time a page in the frame says it is up, so its masthead chip and its
 * receipt say what the app says instead of the file's own "Not checked".
 * *verdict* is exactly what verdictOf computed ({ state, detail }); nothing
 * else is ever sent, and no verdict sends nothing. hosted: true tells it the
 * app's header shows the build time and verdict, so its masthead keeps only
 * the Receipt link. Returns a stop function.
 */
export function tellVerdict(frame, verdict) {
  if (!frame || !TOLD.has(verdict?.state)) return () => {}
  const say = () => tellFrame(frame, {
    type: 'tracebi:verdict', state: verdict.state, detail: verdict.detail || '', hosted: true })
  const stop = listenToFrame(frame, m => { if (m.type === 'ready') say() })
  say()
  return stop
}
