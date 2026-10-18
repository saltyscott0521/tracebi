import { useEffect, useMemo, useRef, useState } from 'react'

import { FRAME_SANDBOX, listenToFrame } from '../frameBridge'

// The build's own receipt, as a certificate in the app's panel. The app does
// not draw it: it hands the build's own tracebi.css, tracebi.js, receipt block
// and semantic contracts to a sandboxed frame, and tracebi.renderReceipt draws
// it there as the file's drawer does. A frame, because loading the runtime
// boots its page hydration and its stylesheet styles the document it is in;
// neither belongs on the app's page.

const CSS_MARK = '<!-- tracebi.css: the TraceBi design system -->'
const JS_MARK = '<!-- tracebi.js: the TraceBi runtime -->'

// The text of the first `open … close` after *mark*, or null.
function after(html, mark, open, close) {
  const at = html.indexOf(mark)
  if (at < 0) return null
  const a = html.indexOf(open, at)
  const b = a < 0 ? -1 : html.indexOf(close, a + open.length)
  return b < 0 ? null : html.slice(a + open.length, b)
}

// The build's blocks go in as the build escaped them; only the app's own value
// is escaped here.
const json = v => (v === undefined ? 'undefined' : JSON.stringify(v).replace(/</g, '\\u003c'))
// The states the app may put on the chip: what verdictOf computes for a build.
const TOLD = new Set(['reproduces', 'needs-a-look', 'does-not-reproduce', 'not-checked'])

/** The page that renders *html*'s receipt with *verdict*, or null when the build has none.
 *  *file* is the built file's name, for the "how to check" line. */
export function receiptDocument(html, verdict, mode, file) {
  if (!html) return null
  const css = after(html, CSS_MARK, '<style>', '</style>')
  const js = after(html, JS_MARK, '<script>', '</script>')
  const receipt = html.match(/<script id="tracebi-receipt"[^>]*>([\s\S]*?)<\/script>/)
  if (css == null || js == null || !receipt) return null
  const contracts = html.match(/<script id="tb-semantic-contract-[^"]*"[^>]*>[\s\S]*?<\/script>/g) || []
  return `<!doctype html><html lang="en" data-tb-mode="${mode === 'dark' ? 'dark' : 'light'}"><head>
<meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; font-src data:; img-src data:">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>${css}</style>
<style>body { max-width: none; margin: 0; padding: 16px 18px 24px; background: var(--tb-bg); font-size: var(--tb-text-sm); line-height: 1.5; }</style>
</head><body><div id="tb-host-mount"></div>
<script id="tb-host-receipt" type="application/json">${receipt[1]}</script>
${contracts.join('\n')}
<script>${js}</script>
<script>(function () {
  var contracts = [].map.call(document.querySelectorAll('script[id^="tb-semantic-contract-"]'),
    function (s) { try { return JSON.parse(s.textContent); } catch (e) { return null; } });
  window.tracebi.renderReceipt(document.getElementById('tb-host-mount'),
    JSON.parse(document.getElementById('tb-host-receipt').textContent),
    { verdict: ${json(TOLD.has(verdict) ? verdict : 'not-checked')}, page: null,
      contracts: contracts.filter(Boolean), file: ${json(file || undefined)} });
})();</script>
</body></html>`
}

/**
 * The receipt of the build in *html*, its chip in the app's *verdict* state (a
 * state verdictOf computed; with none, what the file says of itself: Not
 * checked). As tall as the certificate, so the panel scrolls it.
 */
export default function ReceiptFrame({ html, verdict, title, file }) {
  const frame = useRef(null)
  const [height, setHeight] = useState(480)
  const mode = document.documentElement.getAttribute('data-theme')
  const doc = useMemo(() => receiptDocument(html, verdict, mode, file), [html, verdict, mode, file])
  useEffect(() => (frame.current ? listenToFrame(frame.current, m => {
    if (m.type === 'size' && m.height) setHeight(m.height)
  }) : undefined), [doc])
  if (!doc) {
    return <p className="rpanel__empty">This build carries no trace the app can show. Open the report to read it there.</p>
  }
  return (
    <iframe ref={frame} srcDoc={doc} sandbox={FRAME_SANDBOX} title={title}
            className="rpanel__receipt" style={{ height }} />
  )
}
