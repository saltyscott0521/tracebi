import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { easeCubicOut, max, min, scaleLinear } from 'd3'

import { useNarrow } from './Shared'

// The app's bar chart: Ask's answer and Explore's result. It is drawn the way
// a built report draws a horizontal bar (tracebi.js, "The D3 chart engine"):
// the bar is 55% of its band, the end facing away from zero is rounded, the
// one rule is the baseline at zero, and the number at the end of a bar is the
// server's own text for it. d3 is a scale and easing helper only; React draws
// the SVG, so the chart stays declarative. It computes no number: every bar is
// one row's value.

const MOTION_MS = 450
const LINE = 15      // px between the lines of a wrapped label
const VALUE_ROOM = 104

// Category labels wrap rather than cut: words onto as many lines as they need.
function wrapWords(text, chars) {
  const lines = []
  for (const word of String(text).split(' ')) {
    const last = lines[lines.length - 1]
    if (last && (last + ' ' + word).length <= chars) lines[lines.length - 1] = `${last} ${word}`
    else lines.push(word)
  }
  return lines
}

function useWidth() {
  const ref = useRef(null)
  const [width, setWidth] = useState(0)
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return undefined
    setWidth(el.getBoundingClientRect().width)
    const ro = new ResizeObserver(([e]) => setWidth(e.contentRect.width))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  return [ref, width]
}

const reducedMotion = () => !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

// Each bar's [start, length] in pixels, eased from what is on screen to the
// target whenever the data changes: a bar that stays moves, a new one grows
// from zero. A change of width alone (a resize) jumps; it is not news.
function useTween(target, zero, width) {
  const [shown, setShown] = useState(target)
  const last = useRef({ shown: target, width })
  useEffect(() => {
    const from = last.current.shown
    if (last.current.width !== width || reducedMotion()) {
      last.current = { shown: target, width }
      setShown(target)
      return undefined
    }
    let frame
    const start = performance.now()
    const tick = now => {
      const t = easeCubicOut(Math.min(1, (now - start) / MOTION_MS))
      const next = {}
      for (const [k, [x, w]] of Object.entries(target)) {
        const [x0, w0] = from[k] || [zero, 0]
        next[k] = [x0 + (x - x0) * t, w0 + (w - w0) * t]
      }
      last.current = { shown: next, width }
      setShown(next)
      if (t < 1) frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
    // The target is new on every render; its content is what matters.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(target), width])
  return shown
}

// One bar: a rectangle with its far end rounded (radius 2), as the report draws it.
function barPath(x, w, y, h, positive) {
  const r = Math.min(2, w, h / 2)
  if (w <= 0) return `M${x},${y}V${y + h}Z`
  if (positive) {
    const x1 = x + w
    return `M${x},${y}H${x1 - r}Q${x1},${y} ${x1},${y + r}V${y + h - r}Q${x1},${y + h} ${x1 - r},${y + h}H${x}Z`
  }
  return `M${x + w},${y}H${x + r}Q${x},${y} ${x},${y + r}V${y + h - r}Q${x},${y + h} ${x + r},${y + h}H${x + w}Z`
}

/**
 * Horizontal bars, one per row: *rows* is [{label, value, display}], *display*
 * the server's text for the value. *onPick(label)*, when given, is a click (or
 * Enter / Space) on a bar. *label* names the figure for assistive technology.
 */
export default function AnswerChart({ rows, onPick, label, className = '' }) {
  const narrow = useNarrow()
  const [ref, width] = useWidth()
  const axis = narrow ? 112 : 200
  const chars = Math.floor(axis / 7)
  const bars = rows.map((r, i) => ({ ...r, key: `${i}:${r.label}`, lines: wrapWords(r.label, chars) }))
  const tall = max(bars, b => b.lines.length) || 1
  const band = Math.max(34, tall * LINE + 10)
  const thick = Math.min(22, Math.round(band * 0.55))
  const height = bars.length * band + 8

  const plot = Math.max(10, width - axis - VALUE_ROOM)
  const values = bars.map(b => (typeof b.value === 'number' ? b.value : 0))
  const lo = Math.min(0, min(values) ?? 0)
  const hi = Math.max(0, max(values) ?? 0)
  const x = scaleLinear().domain([lo, hi === lo ? lo + 1 : hi]).range([axis, axis + plot])
  const zero = x(0)
  const target = Object.fromEntries(bars.map((b, i) => {
    const v = x(values[i])
    return [b.key, [Math.min(v, zero), Math.abs(v - zero)]]
  }))
  const shown = useTween(target, zero, width)

  const pick = b => () => onPick?.(b.label)
  return (
    <figure ref={ref} className={`answer-chart ${className}`.trim()} aria-label={label}>
      {width > 0 && (
        <svg width={width} height={height} role="group" aria-label={label} className="answer-chart__svg">
          {bars.map((b, i) => {
            const y = 4 + i * band
            const [bx, bw] = shown[b.key] || [zero, 0]
            const positive = values[i] >= 0
            const name = `${b.label}, ${b.display}`
            return (
              <g key={b.key} className={`answer-chart__bar${onPick ? ' answer-chart__bar--pick' : ''}`}
                 tabIndex={0} role={onPick ? 'button' : 'img'} aria-label={name}
                 onClick={onPick ? pick(b) : undefined}
                 onKeyDown={onPick ? e => {
                   if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onPick(b.label) }
                 } : undefined}>
                <title>{name}</title>
                <rect className="answer-chart__band" x={0} y={y} width={width} height={band} rx={4} />
                <text className="answer-chart__label" x={axis - 8} y={y + band / 2 - ((b.lines.length - 1) * LINE) / 2}>
                  {b.lines.map((l, j) => <tspan key={j} x={axis - 8} dy={j ? LINE : 0}>{l}</tspan>)}
                </text>
                <path className="answer-chart__mark" d={barPath(bx, bw, y + (band - thick) / 2, thick, positive)} />
                {/* A negative bar's number sits past zero, clear of the names. */}
                <text className="answer-chart__value" x={positive ? bx + bw + 8 : zero + 8} y={y + band / 2}>
                  {b.display}
                </text>
              </g>
            )
          })}
          <line className="answer-chart__zero" x1={zero} x2={zero} y1={4} y2={height - 4} />
        </svg>
      )}
    </figure>
  )
}
