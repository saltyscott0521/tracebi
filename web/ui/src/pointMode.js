// Build mode: point at something in a report.
//
// The pointing itself happens inside the report's own frame (the report runtime,
// tracebi.js "Build mode, in the frame"): the frame is sandboxed, so the app
// cannot reach into it. The runtime outlines what you hover and, on a click,
// sends WHAT you pointed at, so the agent can resolve "this". A figure is the
// stamped element (`data-tb-figure`, with its binding and cell); anything else
// is described by a short selector and its text. This file words it for the person.

/** One line for the person: what they are pointing at, in the page's own terms. */
export function label(p) {
  if (!p) return ''
  if (p.kind === 'figure') {
    const where = [p.binding, p.cell].filter(Boolean).join(' → ')
    return `${p.figure_kind} figure${p.id ? ` ${p.id}` : ''}${where ? ` · ${where}` : ''}`
  }
  return `${p.tag}${p.id ? `#${p.id}` : ''}${p.section ? ` · under “${p.section}”` : ''}`
}
