// A report.json "schedule" block ({cron, timezone}) in words: "Every Monday,
// 07:00 New York", short "Mondays 07:00". Only the plain timetables are spelled
// out (a time of day, on every day, certain weekdays or one day of the month);
// any other cron expression is shown as written rather than guessed at.

const DAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
const CODES = { SUN: 0, MON: 1, TUE: 2, WED: 3, THU: 4, FRI: 5, SAT: 6 }

const pad = n => String(n).padStart(2, '0')
const list = parts => (parts.length > 1 ? `${parts.slice(0, -1).join(', ')} and ${parts[parts.length - 1]}` : parts[0])
const ordinal = n => `${n}${n % 100 >= 11 && n % 100 <= 13 ? 'th' : { 1: 'st', 2: 'nd', 3: 'rd' }[n % 10] || 'th'}`

function dayNumber(token) {
  const t = token.toUpperCase()
  if (t in CODES) return CODES[t]
  return /^[0-7]$/.test(t) ? Number(t) % 7 : null
}

// "MON,WED" or "1-5" → [1, 3] / [1, 2, 3, 4, 5]; null when it is anything else.
function weekdays(field) {
  const days = []
  for (const part of field.split(',')) {
    const [from, to = from, extra] = part.split('-')
    const a = dayNumber(from)
    const b = dayNumber(to)
    if (extra !== undefined || a === null || b === null || b < a) return null
    for (let d = a; d <= b; d++) days.push(d)
  }
  return [...new Set(days)].sort((x, y) => x - y)
}

export function scheduleWords(schedule) {
  const cron = schedule?.cron?.trim()
  if (!cron) return null
  const zone = (schedule.timezone || '').split('/').pop().replace(/_/g, ' ')
  const as = (when, short, time) => ({
    long: `${when}${time ? `, ${time}` : ''}${zone ? ` ${zone}` : ''}`,
    short: time ? `${short} ${time}` : short,
  })
  const asWritten = as(cron, cron)

  const [minute, hour, dom, month, dow, extra] = cron.split(/\s+/)
  if (dow === undefined || extra !== undefined || month !== '*') return asWritten
  if (!/^\d{1,2}$/.test(minute) || !/^\d{1,2}$/.test(hour)) return asWritten
  const time = `${pad(hour)}:${pad(minute)}`

  if (dom === '*' && dow === '*') return as('Every day', 'Daily', time)
  if (/^\d{1,2}$/.test(dom) && dow === '*') {
    return as(`Monthly on the ${ordinal(Number(dom))}`, 'Monthly', time)
  }
  const days = dom === '*' ? weekdays(dow) : null
  if (!days) return asWritten
  if (days.join() === '1,2,3,4,5') return as('Every weekday', 'Weekdays', time)
  return as(
    `Every ${list(days.map(d => DAYS[d]))}`,
    days.length === 1 ? `${DAYS[days[0]]}s` : days.map(d => DAYS[d].slice(0, 3)).join(', '),
    time,
  )
}
