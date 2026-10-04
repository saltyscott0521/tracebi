// Build mode: point at something in a report.
//
// Listens inside the report preview (the iframe's own document, in memory: the
// built file is never touched), outlines what you hover, and on a click reports
// WHAT you pointed at, so the agent can resolve "this". A figure is the
// stamped element (`data-tb-figure`, with its binding and cell); anything else
// is described by a short selector and its text.

const CHROME = '#tracebi-receipt, .tb-badge, .tb-receipt-btn, [data-tb-chrome]'
const INLINE = new Set(['SPAN', 'B', 'I', 'EM', 'STRONG', 'A', 'CODE', 'SMALL', 'SUP', 'SUB', 'TSPAN'])
const HEADING = /^H[1-6]$/

/** The element a click means: its figure, else the nearest block (not inline text). */
export function targetOf(el) {
  if (!el || el.nodeType !== 1) return null
  if (el.closest(CHROME)) return null
  const figure = el.closest('[data-tb-figure]')
  if (figure) return figure
  let node = el
  while (node && INLINE.has(node.tagName) && node.parentElement) node = node.parentElement
  return node && !['HTML', 'BODY'].includes(node.tagName) ? node : null
}

function selectorOf(el) {
  const parts = []
  for (let node = el; node && node.nodeType === 1 && node.tagName !== 'BODY'; node = node.parentElement) {
    let part = node.tagName.toLowerCase()
    if (node.id) { parts.unshift(`${part}#${node.id}`); break }
    const cls = [...node.classList].filter(c => !c.startsWith('tb-point')).slice(0, 2)
    if (cls.length) part += '.' + cls.join('.')
    parts.unshift(part)
    if (parts.length >= 4) break
  }
  return parts.join(' > ')
}

/** The nearest heading above the element: which section of the page it is in. */
function sectionOf(el) {
  for (let node = el; node && node.nodeType === 1; node = node.parentElement) {
    for (let sib = node.previousElementSibling; sib; sib = sib.previousElementSibling) {
      if (HEADING.test(sib.tagName)) return sib.textContent
      const inner = sib.querySelector?.('h1,h2,h3,h4,h5,h6')
      if (inner) return inner.textContent
    }
  }
  return ''
}

/** What the agent is told: the figure's addresses, or the element's selector and text. */
export function describe(el) {
  const text = (el.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 200)
  const figure = el.getAttribute('data-tb-figure')
  if (figure) {
    return {
      kind: 'figure',
      figure_kind: figure,
      id: el.id || '',
      binding: el.getAttribute('data-tb-binding') || '',
      cell: el.getAttribute('data-tb-cell') || '',
      text,
    }
  }
  return {
    kind: 'element',
    tag: el.tagName.toLowerCase(),
    id: el.id || '',
    selector: selectorOf(el),
    text,
    section: (sectionOf(el) || '').replace(/\s+/g, ' ').trim().slice(0, 120),
  }
}

/** One line for the person: what they are pointing at, in the page's own terms. */
export function label(p) {
  if (!p) return ''
  if (p.kind === 'figure') {
    const where = [p.binding, p.cell].filter(Boolean).join(' → ')
    return `${p.figure_kind} figure${p.id ? ` ${p.id}` : ''}${where ? ` · ${where}` : ''}`
  }
  return `${p.tag}${p.id ? `#${p.id}` : ''}${p.section ? ` · under “${p.section}”` : ''}`
}

const STYLE = `
  .tb-point-hover { outline: 2px solid #2563eb !important; outline-offset: 2px; cursor: crosshair !important; }
  .tb-point-picked { outline: 2px solid #2563eb !important; outline-offset: 2px;
    background-color: rgba(37,99,235,.08) !important; }
  body * { cursor: crosshair; }
`

/**
 * Start listening in *doc*. Calls onPoint(descriptor) on a click and onClear()
 * on Escape. Returns a function that stops and removes every trace.
 */
export function attachPointMode(doc, { onPoint, onClear }) {
  if (!doc?.body) return () => {}
  const style = doc.createElement('style')
  style.setAttribute('data-tb-point', '')
  style.textContent = STYLE
  doc.head.appendChild(style)

  let hovered = null
  let picked = null
  const mark = (el, cls, on) => el && el.classList[on ? 'add' : 'remove'](cls)

  const over = e => {
    const el = targetOf(e.target)
    if (el === hovered) return
    mark(hovered, 'tb-point-hover', false)
    hovered = el
    mark(hovered, 'tb-point-hover', true)
  }
  const out = e => {
    if (!e.relatedTarget) { mark(hovered, 'tb-point-hover', false); hovered = null }
  }
  const click = e => {
    const el = targetOf(e.target)
    if (!el) return
    e.preventDefault()
    e.stopPropagation()
    mark(picked, 'tb-point-picked', false)
    picked = el
    mark(picked, 'tb-point-picked', true)
    onPoint(describe(el))
  }
  const key = e => {
    if (e.key !== 'Escape') return
    mark(picked, 'tb-point-picked', false)
    picked = null
    onClear()
  }

  doc.addEventListener('mouseover', over, true)
  doc.addEventListener('mouseout', out, true)
  doc.addEventListener('click', click, true)
  doc.addEventListener('keydown', key, true)
  return () => {
    doc.removeEventListener('mouseover', over, true)
    doc.removeEventListener('mouseout', out, true)
    doc.removeEventListener('click', click, true)
    doc.removeEventListener('keydown', key, true)
    mark(hovered, 'tb-point-hover', false)
    mark(picked, 'tb-point-picked', false)
    style.remove()
  }
}
