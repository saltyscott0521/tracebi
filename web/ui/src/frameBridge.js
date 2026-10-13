// The app's side of the report frame.
//
// A report runs custom script, so every frame that shows one is sandboxed with
// an opaque origin: no cookies, no app API, no way to reach window.parent's
// DOM. That also means the app cannot read the frame's DOM. The report runtime
// (tracebi.js, "Host bridge") and the app talk by postMessage instead, and only
// about presentation: how tall the report is, which figures it holds, what the
// person pointed at, which cut to apply.
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
 * Run the selections a report frame asks for, as the signed-in viewer. The frame
 * has no network of its own. Only the report this frame is showing may ask, and
 * only for filters (never a free-text question, which can change the package).
 * *run(filters)* resolves to the payload.
 */
export function answerSelections(frame, report, run) {
  return listenToFrame(frame, m => {
    if (m.type !== 'selection-request' || m.report !== report) return
    run(m.filters && typeof m.filters === 'object' ? m.filters : {}).then(
      payload => tellFrame(frame, { type: 'selection-response', id: m.id, ok: true, payload }),
      () => tellFrame(frame, { type: 'selection-response', id: m.id, ok: false }),
    )
  })
}

/** Send a command to the report running in *frame*. */
export function tellFrame(frame, message) {
  // An opaque origin cannot be named as a target; the command carries nothing secret.
  frame?.contentWindow?.postMessage({ ...message, tracebiFrame: 1 }, '*')
}
