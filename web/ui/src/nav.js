// The app's frame: four places, each for one job.
//
//   Reports  /                  the library: every report, by folder; ?model=<m> filters it
//            /reports/<name>    one report as a page of its own (<name> is folder/slug)
//   Ask      /ask               a question of one model; ?model=<m> picks it
//   Data     /data              the models, one row each; ?view=map draws them as one
//                               picture. /data/<m> one model: its line, then the tabs
//                               /data/<m>/model|transform|sources|runs (Model at /data/<m>).
//                               /data/sources every source
//   Review   /review            its tabs: Attention (/review), Drafts (/review/drafts),
//                               History (/runs) and Verify (/verify), each at its own
//                               address in Review's frame; /drafts/<owner>/<kind>/<path>
//                               (one draft) is part of it. /drafts and /review#drafts
//                               land on /review/drafts
//
// Who sees which place (placesFor): everyone Reports and Ask, an analyst also
// Review, an admin also Data. With no sign-in the API names everyone admin,
// so every place shows. The API enforces the roles; this is what the app shows.
//
// Every older address (/models, /m/<model>/…, /explore, /sources, /map,
// /reports?r=<name>) redirects into these (see Moved in components/Scope.jsx),
// keeping its query.
//
// The convention that ties a model to its reports (and what model_pipeline
// stamps): the model file models/<model>.py, its pipeline pipelines/<model>.py,
// its reports under reports/<model>/.

// The four places, then the pages inside Review (`parent`): each keeps its own
// address, and the sidebar marks Review on it. `minRole` is the least role
// that sees it.
export const PAGES = [
  { key: 'reports', label: 'Reports', path: '/', minRole: 'viewer',
    sub: 'What people read. Every report, and whether its numbers still hold.' },
  { key: 'ask',     label: 'Ask',     path: '/ask', minRole: 'viewer',
    sub: 'Ask a model a question and see the query behind the answer.' },
  { key: 'data',    label: 'Data',    path: '/data', minRole: 'admin',
    sub: 'How the numbers are made: each model, the transform that feeds it, and where the data is kept.' },
  { key: 'review',  label: 'Review',  path: '/review', minRole: 'analyst',
    sub: 'What waits on a person: what needs attention, drafts, what ran, and checking a file you were sent.' },
  { key: 'drafts',  label: 'Drafts',  path: '/review/drafts', parent: 'review', minRole: 'analyst' },
  { key: 'runs',    label: 'History', path: '/runs', parent: 'review', minRole: 'analyst',
    sub: 'What ran, when, for whom, and whether it reproduced.' },
  { key: 'verify',  label: 'Verify',  path: '/verify', parent: 'review', minRole: 'analyst' },
]

// Pages inside a place that keep a heading of their own.
const INNER = [
  { key: 'sources', label: 'Sources', sub: 'Where the data is kept: a file, a folder or a database.' },
]

// Review's tabs, in order: Attention is /review itself.
export const REVIEW_TABS = [
  { key: 'review', label: 'Attention', path: '/review' },
  ...PAGES.filter(p => p.parent === 'review'),
]

// The tabs of a model's Data page, in order (the first opens at /data/<m>).
export const TABS = ['model', 'transform', 'sources', 'runs']

export const page = key => PAGES.find(p => p.key === key) || INNER.find(p => p.key === key)

const RANK = { viewer: 0, analyst: 1, admin: 2 }

/** Whether *role* sees the page *key* (a page outside the places: everyone). */
export function mayUse(role, key) {
  const p = page(key)
  return !p?.minRole || (RANK[role] ?? 0) >= RANK[p.minRole]
}

/**
 * The places *role* sees, in the sidebar's order: the one list the sidebar,
 * the phone's drawer, the rail and the ⌘K palette draw. No role yet (while
 * /api/me loads) is the least: Reports and Ask, never a flash of the rest.
 */
export const placesFor = role => PAGES.filter(p => !p.parent && mayUse(role, p.key))

/** The place a page sits in: itself, or its parent. */
export const placeOf = key => page(key)?.parent || key

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
  [/^\/(review\/drafts|drafts)(\/.*)?$/, 'drafts'],
  [/^\/runs$/, 'runs'],
  [/^\/verify$/, 'verify'],
  [/^\/review$/, 'review'],
]

/**
 * Which page a pathname is ({page, model, tab}), or null for pages outside
 * the four places (Help, an unknown address). Inside Review it is the tab's
 * own page (placeOf gives Review). On Data, `model` and `tab`
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

export const pipelineBelongsToModel = (p, model) =>
  !model || pipelineModels(p).includes(model)

/** A report's own page: /reports/<folder>/<slug>, each segment encoded. */
export const reportPagePath = name =>
  `/reports/${String(name).split('/').map(encodeURIComponent).join('/')}`

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
