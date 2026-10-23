// The app's frame: five places, each for one job.
//
//   Reports  /                  the library: every report, by folder; ?model=<m> filters it
//            /reports/<name>    one report as a page of its own (<name> is folder/slug)
//   Ask      /ask               a question of one model; ?model=<m> picks it
//   Data     /data              the chain, as four tabs (DATA_TABS), left to right:
//                               Models (/data: one row per model, its chain of sources →
//                               transform → tables → measures → reports), Sources
//                               (/data/sources: every connection and the inputs/ folder),
//                               Warehouse (/data/warehouse: every table, who wrote it,
//                               who reads it, its checks) and Map (/data/map: the models
//                               as one picture). ?model=<m> narrows Sources, Warehouse and
//                               Map to one model. /data/<m> one model: its line, then the
//                               tabs /data/<m>/model|transform|sources|runs (Model at /data/<m>)
//   Review   /review            its tabs: Attention (/review), Drafts (/review/drafts),
//                               History (/runs) and Verify (/verify), each at its own
//                               address in Review's frame; /drafts/<owner>/<kind>/<path>
//                               (one draft) is part of it. /drafts and /review#drafts
//                               land on /review/drafts
//   Docs     /docs              the handbook: /docs/get-started first, then a page per
//                               file of docs/ at /docs/<section>/<page>
//
// Who sees which place (placesFor): everyone Reports, Ask and Docs, an analyst
// also Review and Data. Data is read-only below admin: its run buttons (Refresh
// data, a step's Run) and credential forms show for an admin only. With no
// sign-in the API names everyone admin, so every place shows. The API enforces
// the roles; this is what the app shows.
//
// Every older address (/models, /m/<model>/…, /explore, /sources, /map,
// /data?view=map, /handbook, /getting-started, /reports?r=<name>) redirects into
// these (see Moved in components/Scope.jsx), keeping its query.
//
// The convention that ties a model to its reports (and what model_pipeline
// stamps): the model file models/<model>.py, its pipeline pipelines/<model>.py,
// its reports under reports/<model>/.

// The five places, then the pages inside Review (`parent`): each keeps its own
// address, and the sidebar marks Review on it. `minRole` is the least role
// that sees it.
export const PAGES = [
  { key: 'reports', label: 'Reports', path: '/', minRole: 'viewer',
    sub: 'What people read. Every report, and whether its numbers still hold.' },
  { key: 'ask',     label: 'Ask',     path: '/ask', minRole: 'viewer',
    sub: 'Ask a model a question and see the query behind the answer.' },
  { key: 'data',    label: 'Data',    path: '/data', minRole: 'analyst',
    sub: 'How the numbers are made, left to right: the sources, the warehouse the transforms write, and the models over it.' },
  { key: 'review',  label: 'Review',  path: '/review', minRole: 'analyst',
    sub: 'What waits on a person: what needs attention, drafts, what ran, and checking a file you were sent.' },
  { key: 'drafts',  label: 'Drafts',  path: '/review/drafts', parent: 'review', minRole: 'analyst' },
  { key: 'runs',    label: 'History', path: '/runs', parent: 'review', minRole: 'analyst',
    sub: 'What ran, when, for whom, and whether it reproduced.' },
  { key: 'verify',  label: 'Verify',  path: '/verify', parent: 'review', minRole: 'analyst' },
  { key: 'docs',    label: 'Docs',    path: '/docs', minRole: 'viewer',
    sub: 'The handbook: concepts, guides and reference, versioned with the project.' },
]

// Data's tabs, in the order the data flows (the first opens at /data).
export const DATA_TABS = ['models', 'sources', 'warehouse', 'map']
export const DATA_TAB_LABEL = { models: 'Models', sources: 'Sources', warehouse: 'Warehouse', map: 'Map' }

// Review's tabs, in order: Attention is /review itself.
export const REVIEW_TABS = [
  { key: 'review', label: 'Attention', path: '/review' },
  ...PAGES.filter(p => p.parent === 'review'),
]

// The tabs of a model's Data page, in order (the first opens at /data/<m>).
export const TABS = ['model', 'transform', 'sources', 'runs']

export const page = key => PAGES.find(p => p.key === key)

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

/** One of Data's tabs (DATA_TABS), narrowed to *model* when one is given. */
export const dataTabPath = (tab, model = '') =>
  `/data${tab && tab !== 'models' ? `/${tab}` : ''}${qs({ model })}`

/** Data's Sources tab: every connection and input file, or those *model* is made from. */
export const sourcesPath = (model = '') => dataTabPath('sources', model)

/** Data's Warehouse tab: every table, or *model*'s. */
export const warehousePath = (model = '') => dataTabPath('warehouse', model)

/** Data with the models drawn as one picture (the Map). */
export const mapPath = (model = '') => dataTabPath('map', model)

/** A handbook page: /docs/<section>/<page> for the API's "section--page". */
export const docPath = (name = '') => (name ? `/docs/${name.replace('--', '/')}` : '/docs')

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
  [/^\/docs(\/.*)?$/, 'docs'],
]

/**
 * Which page a pathname is ({page, model, tab}), or null for pages outside
 * the five places (an unknown address). Inside Review it is the tab's own
 * page (placeOf gives Review). On Data, `tab` is one of Data's own tabs
 * (DATA_TABS) with no `model`, or, on one model's page, `model` and which of
 * its tabs.
 */
export function whereAmI(pathname) {
  const path = pathname.replace(/(.)\/+$/, '$1')
  const hit = PLACE_OF.find(([re]) => re.test(path))
  if (!hit) return null
  if (hit[1] !== 'data') return { page: hit[1], model: '', tab: null }
  const scoped = path.match(/^\/data\/([^/]+)(?:\/([^/]+))?$/)
  if (!scoped) return { page: 'data', model: '', tab: 'models' }
  if (DATA_TABS.includes(scoped[1])) return { page: 'data', model: '', tab: scoped[1] }
  const tab = TABS.includes(scoped[2]) ? scoped[2] : null
  return { page: 'data', model: decodeURIComponent(scoped[1]), tab }
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
 * Where an older address lives now, or null when it is not one of them. Its
 * query comes along (a report named by ?r= opens as its own page; &build=1
 * still turns Build mode on).
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
  if (path === '/map') return to(mapPath())
  // The handbook and Get started are the Docs place, page for page.
  if (path === '/handbook') return to('/docs')
  if (path === '/getting-started') return to('/docs/get-started')
  const handbook = path.match(/^\/handbook\/(.+)$/)
  if (handbook) return to(`/docs/${handbook[1]}`)
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
