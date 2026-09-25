import { useEffect, useState } from 'react'

// Illustrations drawn in SVG and animated with CSS (see "Motion &
// illustration" in global.css). Each one shows something TraceBi actually
// does: a receipt printed and stamped, a file scanned against its receipt,
// the report and its receipt belonging together. Colors come from theme
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

// ── The receipt printer ─────────────────────────────────────────────────────
// mode="done": the slip feeds out, its figures draw in, the stamp lands, then
//   it rests with a slow float. The Reports page's empty state.
// mode="print": the slip feeds and figures draw on a loop — a build or an
//   open in progress. No stamp: nothing has been checked yet.

const TEETH = 8
function slipPath() {
  // A slip 88 wide from x=56, 96 tall, with a torn (zigzag) bottom edge.
  const left = 56, right = 144, bottom = 132, w = (right - left) / TEETH
  let d = `M${left} 30 H${right} V${bottom}`
  for (let i = 0; i < TEETH; i++) {
    const x = right - w * (i + 0.5)
    d += ` L${x.toFixed(1)} ${bottom + 5} L${(right - w * (i + 1)).toFixed(1)} ${bottom}`
  }
  return d + ' Z'
}
const SLIP = slipPath()

export function ReceiptArt({ mode = 'done', size = 200 }) {
  const bars = [16, 26, 20, 34, 28]
  return (
    <svg className={`rc rc-${mode}`} width={size} height={size * 0.85}
         viewBox="0 0 200 170" fill="none" role="img"
         aria-label={mode === 'print' ? 'A receipt printing' : 'A printed receipt with a stamp'}>
      <defs>
        <clipPath id={`rc-clip-${mode}`}><rect x="0" y="37" width="200" height="140" /></clipPath>
      </defs>
      <g className="rc-float">
        <g clipPath={`url(#rc-clip-${mode})`}>
          <g className="rc-paper">
            <path d={SLIP} fill="var(--surface)" stroke="var(--border-hl)" strokeWidth="1.2" />
            <rect className="rc-line" style={{ '--i': 0 }} x="66" y="46" width="34" height="5" rx="2.5" fill="var(--accent-text)" />
            {[0, 1, 2].map(r => (
              <g key={r}>
                <rect className="rc-line" style={{ '--i': r + 1 }} x="66" y={60 + r * 10} width="30" height="3.5" rx="1.75" fill="var(--muted)" opacity=".55" />
                <rect className="rc-line rc-line-r" style={{ '--i': r + 1 }} x={116 - r * 4} y={60 + r * 10} width={18 + r * 4} height="3.5" rx="1.75" fill="var(--text-2)" />
              </g>
            ))}
            <line x1="66" y1="94" x2="134" y2="94" stroke="var(--border)" strokeDasharray="2 3" />
            {bars.map((h, i) => (
              <rect key={i} className="rc-bar" style={{ '--i': i }}
                    x={68 + i * 10} y={126 - h} width="6" height={h} rx="1.5"
                    fill="var(--accent-text)" opacity={0.35 + i * 0.1} />
            ))}
          </g>
        </g>
        <rect x="30" y="8" width="140" height="32" rx="10" fill="var(--card)" stroke="var(--border-hl)" strokeWidth="1.2" />
        <rect x="46" y="32" width="108" height="5" rx="2.5" fill="var(--text)" opacity=".75" />
        <circle className="rc-led" cx="152" cy="20" r="3" fill="var(--green)" />
        {mode === 'done' && (
          <g className="rc-stamp">
            <circle cx="132" cy="108" r="17" fill="var(--green-lt)" stroke="var(--green-text)" strokeWidth="2" />
            <circle cx="132" cy="108" r="13" stroke="var(--green-text)" strokeWidth=".8" strokeDasharray="1.5 2" />
            <path className="rc-check" d="M125 108.5l4.5 4.5 8.5-9.5" stroke="var(--green-text)"
                  strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
          </g>
        )}
      </g>
    </svg>
  )
}

// ── A file and its receipt, belonging together ──────────────────────────────
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
        <text x="176" y="34" textAnchor="middle" fontSize="8.5" fontWeight="700" fill="var(--accent-text)" fontFamily="IBM Plex Mono, monospace">receipt</text>
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

// ── The scan: a beam re-hashing the file, the fingerprint ticking over ──────

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
    <div className="scan" role="status" aria-label="Re-hashing the file against its receipt">
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
