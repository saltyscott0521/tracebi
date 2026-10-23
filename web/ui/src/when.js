// How the app writes a moment: one module, so every page says a time the same
// way. `stamp` for a moment ("Oct 23 · 11:48"), `ago` for recency ("2 h ago"),
// and the full ISO time in the title (`isoTitle`) for whoever needs the year,
// the seconds or the zone. Local time throughout; the title carries UTC.
// scripts/ui_audit.py `[date-formats]` fails when the app writes a third shape.

const pad = n => String(n).padStart(2, '0')

function parse(iso) {
  if (iso == null || iso === '') return null
  const d = iso instanceof Date ? iso : new Date(iso)
  return Number.isNaN(d.getTime()) ? null : d
}

/** "Oct 23": the day of a moment, as `stamp` writes it. Null when unreadable. */
export function day(iso) {
  const d = parse(iso)
  return d && d.toLocaleString('en-US', { month: 'short', day: 'numeric' })
}

/** "Oct 23 · 11:48" (24-hour, local). Null when unreadable. */
export function stamp(iso) {
  const d = parse(iso)
  return d && `${day(d)} · ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

/** "just now", "2 min ago", "3 h ago", "2 d ago"; a week or more is its stamp. Null when unreadable. */
export function ago(iso, now = Date.now()) {
  const d = parse(iso)
  if (!d) return null
  const minutes = Math.floor(Math.max(0, now - d.getTime()) / 60000)
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes} min ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours} h ago`
  const days = Math.floor(hours / 24)
  return days < 7 ? `${days} d ago` : stamp(d)
}

/** The full moment, for a title: "2026-10-23T11:48:03Z". Undefined when unreadable, so no title is set. */
export function isoTitle(iso) {
  const d = parse(iso)
  return d ? d.toISOString().replace(/\.\d{3}Z$/, 'Z') : undefined
}
