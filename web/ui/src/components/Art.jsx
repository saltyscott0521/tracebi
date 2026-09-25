import { useEffect, useState } from 'react'

// Illustrations drawn in SVG and animated with CSS (see "Motion &
// illustration" in global.css). Each one shows something TraceBi actually
// does: a report assembling, a file checked against its manifest, the report
// and its manifest belonging together. Colors come from theme
// tokens so they hold in light and dark, and everything stops under
// prefers-reduced-motion.

// ── The brand mark: brackets, two bars rising, a trace dot running across ──

export function BrandMark() {
  const [play, setPlay] = useState(0)            // bump to replay on hover
  return (
    <div className="bm" onMouseEnter={() => setPlay(p => p + 1)} aria-hidden="true">
      <svg key={play} width="16" height="16" viewBox="0 0 20 20" fill="none">
        <path className="bm-bracket" d="M6.6 4.5 H4.6 V15.5 H6.6 M13.4 4.5 H15.4 V15.5 H13.4"
              stroke="white" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
        <rect className="bm-bar bm-bar-1" x="8.1" y="9.6" width="1.7" height="4.4" rx=".4" fill="white" />
        <rect className="bm-bar bm-bar-2" x="11" y="7.2" width="1.7" height="6.8" rx=".4" fill="white" />
        <circle className="bm-dot" cx="5" cy="4.5" r="1.1" fill="#7dd3fc" />
      </svg>
    </div>
  )
}

// ── A report assembling itself ─────────────────────────────────────────────
// mode="done": the numbers, bars, trend line and donut build in once, then the
//   card rests with a slow float. The Reports page's empty state.
// mode="build": the same build on a loop, while a report opens or rebuilds.

const BARS = [22, 34, 28, 46, 38, 54]
const TREND = 'M30 112 L46 106 L62 108 L78 96 L94 100 L110 86 L124 80'

export function ReportArt({ mode = 'done', size = 220 }) {
  return (
    <svg className={`ra ra-${mode}`} width={size} height={size * 0.73}
         viewBox="0 0 220 160" fill="none" role="img"
         aria-label={mode === 'build' ? 'A report being built' : 'A report'}>
      <g className="ra-float">
        <rect x="10" y="10" width="200" height="140" rx="10" fill="var(--surface)" stroke="var(--border-hl)" strokeWidth="1.2" />
        {[22, 30, 38].map(cx => <circle key={cx} cx={cx} cy="22" r="2.4" fill="var(--border-hl)" />)}
        <rect x="50" y="19.5" width="54" height="5" rx="2.5" fill="var(--muted)" opacity=".4" />
        {[20, 83, 146].map((x, i) => (
          <g key={x}>
            <rect x={x} y="34" width="54" height="24" rx="5" fill="var(--surface-2)" stroke="var(--border)" />
            <rect x={x + 6} y="40" width="20" height="3" rx="1.5" fill="var(--muted)" opacity=".5" />
            <rect className="ra-kpi" style={{ '--i': i }} x={x + 6} y="47" width={[30, 24, 36][i]} height="6" rx="3" fill="var(--accent-text)" />
          </g>
        ))}
        <rect x="20" y="66" width="110" height="74" rx="5" fill="var(--surface-2)" stroke="var(--border)" />
        {BARS.map((h, i) => (
          <rect key={i} className="ra-bar" style={{ '--i': i }}
                x={29 + i * 16} y={132 - h} width="9" height={h} rx="2"
                fill="var(--accent-text)" opacity={0.3 + i * 0.1} />
        ))}
        <path className="ra-trend" d={TREND} pathLength="100" stroke="#38bdf8" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
        <circle className="ra-dot" cx="124" cy="80" r="3" fill="#38bdf8" />
        <rect x="138" y="66" width="62" height="74" rx="5" fill="var(--surface-2)" stroke="var(--border)" />
        <circle cx="169" cy="100" r="18" stroke="var(--border)" strokeWidth="7" />
        <circle className="ra-donut" cx="169" cy="100" r="18" pathLength="100" stroke="var(--accent-text)" strokeWidth="7"
                strokeLinecap="round" transform="rotate(-90 169 100)" />
        <rect x="152" y="126" width="34" height="3" rx="1.5" fill="var(--muted)" opacity=".5" />
      </g>
    </svg>
  )
}

// ── A report file and its manifest, belonging together ──────────────────────
// The Verify drop zone: two documents joined by a line that data runs along.

export function PairArt() {
  return (
    <svg className="pair" width="220" height="92" viewBox="0 0 220 92" fill="none" aria-hidden="true">
      <g className="pair-doc">
        <path d="M20 10h40l12 12v60a4 4 0 01-4 4H20a4 4 0 01-4-4V14a4 4 0 014-4z" fill="var(--surface)" stroke="var(--border-hl)" strokeWidth="1.3" />
        <path d="M60 10v12h12" stroke="var(--border-hl)" strokeWidth="1.3" />
        <text x="44" y="46" textAnchor="middle" fontSize="10" fontWeight="700" fill="var(--accent-text)" fontFamily="IBM Plex Mono, monospace">.html</text>
        {[56, 63, 70].map((y, i) => <rect key={y} x="26" y={y} width={36 - i * 8} height="3" rx="1.5" fill="var(--muted)" opacity=".5" />)}
      </g>
      <path className="pair-link" d="M78 48 H142" stroke="var(--accent-text)" strokeWidth="1.6" strokeDasharray="3 5" strokeLinecap="round" />
      <circle className="pair-packet" cx="78" cy="48" r="3" fill="var(--accent-text)" />
      <g className="pair-doc pair-doc-2">
        <path d="M152 10h48a4 4 0 014 4v70l-6-4-6 4-6-4-6 4-6-4-6 4-6-4-6 4-6-4V14a4 4 0 014-4z" fill="var(--surface)" stroke="var(--border-hl)" strokeWidth="1.3" />
        <text x="176" y="34" textAnchor="middle" fontSize="8.5" fontWeight="700" fill="var(--accent-text)" fontFamily="IBM Plex Mono, monospace">manifest</text>
        {[44, 52, 60].map((y) => (
          <g key={y}>
            <rect x="158" y={y} width="20" height="3" rx="1.5" fill="var(--muted)" opacity=".5" />
            <rect x="184" y={y} width="12" height="3" rx="1.5" fill="var(--text-2)" opacity=".7" />
          </g>
        ))}
      </g>
    </svg>
  )
}

// ── The scan: a beam re-hashing the file, the fingerprint ticking over ─────

const HEX = '0123456789abcdef'
function randomHex(n) {
  let s = ''
  for (let i = 0; i < n; i++) s += HEX[Math.floor(Math.random() * 16)]
  return s
}

export function ScanArt() {
  const [hex, setHex] = useState(() => randomHex(32))
  useEffect(() => {
    if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) return undefined
    const id = setInterval(() => setHex(randomHex(32)), 90)
    return () => clearInterval(id)
  }, [])
  return (
    <div className="scan" role="status" aria-label="Re-hashing the file against its manifest">
      <svg width="120" height="120" viewBox="0 0 120 120" fill="none" aria-hidden="true">
        <defs>
          <linearGradient id="scan-beam" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="var(--accent-text)" stopOpacity="0" />
            <stop offset=".85" stopColor="var(--accent-text)" stopOpacity=".28" />
            <stop offset="1" stopColor="var(--accent-text)" stopOpacity=".9" />
          </linearGradient>
          <clipPath id="scan-clip"><rect x="30" y="12" width="60" height="96" rx="6" /></clipPath>
        </defs>
        <rect x="30" y="12" width="60" height="96" rx="6" fill="var(--surface)" stroke="var(--border-hl)" strokeWidth="1.3" />
        {[26, 36, 46, 62, 72, 82, 92].map((y, i) => (
          <rect key={y} x="38" y={y} width={i % 3 === 0 ? 30 : 44} height="3.5" rx="1.75" fill="var(--muted)" opacity=".45" />
        ))}
        <g clipPath="url(#scan-clip)">
          <rect className="scan-beam" x="30" y="-10" width="60" height="26" fill="url(#scan-beam)" />
        </g>
      </svg>
      <code className="scan-hex">sha256 {hex.slice(0, 16)}<span>{hex.slice(16)}</span></code>
    </div>
  )
}
