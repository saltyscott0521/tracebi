import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'

import { ReportCover } from './Cover'
import { Verdict, Time } from './Shared'
import { VERDICT_LABEL } from '../verdict'
import { reportPagePath } from '../nav'
import { KIND_TAG, folderPath, hueStyle, kindOf, newestBuild, reportLabel } from '../folders'
import { scheduleWords } from '../schedule'
import { count, plural } from '../format'
import { stamp } from '../when'

// The parts of the library as a directory (/ and /?folder=<path>): a report's
// cover tile, a sideways row of them, a folder's tile, the health pills, and
// the Today ribbon of headline numbers. Every number here is one a build
// printed (the desk's `values`, read from the built page); none is computed.

function CalendarIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
         strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="3" y="5" width="18" height="16" rx="2" /><path d="M16 3v4M8 3v4M3 11h18" />
    </svg>
  )
}

/**
 * One report as a cover: its picture (or the one drawn from its manifest,
 * never a blank), then its name, what it is, its verdict, when it was built
 * and when it is built again. The whole tile is the link. *wide* is the lead
 * tile of a row; *tag* a word on the picture (what kind of report it is);
 * *hue* its folder's (folders.js folderHue).
 */
export function CoverTile({ report, verdict, built, wide, tag, hue }) {
  const words = scheduleWords(report.schedule)
  const name = reportLabel(report)
  return (
    <Link to={reportPagePath(report.name)} className={`ctile${wide ? ' ctile--wide' : ''}`}
          data-report={report.name} style={hue ? hueStyle(hue) : undefined}>
      <span className="ctile__pic">
        <ReportCover report={report} name={name} build={built} />
        {tag && <span className="ctile__tag">{tag}</span>}
      </span>
      <span className="ctile__body">
        <span className="ctile__name">{name}</span>
        {report.description && <span className="ctile__desc" title={report.description}>{report.description}</span>}
        <span className="ctile__meta">
          {verdict && <Verdict state={verdict.state} detail={verdict.detail} size="sm" />}
          {built && <span className="ctile__built">Built <Time iso={built.built_at} /></span>}
          {words && <span className="ctile__sched" title={words.long}><CalendarIcon /> {words.short}</span>}
        </span>
      </span>
    </Link>
  )
}

/** The covers of a folder's newest builds, fanned (a tile) or stacked (a hero). Pictures only. */
export function CoverFan({ reports, builds, className = 'cfan' }) {
  const newest = [...reports]
    .sort((a, b) => (builds[b.name]?.built_at || '').localeCompare(builds[a.name]?.built_at || ''))
    .slice(0, 3)
  return (
    <span className={className} aria-hidden="true">
      {newest.map(r => (
        <span key={r.name} className={`${className}__card`}>
          <ReportCover report={r} name={reportLabel(r)} build={builds[r.name]} />
        </span>
      ))}
      {!newest.length && <span className={`${className}__card ${className}__card--empty`} />}
    </span>
  )
}

// A row scrolls sideways; the arrows move it most of a view at a time and
// show only while there is more than fits.
function useOverflow(ref) {
  const [more, setMore] = useState(false)
  useEffect(() => {
    const el = ref.current
    if (!el) return undefined
    const check = () => setMore(el.scrollWidth > el.clientWidth + 1)
    check()
    const watch = new ResizeObserver(check)
    watch.observe(el)
    return () => watch.disconnect()
  }, [ref])
  return more
}

function Arrow({ dir, onClick, label }) {
  return (
    <button type="button" className="crow__arrow" onClick={onClick} aria-label={label}>
      <span aria-hidden="true">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"
             strokeLinecap="round" strokeLinejoin="round">
          <path d={dir < 0 ? 'M15 6l-6 6 6 6' : 'M9 6l6 6-6 6'} />
        </svg>
      </span>
    </button>
  )
}

/**
 * A row of covers that scrolls sideways (snapping a tile at a time): its
 * title with the folder's hue, a line of what it holds, "Open folder" when it
 * is one, and two arrows. *children* are the tiles; *empty* is what a row
 * with none says (how it fills).
 */
export function CoverRow({ title, hue, meta, open, row, empty, children }) {
  const track = useRef(null)
  const more = useOverflow(track)
  const move = dir => track.current?.scrollBy({ left: dir * track.current.clientWidth * 0.8, behavior: 'smooth' })
  return (
    <section className="crow" aria-label={title} data-row={row} style={hue ? hueStyle(hue) : undefined}>
      <div className="crow__head">
        <h2 className="crow__title"><i aria-hidden="true" />{title}</h2>
        {meta && <span className="crow__meta">{meta}</span>}
        {open && <Link to={open} className="crow__open">Open folder <span aria-hidden="true">→</span></Link>}
        {more && (
          <span className="crow__arrows">
            <Arrow dir={-1} onClick={() => move(-1)} label={`Scroll ${title} left`} />
            <Arrow dir={1} onClick={() => move(1)} label={`Scroll ${title} right`} />
          </span>
        )}
      </div>
      {[children].flat().filter(Boolean).length || !empty
        ? <ul className="crow__track" ref={track}>{children}</ul>
        : <p className="crow__none">{empty}</p>}
    </section>
  )
}

/** A folder on the directory: its hue, a fan of its newest covers, its name, how many reports, a headline number. */
export function FolderTile({ folder, builds }) {
  const lead = newestBuild(folder.items, builds)?.values?.[0]
  return (
    <Link to={folderPath(folder.path)} className="ftile" style={hueStyle(folder.hue)} data-folder={folder.path}>
      <CoverFan reports={folder.items} builds={builds} />
      <span className="ftile__name">{folder.label}</span>
      <span className="ftile__meta">
        <span><b>{folder.items.length}</b> {plural(folder.items.length, 'report')}</span>
        {lead && <span className="ftile__lead" title={`${lead.label}, as last built`}>{lead.text}</span>}
      </span>
    </Link>
  )
}

const GLANCE = [
  ['reproduces', n => `${n} reproduce${n === 1 ? 's' : ''}`],
  ['needs-a-look', n => `${n} ${n === 1 ? 'needs' : 'need'} a look`],
  ['does-not-reproduce', n => `${n} ${n === 1 ? 'does' : 'do'} not reproduce`],
  ['not-checked', n => `${n} not checked`],
  ['never-built', n => `${n} never built`],
]

/**
 * What *reports* hold at a glance, as pills: how many, how many of their last
 * builds reproduce, need a look, or were never built (in the words of the chip
 * each counts), when the newest was built and, when any has one, its schedule.
 */
export function Health({ reports, verdictFor, builds, known }) {
  const tally = {}
  reports.forEach(r => { const v = verdictFor(r); if (v) tally[v.state] = (tally[v.state] || 0) + 1 })
  const parts = GLANCE.filter(([state]) => tally[state] || ['reproduces', 'needs-a-look', 'never-built'].includes(state))
  const newest = newestBuild(reports, builds)
  const scheduled = [...new Set(reports.map(r => scheduleWords(r.schedule)?.short).filter(Boolean))]
  return (
    <div className="glance" role="group" aria-label="At a glance">
      <span className="glance__item"><b>{reports.length}</b> {plural(reports.length, 'report')}</span>
      {/* A count of nothing is not a signal: it reads muted, not in its chip's colour. */}
      {known && parts.map(([state, say]) => (
        <span key={state} className={`glance__item glance__item--${tally[state] ? state : 'none'}`}>{say(tally[state] || 0)}</span>
      ))}
      {newest && <span className="glance__item">Last built <Time iso={newest.built_at} /></span>}
      {scheduled.length === 1 && <span className="glance__item">Next: {scheduled[0]}</span>}
      {scheduled.length > 1 && <span className="glance__item">{count(scheduled.length, 'schedule')}</span>}
    </div>
  )
}

/** A series the build recorded, drawn small; never one made up. */
function Spark({ points }) {
  const lo = Math.min(...points)
  const span = Math.max(...points) - lo || 1
  const xy = points.map((p, i) => [(i / (points.length - 1)) * 84 + 1, 31 - ((p - lo) / span) * 28])
  const line = xy.map(([x, y], i) => `${i ? 'L' : 'M'}${x.toFixed(1)} ${y.toFixed(1)}`).join(' ')
  const [lx, ly] = xy[xy.length - 1]
  return (
    <svg className="today__spark" viewBox="0 0 86 34" fill="none" aria-hidden="true">
      <path d={`${line} V34 H1Z`} className="today__area" />
      <path d={line} className="today__line" />
      <circle cx={lx} cy={ly} r="2.5" className="today__end" />
    </svg>
  )
}

/**
 * The home page's headline numbers: one tile per pinned figure, or, when
 * nothing is pinned, the first number of each folder's newest build (at most
 * four). Each is the value the build printed, with its delta and series only
 * when the build carries them, its build's verdict, and the report it is
 * from, which the tile opens.
 */
export function Today({ library, builds, verdictFor, pins }) {
  const folderOfReport = Object.fromEntries(library.folders.flatMap(f => f.items.map(r => [r.name, f])))
  const report = name => library.all.find(r => r.name === name)
  let tiles = (pins || []).map(p => {
    const value = builds[p.report]?.values?.find(v => v.id === p.id)
    return value && report(p.report) ? { report: report(p.report), value, pinned: true } : null
  }).filter(Boolean)
  if (!tiles.length) {
    tiles = library.folders.map(f => {
      const b = newestBuild(f.items, builds)
      return b?.values?.[0] ? { report: report(b.report), value: b.values[0], pinned: false } : null
    }).filter(t => t?.report)
  }
  tiles = tiles.slice(0, 4)
  if (!tiles.length) return null
  return (
    <ul className="today" aria-label="Today">
      {tiles.map(({ report: r, value, pinned }) => {
        const folder = folderOfReport[r.name]
        const v = verdictFor(r)
        return (
          <li key={`${r.name}#${value.id}`}>
            <Link to={reportPagePath(r.name)} className="today__tile" style={folder ? hueStyle(folder.hue) : undefined}>
              <span className="today__label">
                <span title={`${value.label}${folder ? ` · ${folder.label}` : ''}`}>{value.label}{folder && <> · {folder.label}</>}</span>
                {v && <span className={`today__dot today__dot--${v.state}`} title={v.detail}>
                  <span className="sr-only">{VERDICT_LABEL[v.state]}</span>
                </span>}
              </span>
              <span className="today__value">{value.text}</span>
              {value.delta && <span className="today__delta">{value.delta}</span>}
              {value.spark && <Spark points={value.spark} />}
              <span className="today__from">from {reportLabel(r)}{pinned ? ' · pinned' : ''}</span>
            </Link>
          </li>
        )
      })}
    </ul>
  )
}

/** The kind of a report, as the word on its cover. */
export const tagOf = r => KIND_TAG[kindOf(r)]

/** When the newest of *reports* was built, as a row's line ("Oct 24 · 21:24"). */
export const builtLine = (reports, builds) => {
  const b = newestBuild(reports, builds)
  return b ? stamp(b.built_at) : null
}
