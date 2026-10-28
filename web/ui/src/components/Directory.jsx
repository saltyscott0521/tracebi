import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'

import { ReportCover } from './Cover'
import { Verdict, Time } from './Shared'
import { reportPagePath } from '../nav'
import { KIND_TAG, folderPath, folderWord, hueStyle, kindOf, newestBuild, reportLabel } from '../folders'
import { scheduleWords } from '../schedule'
import { count, plural } from '../format'
import { stamp } from '../when'

// The parts of the library as a directory (/ and /?folder=<path>): a report's
// cover tile, a sideways row of them, a project's (or folder's) tile and the
// health pills.
// They draw no figure: a number appears only inside a report. The counts here
// are of reports, and the times are of builds.

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
 * *hue* its project's or folder's (folders.js folderHue).
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

/** The covers of a project's newest builds, fanned (a tile) or stacked (a hero). Pictures only. */
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
 * title with its project's hue, a line of what it holds, "Open project" (or
 * "Open folder", *word*) when it is one, and two arrows. *children* are the
 * tiles; *empty* is what a row with none says (how it fills).
 */
export function CoverRow({ title, hue, meta, open, word = 'folder', row, empty, children }) {
  const track = useRef(null)
  const more = useOverflow(track)
  const move = dir => track.current?.scrollBy({ left: dir * track.current.clientWidth * 0.8, behavior: 'smooth' })
  return (
    <section className="crow" aria-label={title} data-row={row} style={hue ? hueStyle(hue) : undefined}>
      <div className="crow__head">
        <h2 className="crow__title"><i aria-hidden="true" />{title}</h2>
        {meta && <span className="crow__meta">{meta}</span>}
        {open && <Link to={open} className="crow__open">Open {word} <span aria-hidden="true">→</span></Link>}
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

/**
 * A project on the directory (or a folder, or My published): its hue, a fan of
 * its newest covers, what it is (Project or Folder), its name, how many
 * reports, when it was last built.
 */
export function FolderTile({ folder, builds }) {
  const newest = newestBuild(folder.items, builds)
  return (
    <Link to={folderPath(folder.path)} className="ftile" style={hueStyle(folder.hue)} data-folder={folder.path}>
      <CoverFan reports={folder.items} builds={builds} />
      <span className="ftile__kind">{folderWord(folder)}</span>
      <span className="ftile__name">{folder.label}</span>
      <span className="ftile__meta">
        <span><b>{folder.items.length}</b> {plural(folder.items.length, 'report')}</span>
        {newest && <span className="ftile__when">Built <Time iso={newest.built_at} /></span>}
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

/** The kind of a report, as the word on its cover. */
export const tagOf = r => KIND_TAG[kindOf(r)]

/** When the newest of *reports* was built, as a row's line ("Oct 24 · 21:24"). */
export const builtLine = (reports, builds) => {
  const b = newestBuild(reports, builds)
  return b ? stamp(b.built_at) : null
}
