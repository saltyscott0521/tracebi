// Ask: a question of one model, as a sentence built from the model's own
// definitions — "Show [measure] by [dimension] for [filter], [order], top [n]".
// The app calls no language model: each slot is a token picked from GET
// /api/models/<name> (and a dimension's values), so a question is always a
// query the model can run. Free text only finds tokens.
//
// Pure functions, no React and no fetch, so node can run them in a test: the
// question's query, the sentence, the suggestions, the definitions in words,
// and the two files "Keep this" writes into a draft.

// ── Names ────────────────────────────────────────────────────────────────────

// Mirrors tracebi/reports/derive.py (_ACRONYMS, humanise, in_sentence), so a
// label reads the same here as in a built report.
const ACRONYMS = new Set(['aov', 'api', 'arpu', 'arr', 'cac', 'cogs', 'cpa', 'cpc', 'cpm', 'ctr', 'ebitda', 'eur', 'fte', 'gbp', 'gmv', 'kpi', 'ltv', 'mau', 'mom', 'mrr', 'mtd', 'nps', 'qoq', 'qtd', 'roas', 'roi', 'sku', 'sla', 'usd', 'wau', 'dau', 'wow', 'yoy', 'ytd'])

/** `dim_branch.region` → `Region`; `ending_mrr` → `Ending MRR`. */
export function humanise(column) {
  let name = String(column).split('.').pop().replace(/^(dim|fact)_/, '').replace(/_/g, ' ').trim()
  if (!name) return String(column)
  name = name.split(' ').map(w => (ACRONYMS.has(w.toLowerCase()) ? w.toUpperCase() : w)).join(' ')
  return name[0].toUpperCase() + name.slice(1)
}

/** A label mid-sentence: lower case, except the acronyms. */
export const inSentence = label =>
  label.split(' ').map(w => (w.length > 1 && w === w.toUpperCase() && /[A-Z]/.test(w) ? w : w.toLowerCase())).join(' ')

const listWords = items =>
  items.length < 2 ? items.join('') : `${items.slice(0, -1).join(', ')} and ${items[items.length - 1]}`

// ── The query ────────────────────────────────────────────────────────────────

/** The measures a query asks for: declared names, or the raw columns it aggregates. */
export const measureNames = q =>
  Array.isArray(q?.measures) ? q.measures : Object.keys(q?.measures || {})

export const factOf = (model, q) =>
  (model?.facts || []).find(f => f.name === q?.fact) || (model?.facts || [])[0] || null

const declared = (model, name) => (model?.measures || []).find(m => m.name === name)

export function measureLabel(model, q, name) {
  if (!Array.isArray(q?.measures) && q?.measures) return `${humanise(name)} (${q.measures[name]})`
  return declared(model, name)?.label || humanise(name)
}

/** What the model says of one attribute: `{label?, description?, synonyms?}`. */
export const attributeInfo = (model, ref) => {
  const [dim, attr] = String(ref).split('.')
  return (model?.dimensions || []).find(d => d.name === dim)?.attribute_info?.[attr] || {}
}

/** A dimension attribute's label (its declared one, else humanised); the dimension's name joins it when two share one. */
export function dimensionLabel(model, ref) {
  const [dim, attr] = String(ref).split('.')
  const twins = (model?.dimensions || []).filter(d => d.name !== dim && (d.attributes || []).includes(attr))
  const label = attributeInfo(model, ref).label || humanise(attr)
  return twins.length ? `${label} (${humanise(dim)})` : label
}

const columnLabel = (model, q, col) =>
  measureNames(q).includes(col) ? measureLabel(model, q, col)
    : col.includes('.') ? dimensionLabel(model, col) : humanise(col)

/**
 * The query made consistent after an edit: an order needs a column the query
 * returns, a limit needs an order (the API refuses one without).
 */
export function tidy(q) {
  const out = { ...q, dimensions: q.dimensions || [], filters: q.filters || {} }
  const cols = new Set([...measureNames(out), ...out.dimensions])
  const order = (out.order_by || []).filter(o => cols.has(typeof o === 'string' ? o.replace(/^-/, '') : o?.column))
  if (order.length) out.order_by = order
  else delete out.order_by
  if (!out.order_by || !(out.limit > 0)) delete out.limit
  return out
}

/** The body POST /api/models/<name>/query takes: no empty parts, no blank filters. */
export function requestOf(model, q) {
  const fact = factOf(model, q)
  const body = { fact: q.fact || fact?.name, measures: q.measures }
  if (q.dimensions?.length) body.dimensions = q.dimensions
  const filters = Object.fromEntries(Object.entries(q.filters || {}).filter(([, v]) => v !== '' && v != null))
  if (Object.keys(filters).length) body.filters = filters
  if (q.order_by?.length) body.order_by = q.order_by
  if (q.limit > 0) body.limit = q.limit
  return body
}

export const canAsk = q => measureNames(q).length > 0

/** The question as a URL value (`/ask?model=…&q=…`): a link reproduces it. */
export const encodeQuery = q => JSON.stringify(q)
export function decodeQuery(text) {
  if (!text) return null
  try {
    const q = JSON.parse(text)
    return q && typeof q === 'object' && q.measures ? tidy(q) : null
  } catch {
    return null
  }
}

// ── The sentence ─────────────────────────────────────────────────────────────

const valueWords = v => (Array.isArray(v) ? listWords(v.map(String)).replace(/ and ([^,]*)$/, ' or $1') : String(v))

function filterWords(model, filters) {
  return Object.entries(filters || {}).filter(([, v]) => v !== '' && v != null).map(([col, v]) => {
    const label = inSentence(col.includes('.') ? dimensionLabel(model, col) : humanise(col))
    if (v && typeof v === 'object' && !Array.isArray(v)) {
      return Object.entries(v).map(([op, x]) => `${label} ${op} ${valueWords(x)}`).join(', ')
    }
    return `${label} ${valueWords(v)}`
  })
}

/** "largest first", "sector A to Z", or null. */
export function orderWords(model, q) {
  const [o] = q?.order_by || []
  if (!o) return null
  const column = typeof o === 'string' ? o.replace(/^-/, '') : o.column
  const desc = typeof o === 'string' ? o.startsWith('-') : !!o.desc
  if (measureNames(q).includes(column)) {
    const first = measureNames(q)[0] === column
    const by = first ? '' : ` by ${inSentence(measureLabel(model, q, column))}`
    return `${desc ? 'largest' : 'smallest'} first${by}`
  }
  return `${inSentence(columnLabel(model, q, column))} ${desc ? 'Z to A' : 'A to Z'}`
}

/** The question in words: "Fair value by sector, for fund Harbor Point BDC, largest first, top 8". */
export function sentenceOf(model, q, { limit = true } = {}) {
  const ms = measureNames(q).map((m, i) => (i ? inSentence(measureLabel(model, q, m)) : measureLabel(model, q, m)))
  if (!ms.length) return ''
  let s = listWords(ms)
  if (q.dimensions?.length) s += ` by ${listWords(q.dimensions.map(d => inSentence(dimensionLabel(model, d))))}`
  const parts = []
  const f = filterWords(model, q.filters)
  if (f.length) parts.push(`for ${f.join(', ')}`)
  const order = orderWords(model, q)
  if (order) parts.push(order)
  if (limit && q.limit > 0) parts.push(`top ${q.limit}`)
  return [s, ...parts].join(', ')
}

// ── The answer ───────────────────────────────────────────────────────────────

/**
 * How an answer is drawn: one number (or a few) when nothing groups it; a
 * chart for one measure by one dimension in at most 12 rows; else a table.
 */
export function answerShape(q, result) {
  const dims = q.dimensions || []
  const ms = measureNames(q)
  if (!dims.length && result.rows === 1) return 'number'
  const numeric = result.data.every(r => r[ms[0]] == null || typeof r[ms[0]] === 'number')
  if (dims.length === 1 && ms.length === 1 && result.rows >= 1 && result.rows <= 12 && numeric) return 'chart'
  return 'table'
}

/** The columns an answer shows: what was asked (a ratio's inputs come back too; they stay in Advanced). */
export const answerColumns = (q, result) =>
  [...(q.dimensions || []), ...measureNames(q)].filter(c => result.columns.includes(c))

export const answerColumnLabel = columnLabel

const AGG = {
  sum: 'the sum', count: 'the count', mean: 'the average', avg: 'the average', min: 'the smallest',
  max: 'the largest', nunique: 'the number of distinct', median: 'the median',
}
const aggWords = agg => AGG[agg] || (/^p\d+$/.test(agg || '') ? `the ${agg.slice(1)}th percentile` : `the ${agg}`)
const exprWords = expr => String(expr).replace(/[A-Za-z_][A-Za-z0-9_]*/g, w => inSentence(humanise(w)))
const UNIT = { currency: 'in dollars', currency0: 'in dollars', currency_compact: 'in dollars', percent: 'as a percent' }

/**
 * One measure's definition in words, from what the model declares:
 * `{label, description, how}` — "Fair value", "Total fair value",
 * "the sum of fair value, in dollars".
 */
export function definitionOf(model, q, name) {
  const label = measureLabel(model, q, name)
  if (!Array.isArray(q?.measures)) {
    return { label, description: '', how: `${aggWords(q.measures[name])} of ${inSentence(humanise(name))}, a column of the fact; not a measure the model declares` }
  }
  const m = declared(model, name)
  if (!m) return { label, description: '', how: '' }
  const named = n => inSentence(declared(model, n)?.label || humanise(n))
  let how = ''
  if (m.kind === 'simple' && m.column) how = `${aggWords(m.agg)} of ${inSentence(humanise(m.column))}`
  else if (m.kind === 'expression' && m.expr) how = `${aggWords(m.agg)} of ${exprWords(m.expr)}`
  else if (m.kind === 'ratio' && m.ratio) how = `${named(m.ratio[0])} divided by ${named(m.ratio[1])}`
  else if (m.kind === 'share' && m.share) how = `${named(m.share)} as a share of the total`
  const unit = UNIT[m.format]
  if (unit) how = how ? `${how}, ${unit}` : unit
  return { label, description: m.description || '', how }
}

// ── Suggestions: free text finds tokens ──────────────────────────────────────

const LIMITS = [3, 5, 8, 10, 20]
const KIND_RANK = { measure: 0, dimension: 1, order: 2, limit: 3, filter: 4 }

/**
 * Every token the model offers for this question. Each is
 * `{kind, id, label, sub, fields, pick(q) → q}`. *values* is
 * `{ "dim.attr": [values] }` for the filters.
 */
export function tokens(model, q, values = {}) {
  const fact = factOf(model, q)
  const out = []
  const asked = measureNames(q)
  const named = Array.isArray(q.measures)
  // Measures: those this fact runs first; a measure of another fact moves the
  // question to that fact, keeping what still applies there.
  for (const m of model?.measures || []) {
    if (named && asked.includes(m.name)) continue
    const home = fact?.runnable_measures?.includes(m.name) ? fact
      : (model.facts || []).find(f => f.runnable_measures?.includes(m.name))
    if (!home) continue
    const label = m.label || humanise(m.name)
    out.push({
      kind: 'measure', id: `m:${m.name}`, label, sub: m.description || '',
      fields: [[label, 3], [m.name.replace(/_/g, ' '), 2], [(m.synonyms || []).join(' '), 2], [m.description || '', 1]],
      pick: cur => moveTo(model, { ...cur, measures: [...(Array.isArray(cur.measures) ? cur.measures : []), m.name] }, home),
    })
  }
  const joined = (model?.dimensions || []).filter(d => d.name in (fact?.foreign_keys || {}))
  for (const d of joined) {
    for (const attr of d.attributes || []) {
      const ref = `${d.name}.${attr}`
      const label = dimensionLabel(model, ref)
      if (!(q.dimensions || []).includes(ref)) {
        out.push({
          kind: 'dimension', id: `d:${ref}`, label, sub: humanise(d.name) === label ? '' : humanise(d.name),
          fields: [[label, 3], [attr.replace(/_/g, ' '), 2], [(attributeInfo(model, ref).synonyms || []).join(' '), 2],
            [d.name.replace(/_/g, ' '), 1]],
          pick: cur => ({ ...cur, dimensions: [...(cur.dimensions || []), ref] }),
        })
      }
      for (const v of values[ref] || []) {
        const now = q.filters?.[ref]
        if (now === v || (Array.isArray(now) && now.includes(v))) continue
        out.push({
          kind: 'filter', id: `f:${ref}=${v}`, label: String(v), sub: `${label}`,
          fields: [[String(v), 3], [label, 1]],
          pick: cur => {
            const was = cur.filters?.[ref]
            const next = was == null || was === '' ? v : [...(Array.isArray(was) ? was : [was]), v]
            return { ...cur, filters: { ...(cur.filters || {}), [ref]: next } }
          },
        })
      }
    }
  }
  const [first] = asked
  if (first) {
    const order = (column, desc, label, extra) => ({
      kind: 'order', id: `o:${column}:${desc}`, label, sub: 'Order',
      fields: [[label, 3], [extra, 2]],
      pick: cur => ({ ...cur, order_by: [{ column, desc }] }),
    })
    out.push(order(first, true, 'Largest first', 'biggest highest most descending top'))
    out.push(order(first, false, 'Smallest first', 'lowest least fewest ascending bottom'))
    for (const ref of q.dimensions || []) {
      out.push(order(ref, false, `${dimensionLabel(model, ref)} A to Z`, 'alphabetical sorted ascending'))
    }
    for (const n of LIMITS) out.push(limitToken(n))
  }
  return out
}

function limitToken(n) {
  return {
    kind: 'limit', id: `l:${n}`, label: `Top ${n}`, sub: 'How many rows',
    fields: [[`top ${n}`, 3], [`first ${n} ${n}`, 2]],
    pick: cur => ({
      ...cur, limit: n,
      order_by: cur.order_by?.length ? cur.order_by : [{ column: measureNames(cur)[0], desc: true }],
    }),
  }
}

/** Switch the question to *fact*, dropping what that fact cannot answer. */
function moveTo(model, q, fact) {
  if (!fact || fact.name === q.fact) return { ...q, fact: fact?.name ?? q.fact }
  const joined = new Set(Object.keys(fact.foreign_keys || {}))
  const keep = ref => joined.has(String(ref).split('.')[0])
  return tidy({
    ...q,
    fact: fact.name,
    measures: measureNames(q).filter(m => fact.runnable_measures?.includes(m)),
    dimensions: (q.dimensions || []).filter(keep),
    filters: Object.fromEntries(Object.entries(q.filters || {}).filter(([k]) => keep(k))),
  })
}

// A word that starts a slot: "by" a dimension, "for" a value, "top" a number…
const SLOT_WORDS = [
  [/^(?:by|per|across)\b\s*/, 'dimension'],
  [/^(?:for|where|in|only|just)\b\s*/, 'filter'],
  [/^(?:top|first)\b\s*/, 'limit'],
  [/^(?:sorted|sort|ordered|order)\b(?:\s+by\b)?\s*/, 'order'],
  [/^(?=(?:largest|smallest|biggest|highest|lowest|ascending|descending)\b)/, 'order'],
]
const SPLIT = /\s+(?=(?:by|per|across|for|where|only|top|first|sorted|ordered|largest|smallest|biggest|highest|lowest)\b)/

/** Free text as segments: [{kind (or null), term}], in order. */
export function segments(text) {
  const clean = String(text || '').toLowerCase()
    .replace(/^\s*(?:show(?:\s+me)?|what(?:'s| is| are| was)?|give me|list)\b\s*/, '').replace(/[,?]/g, ' ').trim()
  if (!clean) return []
  return clean.split(SPLIT).map(part => {
    for (const [re, kind] of SLOT_WORDS) {
      if (re.test(part)) return { kind, term: part.replace(re, '').trim(), raw: part.trim() }
    }
    return { kind: null, term: part.trim(), raw: part.trim() }
  })
}

function score(term, token) {
  if (!term) return 1
  let total = 0
  for (const w of term.split(/\s+/).filter(Boolean)) {
    let best = 0
    for (const [text, weight] of token.fields) {
      const t = String(text).toLowerCase()
      if (t.split(/[^a-z0-9%]+/).some(x => x.startsWith(w))) best = Math.max(best, weight)
      else if (t.includes(w)) best = Math.max(best, weight / 2)
    }
    if (!best) return 0
    total += best
  }
  return total + (token.label.toLowerCase() === term ? 5 : 0)
}

/**
 * The tokens that match one segment, best first (at most *max*). *scope* is
 * the slot the person clicked, used when the text names none; an empty term
 * lists the whole slot.
 */
export function suggest(model, q, values, segment, scope, max = 8) {
  const kind = segment?.kind || scope || null
  const term = segment?.term || ''
  let pool = tokens(model, q, values).filter(t => !kind || t.kind === kind)
  if (kind === 'limit' && /^\d+$/.test(term)) {
    const n = Number(term)
    if (n > 0 && measureNames(q).length) pool = [limitToken(n)]
  }
  if (!kind && !term) return []
  // Values are many: they come up for a word, not for an empty "for".
  if (!kind && term.length < 2) pool = pool.filter(t => t.kind !== 'filter')
  const lookup = kind === 'limit' ? term.replace(/^(\d+)$/, 'top $1') : term
  return pool
    .map((t, i) => ({ t, s: score(lookup, t), i }))
    .filter(x => x.s > 0)
    .sort((a, b) => b.s - a.s || KIND_RANK[a.t.kind] - KIND_RANK[b.t.kind] || a.i - b.i)
    .slice(0, max)
    .map(x => x.t)
}

/** What a slot offers next when the input is empty and focused. */
export const nextSlot = q => (!measureNames(q).length ? 'measure' : !(q.dimensions || []).length ? 'dimension' : null)

/**
 * Apply typed text: each earlier segment becomes its best token; the last
 * becomes *chosen* (the highlighted suggestion) or its best. Returns the new
 * query and the text left over (segments nothing matched).
 */
export function resolve(model, q, values, text, scope, chosen) {
  const segs = segments(text)
  if (!segs.length) return { q: chosen ? tidy(chosen.pick(q)) : q, left: '' }
  let cur = q
  const left = []
  segs.forEach((seg, i) => {
    const last = i === segs.length - 1
    const pick = last && chosen ? chosen : suggest(model, cur, values, seg, i === 0 ? scope : null, 1)[0]
    if (pick) cur = tidy(pick.pick(cur))
    else left.push(seg.raw)
  })
  return { q: cur, left: left.join(' ').trim() }
}

// ── The model's example questions ────────────────────────────────────────────

const wordsOf = text => String(text || '').toLowerCase().split(/[^a-z0-9%&]+/).filter(Boolean)

// How many words of *phrase* the question holds in a row, each a question word
// that starts with it ("sectors" holds "sector"); 0 when it does not hold all.
function holds(words, phrase) {
  const ph = wordsOf(phrase)
  if (!ph.length) return 0
  for (let i = 0; i + ph.length <= words.length; i++) {
    if (ph.every((p, k) => words[i + k].startsWith(p))) return ph.length
  }
  return 0
}

// The longest phrase of *phrases* the question holds, in words.
const best = (words, phrases) => Math.max(0, ...phrases.map(p => holds(words, p)))

/**
 * A model's example question (its `questions:`) as far as its words name a
 * measure and a dimension, by label, identifier or synonym: a word match, no
 * language model. The longest match wins, the first declared on a tie; "most",
 * "largest" and the like order by the measure, largest first. Null when no
 * measure matches: then the question picks only the model.
 */
export function questionQuery(model, question) {
  const words = wordsOf(question)
  let measure = null
  let score = 0
  for (const m of model?.measures || []) {
    const s = best(words, [m.label, humanise(m.name), m.name.replace(/_/g, ' '), ...(m.synonyms || [])])
    if (s > score) { measure = m; score = s }
  }
  const fact = measure && (model.facts || []).find(f => f.runnable_measures?.includes(measure.name))
  if (!fact) return null
  let dimension = null
  score = 0
  for (const d of model.dimensions || []) {
    if (!(d.name in (fact.foreign_keys || {}))) continue
    for (const [i, attr] of (d.attributes || []).entries()) {
      const ref = `${d.name}.${attr}`
      const about = attributeInfo(model, ref)
      // The dimension's own synonyms ("borrower") name its first attribute.
      const s = best(words, [about.label, humanise(attr), attr.replace(/_/g, ' '), ...(about.synonyms || []),
        ...(i === 0 ? d.synonyms || [] : [])])
      if (s > score) { dimension = ref; score = s }
    }
  }
  const most = words.some(w => /^(most|largest|biggest|highest|top)$/.test(w))
  return tidy({
    fact: fact.name, measures: [measure.name], dimensions: dimension ? [dimension] : [], filters: {},
    ...(most && dimension ? { order_by: [{ column: measure.name, desc: true }] } : {}),
  })
}

// ── Keep this: the question as a one-figure draft ────────────────────────────

/** The draft's path: `<model>/<measures>_by_<dimensions>`, unused so far. */
export function keepPath(folder, q, taken = []) {
  const dims = (q.dimensions || []).map(d => d.split('.').pop())
  const base = [measureNames(q).slice(0, 2).join('_and_'), dims.length ? `by_${dims.join('_')}` : '']
    .filter(Boolean).join('_').toLowerCase().replace(/[^a-z0-9_]+/g, '_').replace(/^_+|_+$/g, '').slice(0, 60) || 'answer'
  const used = new Set(taken)
  let path = `${folder}/${base}`
  for (let n = 2; used.has(path); n++) path = `${folder}/${base}_${n}`
  return path
}

// The formats a kit figure accepts (tracebi/reports/figure_markup.py TABLE_FORMATS).
const KIT_FORMATS = new Set(['comma', 'compact', 'currency', 'currency0', 'currency_compact', 'decimal', 'percent'])
// A typed number of two or more characters (tracebi/reports/app_lane.py _NUMERIC_TOKEN).
const TYPED_NUMBER = /\d[\d,.]*\d/
// Text inside a JSX attribute or a comment: one line, no quote or brace to escape.
const attr = s => String(s).replace(/\s+/g, ' ').replace(/"/g, '”').replace(/[{}<>]/g, '').trim()

/**
 * The two files "Keep this" writes into a new report draft: report.json with
 * one binding, `answer`, holding the question's query (never its numbers),
 * and app.jsx, one figure of that binding on the report system. Every value
 * the page shows is a kit figure, so the build stamps and checks it.
 */
export function keepFiles({ model, modelLabel, detail, q, rows }) {
  const query = requestOf(detail, q)
  const ms = measureNames(q)
  const dims = q.dimensions || []
  const shape = !dims.length ? 'number' : answerShape(q, { rows, data: [], columns: [] })
  const sentence = sentenceOf(detail, q)
  // The headline is the question; a typed number in it would fail the build's
  // check, so the count and the filters go to the meta line, a label.
  let title = sentenceOf(detail, { ...q, filters: {} }, { limit: false })
  let kicker = modelLabel
  const meta = [q.limit > 0 ? `Top ${q.limit}` : '', ...filterWords(detail, q.filters)].filter(Boolean)
  if (TYPED_NUMBER.test(title)) { kicker = `${modelLabel} · ${title}`; title = 'An answer kept from Ask' }
  const fmt = m => (Array.isArray(q.measures) ? declared(detail, m)?.format : null)
  const kitFormat = (m, prop) => (KIT_FORMATS.has(fmt(m)) ? ` ${prop}="${fmt(m)}"` : '')

  let figure
  if (shape === 'number') {
    figure = [
      '        <div className="tb-grid">',
      ...ms.map((m, i) => `          <Kpi${i ? '' : ' lead'} binding="answer" cell="${m}" label="${attr(measureLabel(detail, q, m))}"${kitFormat(m, 'format')} id="fig-${m}" />`),
      '        </div>',
    ]
  } else if (shape === 'chart') {
    figure = [
      '        <section className="tb-card">',
      `          <Chart binding="answer" type="barh" x="${dims[0]}" y="${ms[0]}"${kitFormat(ms[0], 'valueFormat')} id="fig-answer" />`,
      '        </section>',
    ]
  } else {
    const formats = ms.filter(m => KIT_FORMATS.has(fmt(m))).map(m => `${JSON.stringify(m)}: "${fmt(m)}"`)
    figure = [
      '        <section className="tb-card">',
      `          <Table binding="answer" columns={${JSON.stringify([...dims, ...ms])}}` +
        (formats.length ? ` formats={{ ${formats.join(', ')} }}` : '') +
        `${rows > 10 ? ' rows="all"' : ''} id="fig-answer" />`,
      '        </section>',
    ]
  }
  const imports = shape === 'number' ? 'Kpi' : shape === 'chart' ? 'Chart' : 'Table'
  const app = [
    `// Kept from Ask: ${attr(sentence)}.`,
    `// One figure of the binding "answer" in report.json, a live query against ${attr(modelLabel)}:`,
    '// the build stamps it and traces it. Reshape the page freely;',
    '// keep binding, cell, x and y literal strings (docs/reference/app-jsx.md).',
    `import { Masthead, Footer, ${imports} } from "tracebi";`,
    '',
    'export default function App() {',
    '  return (',
    '    <div className="min-h-screen bg-page text-ink">',
    '      <main className="tb-page space-y-8 px-6 py-8">',
    `        <Masthead kicker="${attr(kicker)}" title="${attr(title)}"${meta.length ? ` period="${attr(meta.join(' · '))}"` : ''}>`,
    '          Kept from Ask: one question of the model, answered by a live query.',
    '        </Masthead>',
    ...figure,
    '        <Footer />',
    '      </main>',
    '    </div>',
    '  );',
    '}',
    '',
  ].join('\n')
  const report = {
    name: title === 'An answer kept from Ask' ? kicker : title,
    description: `Kept from Ask: ${sentence}.`,
    data: { answer: { model, query } },
  }
  return { 'report.json': JSON.stringify(report, null, 2) + '\n', 'app.jsx': app }
}
