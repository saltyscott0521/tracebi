// The app's frame: four places, each for one job.
//
//   Reports  /                  the library as a directory: its folders, then a row of
//                               covers per folder; ?model=<m> filters it. The sidebar is
//                               its folder tree (folders.js), then Data, Review and Docs
//            /?folder=<path>    one folder's page: its reports by kind, its models
//            /reports/<name>    one report as a page of its own (<name> is folder/slug)
//            /ask               a question of one model; ?model=<m> picks it. Not a place
//                               of its own: a question is about one model, so it is asked
//                               from that model's folder or its Data page (Ask this model)
//   Data     /data              five tabs (DATA_TABS) in the order the data moves:
//                               Flow (/data: the board, one lane per stage, sources →
//                               transforms → warehouse → models → reports; ?model=<m>
//                               opens it with that model's path lit), Sources
//                               (/data/sources: every connection and the inputs/ folder),
//                               Transforms (/data/transforms: every file in transforms/),
//                               Warehouse (/data/warehouse: every table, who wrote it,
//                               who reads it, its checks) and Models (/data/models: one
//                               row per model, its chain of sources → transform → tables
//                               → measures → reports). ?model=<m> narrows Sources,
//                               Transforms and Warehouse to one model. /data/<m> one
//                               model: its line, then the tabs
//                               /data/<m>/model|transform|sources|runs (Model at /data/<m>).
//                               /data/tables/<source>/<table> one table (tablePath): its
//                               rows, columns and who uses it
//   Review   /review            its tabs: Attention (/review), Drafts (/review/drafts),
//                               History (/runs) and Verify (/verify), each at its own
//                               address in Review's frame; /drafts/<owner>/<kind>/<path>
//                               (one draft) is part of it. /drafts and /review#drafts
//                               land on /review/drafts
//   Docs     /docs              the handbook in docs/toc.yaml's order: a page per
//                               file of docs/ at /docs/<section>/<page>; the
//                               quickstart at /docs/get-started
//
// Who sees which place (placesFor): everyone Reports and Docs, an analyst
// also Review and Data. Data is read-only below admin: its run buttons (Refresh
// data, a step's Run) and credential forms show for an admin only. With no
// sign-in the API names everyone admin, so every place shows. The API enforces
// the roles; this is what the app shows.
//
// Every older address (/models, /m/<model>/…, /explore, /sources, /map, /data/map,
// /data?view=map, /handbook, /getting-started, /reports?r=<name>) redirects into
// these (see Moved in components/Scope.jsx), keeping its query.
//
// The convention that ties a model to its reports (and what model_pipeline
// stamps): the model file models/<model>.py, its pipeline pipelines/<model>.py,
// its reports under reports/<model>/.

// The four places, then the pages inside them (`parent`): Ask inside Reports,
// and Review's tabs. Each keeps its own address, and the sidebar marks the
// place it sits in. `minRole` is the least role that sees it.
export const PAGES = [
  { key: 'reports', label: 'Reports', path: '/', minRole: 'viewer',
    sub: 'What people read. Every report, and whether its numbers still hold.' },
  { key: 'ask',     label: 'Ask',     path: '/ask', parent: 'reports', minRole: 'viewer',
    sub: 'Ask a model a question and see the query behind the answer.' },
  { key: 'data',    label: 'Data',    path: '/data', minRole: 'analyst',
    sub: 'How the numbers are made, left to right: the sources, the transforms that read them, the warehouse they write, the models over it and the reports.' },
  { key: 'review',  label: 'Review',  path: '/review', minRole: 'analyst',
    sub: 'What waits on a person: what needs attention, drafts, what ran, and checking a file you were sent.' },
  { key: 'drafts',  label: 'Drafts',  path: '/review/drafts', parent: 'review', minRole: 'analyst' },
  { key: 'runs',    label: 'History', path: '/runs', parent: 'review', minRole: 'analyst',
    sub: 'What ran, when, for whom, and whether it reproduced.' },
  { key: 'verify',  label: 'Verify',  path: '/verify', parent: 'review', minRole: 'analyst' },
  { key: 'docs',    label: 'Docs',    path: '/docs', minRole: 'viewer',
    sub: 'The handbook: concepts, guides and reference, versioned with the project.' },
]

// Data's tabs: the board first (it opens at /data), then the lists behind it
// in the order the data flows.
export const DATA_TABS = ['flow', 'sources', 'transforms', 'warehouse', 'models']
export const DATA_TAB_LABEL = {
  flow: 'Flow', sources: 'Sources', transforms: 'Transforms', warehouse: 'Warehouse', models: 'Models',
}

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
 * /api/me loads) is the least: Reports and Docs, never a flash of the rest.
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

/** Data: the board; one model's page; or one tab of it. */
export function dataPath(model = '', tab = '') {
  if (!model) return '/data'
  const base = `/data/${encodeURIComponent(model)}`
  return tab ? `${base}/${tab}` : base
}

/** One of Data's tabs (DATA_TABS), narrowed to *model* when one is given. */
export const dataTabPath = (tab, model = '') =>
  `/data${tab && tab !== 'flow' ? `/${tab}` : ''}${qs({ model })}`

/** Data's Sources tab: every connection and input file, or those *model* is made from. */
export const sourcesPath = (model = '') => dataTabPath('sources', model)

/** Data's Warehouse tab: every table, or *model*'s. */
export const warehousePath = (model = '') => dataTabPath('warehouse', model)

/** Data's Transforms tab: every transform file, or those that feed *model*. */
export const transformsPath = (model = '') => dataTabPath('transforms', model)

/** The board (Data's Flow tab), with *model*'s path lit when one is given. */
export const flowPath = (model = '') => dataTabPath('flow', model)

/**
 * One table's page: /data/tables/<source>/<table>, where *source* is a
 * connector's name or `inputs` (then *table* is a path under inputs/ and keeps
 * its slashes).
 */
export const tablePath = (source, table) =>
  `/data/tables/${encodeURIComponent(source)}/${String(table).split('/').map(encodeURIComponent).join('/')}`

// Get started is the handbook's quickstart page, kept at its own short
// address: the sidebar, the palette and old links all open it there.
export const GET_STARTED = 'start--quickstart'

/** A handbook page: /docs/<section>/<page> for the API's "section--page". */
export const docPath = (name = '') => (
  name === GET_STARTED || name === 'get-started' ? '/docs/get-started'
    : name ? `/docs/${name.replace('--', '/')}` : '/docs')

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
 * the four places (an unknown address). Inside Review it is the tab's own
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
  if (!scoped) return { page: 'data', model: '', tab: 'flow' }
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
  // The Map's picture is the board; a model's map is its own page's line.
  if (path === '/map' || path === '/data/map') {
    return q.get('model') ? to(dataPath(q.get('model')), {}, ['model']) : to(flowPath())
  }
  // The model list is Models, behind the board; /models?m=<model> was one model.
  if (path === '/models') return q.get('m') ? to(dataPath(q.get('m')), {}, ['m']) : to(dataTabPath('models'))
  // The handbook and Get started are the Docs place, page for page.
  if (path === '/handbook') return to('/docs')
  if (path === '/getting-started') return to('/docs/get-started')
  const handbook = path.match(/^\/handbook\/(.+)$/)
  if (handbook) return to(`/docs/${handbook[1]}`)
  if (path === '/pipelines') return to(dataPath(q.get('model') || '', q.get('model') ? 'transform' : ''), {}, ['model'])
  const flat = {
    '/reports': '/', '/explore': '/ask', '/refresh': '/data',
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
