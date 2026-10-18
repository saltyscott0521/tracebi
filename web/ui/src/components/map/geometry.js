// Sizes and edges for the Map. Nothing here reads the page's layout: a layout
// is plain numbers computed from the data, so a long name or a hundred reports
// change the picture, not the code.
//
// Identifiers are set in IBM Plex Mono, whose advance is 0.6em, so how many
// lines one takes in a box of a given width is exact, not a guess. A model's or
// a report's label is set in the app's sans, so it is measured in that font
// (a canvas's measureText, which lays nothing out). The small labels are
// proportional; they get a conservative average and some slack.

export const MONO_W = 7.8      // one character of a 13px name
const SANS_W = 5.9             // one character of an 11px label, on average
export const NAME_LINE = 19    // a 13px name at line-height 1.45
const SANS_LINE = 21           // a 14px label (.node__name--sans) at line-height 1.45
const KIND_LINE = 20           // a mark (a verdict chip, a flag) or a fact with the name
const PAD_X = 12               // node padding, left and right
const EDGE_GAP = 6             // arrowheads are 7 long; the line stops short of them

export const clamp = (n, lo, hi) => Math.min(hi, Math.max(lo, n))

/** How wide a column of these names wants to be, before it is clamped. */
export const widest = names => Math.max(0, ...names.map(n => n.length * MONO_W + 6))   // +6: a hair of slack, so a name that just fits does not wrap

let canvas = null
/** A label's width in px, in the weight and size .node__name--sans sets it. */
export function labelWidth(text) {
  try {
    canvas = canvas || document.createElement('canvas').getContext('2d')
    const family = getComputedStyle(document.documentElement).getPropertyValue('--font-sans') || 'sans-serif'
    canvas.font = `600 14px ${family}`
    return canvas.measureText(text).width
  } catch {
    return text.length * 8    // no canvas (a test runner): a generous average
  }
}

/** How wide a column of these labels wants to be, before it is clamped. */
export const widestLabel = labels => Math.max(0, ...labels.map(l => Math.ceil(labelWidth(l)) + 6))

/** Lines a label takes in *inner* px, breaking between words, as the browser will. */
export function labelNameLines(text, inner) {
  let lines = 1
  let used = 0
  const space = labelWidth(' ')
  for (const word of String(text).split(/\s+/).filter(Boolean)) {
    const w = labelWidth(word)
    if (used > 0 && used + space + w > inner) {
      lines += 1
      used = 0
    }
    if (w > inner) {
      lines += Math.ceil(w / inner) - 1
      used = w % inner
    } else {
      used += (used > 0 ? space : 0) + w
    }
  }
  return lines
}

/**
 * Lines a name takes in *inner* px. It breaks only after an underscore (the
 * view puts a <wbr> there), unless one piece is longer than the line.
 */
export function nameLines(name, inner) {
  const cap = Math.max(4, Math.floor(inner / MONO_W))
  let lines = 1
  let used = 0
  for (const piece of name.match(/[^_]+_?|_/g) || [name]) {
    if (piece.length > cap) {
      if (used > 0) lines += 1
      lines += Math.ceil(piece.length / cap) - 1
      used = piece.length % cap || cap
    } else if (used + piece.length > cap) {
      lines += 1
      used = piece.length
    } else {
      used += piece.length
    }
  }
  return lines
}

/** Lines a short label takes in *inner* px, breaking between words. */
export function labelLines(text, inner) {
  if (!text) return 0
  const cap = Math.max(6, Math.floor(inner / SANS_W))
  let lines = 1
  let used = 0
  for (const word of text.split(/\s+/)) {
    const len = word.length + (used ? 1 : 0)
    if (used + len > cap && used > 0) {
      lines += 1
      used = word.length
    } else {
      used += len
    }
  }
  return lines
}

/**
 * A node's height from what it says. `reserve` keeps room for a label that
 * arrives later (a table's status), so it does not move the picture when it does.
 */
export function heightOf({ name, label, w, min, sans = false, reserve = false, border = 2, note = 0 }) {
  const inner = w - 2 * PAD_X - 2 * border - note
  const kind = labelLines(label, inner) || (reserve ? 1 : 0)
  const named = sans ? labelNameLines(name, inner) * SANS_LINE : nameLines(name, inner) * NAME_LINE
  return Math.max(min, 12 + kind * KIND_LINE + (kind ? 3 : 0) + named + 1)
}

/**
 * Orthogonal edges as one bus: every `from` runs to a vertical trunk, and the
 * trunk runs to every `to`. One of each at the same height is a straight line.
 * Returns the path, and the points that get an arrowhead.
 */
export function bus({ from, to, trunk, tone = 'quiet', width = 2 }) {
  const ys = [...from, ...to].map(p => p.y)
  const lo = Math.min(...ys)
  const hi = Math.max(...ys)
  let d = ''
  for (const p of from) d += `M${p.x} ${p.y}H${trunk}`
  if (hi > lo) d += `M${trunk} ${lo}V${hi}`
  for (const p of to) d += `M${trunk} ${p.y}H${p.x - EDGE_GAP}`
  return { tone, width, d, heads: to }
}

/** Draw order: quiet first, so the lit path and an amber edge sit on top. */
const ORDER = { quiet: 0, warn: 1, hot: 2 }
export const byTone = edges => [...edges].sort((a, b) => ORDER[a.tone] - ORDER[b.tone])

/** `data/warehouse.duckdb` -> `warehouse.duckdb`; a folder keeps its slash. */
export function fileName(where, kind) {
  const base = String(where).replace(/\/+$/, '').split('/').pop()
  return kind === 'directory' ? `${base}/` : base
}
