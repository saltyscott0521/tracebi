import { useState } from 'react'

import { reportCoverUrl } from '../api'
import { stamp } from '../when'
import { count } from '../format'

// A report's face in the library. The build's own cover when it took one (a
// picture of its first screen, tracebi/reports/cover.py), else one drawn here
// from what the build's manifest says it holds: the name, a glyph per kind of
// figure, and when it was built. A picture of query results, never one: no
// number from the report is drawn here.

const KINDS = [['value', 'value'], ['chart', 'chart'], ['table', 'table']]

const GLYPH = {
  value: <><rect x="3" y="5" width="18" height="14" rx="2" /><path d="M7 14h6M7 10h3" /></>,
  chart: <path d="M4 20V10M10 20V4M16 20v-7M21 20H3" />,
  table: <><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M3 9h18M3 14h18M10 4v16" /></>,
}

function Glyph({ kind }) {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
         strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{GLYPH[kind]}</svg>
  )
}

/** The cover drawn when a build took none: the same on every machine, from
 *  the report's name and its build's manifest. */
export function GeneratedCover({ name, kinds, builtAt }) {
  const held = KINDS.filter(([k]) => kinds?.[k])
  return (
    <div className="gcover" aria-hidden="true">
      <span className="gcover__name">{name}</span>
      <span className="gcover__foot">
        {held.length > 0 && (
          <span className="gcover__kinds">
            {held.map(([k, noun]) => (
              <span key={k} className="gcover__kind"><Glyph kind={k} />{count(kinds[k], noun)}</span>
            ))}
          </span>
        )}
        <span className="gcover__when">{builtAt ? `Built ${stamp(builtAt)}` : 'Not built yet'}</span>
      </span>
    </div>
  )
}

/** A report's cover: the build's picture, or the drawn one when it has none
 *  or the picture will not load. The drawn one stays under the picture (a
 *  loaded image can still be a frame from painting), so a tile is never blank. */
export function ReportCover({ report, name, build }) {
  const [failed, setFailed] = useState(null)
  const [loaded, setLoaded] = useState(null)
  const src = build?.cover ? reportCoverUrl(report.name, build.built_at) : null
  const picture = src && failed !== src
  return (
    <div className="lcover">
      <GeneratedCover name={name} kinds={build?.figure_kinds} builtAt={build?.built_at} />
      {picture && (
        <img src={src} alt="" loading="lazy" decoding="async" className={loaded === src ? 'is-loaded' : undefined}
             onLoad={() => setLoaded(src)} onError={() => setFailed(src)} />
      )}
    </div>
  )
}
