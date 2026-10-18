// The app's frame: four places, each for one job.
//
//   Reports  /                  the library: every report, by folder; ?model=<m> filters it
//            /reports/<name>    one report as a page of its own (<name> is folder/slug)
//   Ask      /ask               a question of one model; ?model=<m> picks it
//   Data     /data              the models, one row each; ?view=map draws them as one
//                               picture. /data/<m> one model: its line, then the tabs
//                               /data/<m>/model|transform|sources|runs (Model at /data/<m>).
//                               /data/sources every source
//   Review   /review            drafts and publish requests; /drafts, /runs (History)
//                               and /verify (Verify a file) are part of it
//
// Every older address (/models, /m/<model>/…, /explore, /sources, /map,
// /reports?r=<name>) redirects into these (see Moved in components/Scope.jsx),
// keeping its query.
//
// The convention that ties a model to its reports (and what model_pipeline
// stamps): the model file models/<model>.py, its pipeline pipelines/<model>.py,
// its reports under reports/<model>/.

export const PAGES = [
  { key: 'reports', label: 'Reports', path: '/',
    sub: 'What people read. Every number carries its receipt.' },
  { key: 'ask',     label: 'Ask',     path: '/ask',
    sub: 'Ask a model a question and see the query behind the answer.' },
  { key: 'data',    label: 'Data',    path: '/data',
    sub: 'How the numbers are made: each model, the transform that feeds it, and where the data is kept.' },
  { key: 'review',  label: 'Review',  path: '/review',
    sub: 'What waits on a person: drafts and requests to publish, what ran, and checking a file.' },
]

// Pages inside a place that keep a heading of their own until Steps 3 and 4
// rebuild them.
const INNER = [
  { key: 'runs',    label: 'History', sub: 'What ran, when, for whom, and whether it reproduced.' },
  { key: 'sources', label: 'Sources', sub: 'Where the data is kept: a file, a folder or a database.' },
]

// The tabs of a model's Data page, in order (the first opens at /data/<m>).
export const TABS = ['model', 'transform', 'sources', 'runs']

export const page = key => PAGES.find(p => p.key === key) || INNER.find(p => p.key === key)

const qs = params => {
  const q = new URLSearchParams(Object.entries(params).filter(([, v]) => v))
  return q.toString() ? `?${q}` : ''
}

/** The library, narrowed to *model* when one is given. */
export const libraryPath = (model = '') => `/${qs({ model })}`

/** Ask, with *model* picked when one is given. */
export const askPath = (model = '') => `/ask${qs({ model })}`

/** Data: the models; one model's page; or one tab of it. */
export function dataPath(model = '', tab = '') {
  if (!model) return '/data'
  const base = `/data/${encodeURIComponent(model)}`
  return tab ? `${base}/${tab}` : base
}

/** Data with the models drawn as one picture (the Map). */
export const mapPath = (model = '') => `/data${qs({ view: 'map', model })}`

/** History, narrowed to *model* when one is given. */
export const historyPath = (model = '') => `/runs${qs({ model })}`

const PLACE_OF = [
  [/^\/(reports(\/.*)?)?$/, 'reports'],
  [/^\/ask$/, 'ask'],
  [/^\/data(\/.*)?$/, 'data'],
  [/^\/(review|drafts|runs|verify)(\/.*)?$/, 'review'],
]

/**
 * Which place a pathname is in ({page, model, tab}), or null for pages
 * outside the four (Help, an unknown address). On Data, `model` and `tab`
 * say which model's page and which of its tabs.
 */
export function whereAmI(pathname) {
  const path = pathname.replace(/(.)\/+$/, '$1')
  const hit = PLACE_OF.find(([re]) => re.test(path))
  if (!hit) return null
  const scoped = hit[1] === 'data' && path.match(/^\/data\/([^/]+)(?:\/([^/]+))?$/)
  if (scoped && !['map', 'sources'].includes(scoped[1])) {
    const tab = TABS.includes(scoped[2]) ? scoped[2] : null
    return { page: 'data', model: decodeURIComponent(scoped[1]), tab }
  }
  return { page: hit[1], model: '', tab: null }
}

/** The folder a report sits in: reports/<folder>/<name>. */
export function folderOf(name) {
  const i = (name || '').lastIndexOf('/')
  return i === -1 ? '' : name.slice(0, i)
}

/**
 * The models a report belongs to: the ones its data bindings read (the API's
 * `models`). Its folder is only the convention, used when nothing is known.
 */
export function reportModels(report) {
  if (report?.models?.length) return report.models
  const i = (report?.name || '').indexOf('/')
  return i === -1 ? [] : [report.name.slice(0, i)]
}

export const reportBelongsToModel = (report, model) =>
  !model || reportModels(report).includes(model)

/**
 * The models a pipeline touches: the ones it names (the API's `models`), else
 * the one model_pipeline stamped, else its own name.
 */
export function pipelineModels(p) {
  if (p?.models?.length) return p.models
  const one = p && (p.model || p.pipeline)
  return one ? [one] : []
}

/** The model a pipeline is mainly about (the first it names). */
export const modelOfPipeline = p => pipelineModels(p)[0] || ''

export const pipelineBelongsToModel = (p, model) =>
  !model || pipelineModels(p).includes(model)

/** A report's own page: /reports/<folder>/<slug>, each segment encoded. */
export const reportPagePath = name =>
  `/reports/${String(name).split('/').map(encodeURIComponent).join('/')}`

/** Where Open goes: the report's page (one address now, from any list). */
export const reportOpenPath = reportPagePath

/** The report an address opens as a page ({name}), or null. */
export function openedReport(pathname) {
  const m = pathname.match(/^\/reports\/(.+?)\/*$/)
  if (!m) return null
  const name = m[1].split('/').map(decodeURIComponent).join('/')
  return name ? { name } : null
}

/**
 * Where an address from before the four places lives now, or null when it is
 * not one of them. Its query comes along (a report named by ?r= opens as its
 * own page; &build=1 still turns Build mode on).
 */
export function movedTo(pathname, search = '') {
  const path = pathname.replace(/(.)\/+$/, '$1')
  const q = new URLSearchParams(search)
  const to = (target, add = {}, drop = []) => {
    const next = new URLSearchParams(q)
    ;['r', 'open', 'tab', ...drop].forEach(k => next.delete(k))
    Object.entries(add).forEach(([k, v]) => { if (v) next.set(k, v) })
    return `${target}${next.toString() ? `?${next}` : ''}`
  }
  const scoped = path.match(/^\/m\/([^/]+)(?:\/([^/]+))?$/)
  const r = q.get('r')
  if (r && (path === '/' || path === '/reports' || (scoped && [undefined, 'reports'].includes(scoped[2])))) {
    return to(reportPagePath(r), {}, ['model'])
  }
  if (scoped) {
    const model = decodeURIComponent(scoped[1])
    const sub = scoped[2] || ''
    if (sub === 'reports') return to('/', { model })
    if (sub === 'explore') return to('/ask', { model })
    if (sub === 'runs') return to('/runs', { model })
    if (sub === 'model' || sub === 'transform') return to(dataPath(model, sub))
    if (sub === 'refresh') return to(dataPath(model, 'transform'))
    if (sub === 'sources') return to(dataPath(model, 'sources'))
    return to(dataPath(model))
  }
  const legacy = path.match(/^\/models\/([^/]+)$/)
  if (legacy) {
    const model = decodeURIComponent(legacy[1])
    const tab = q.get('tab')
    if (tab === 'explore') return to('/ask', { model })
    if (tab === 'reports') return to('/', { model })
    return to(dataPath(model, tab === 'refresh' ? 'transform' : ''))
  }
  // A model's Reports stage is the library, narrowed to it (Step 3 retired the stage).
  const stage = path.match(/^\/data\/([^/]+)\/reports$/)
  if (stage) return r ? to(reportPagePath(r), {}, ['model']) : to('/', { model: decodeURIComponent(stage[1]) })
  if (path === '/map' || path === '/data/map') return to('/data', { view: 'map' })
  if (path === '/pipelines') return to(dataPath(q.get('model') || '', q.get('model') ? 'transform' : ''), {}, ['model'])
  const flat = {
    '/reports': '/', '/models': '/data', '/explore': '/ask', '/refresh': '/data',
    '/sources': '/data/sources', '/connectors': '/data/sources',
  }[path]
  return flat ? to(flat) : null
}

const LAST = 'tracebi-model'
export function rememberModel(model) {
  try { localStorage.setItem(LAST, model || '') } catch { /* private window */ }
}
export function lastModel() {
  try { return localStorage.getItem(LAST) || '' } catch { return '' }
}
