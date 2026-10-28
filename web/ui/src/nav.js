// The app's frame: four places, each for one job.
//
//   Reports  /                  the library as a directory: its projects (top-level
//                               folders), then a row of covers per project; ?model=<m>
//                               filters it. The sidebar is its folder tree (folders.js),
//                               then Data, Review and Docs
//            /?folder=<path>    one project's (or folder's) page: its reports by kind, its
//                               models; ?project=<path> is the same page (movedTo)
//            /reports/<name>    one report as a page of its own (<name> is folder/slug)
//            /ask               a question of one model; ?model=<m> picks it. Not a place
//                               of its own: a question is about one model, so it is asked
//                               from that model's project or its Data page (Ask this model)
//   Data     /data              a directory, like the library: the sidebar nests its
//                               four folders under it, and every page under /data
//                               keeps that frame (DataFrame in pages/Data.jsx). A
//                               folder's page has the folder's name as its h1; a
//                               thing's page has a breadcrumb (Data › Warehouse ›
//                               fact_holdings) and its own name.
//            Data is a console: one list shape for every kind of resource
//            (components/ResourceTable.jsx: search ?q=, filter chips ?filter=,
//            sortable headers ?sort=, -name for descending) and one page shape
//            for every resource (components/ResourcePage.jsx: its name, type
//            and status, actions top right, then tabs at ?tab=, Overview when
//            absent: Overview · its own · Lineage · Activity · Agents · Settings,
//            a tab it has nothing for left out). Status is a column, in
//            words.js statusWords' words.
//            /data              the Data home, a status board (pages/DataHome.jsx):
//                               a card per folder with one health pill, Needs
//                               attention (the graph's gaps and unreachable
//                               sources), Agent access, Recent activity, Schedules
//            /data/lineage      the map (GET /api/graph), one lane per stage,
//                               sources → transforms → warehouse → models → reports,
//                               read through a lens (?lens=coverage|flow|freshness|
//                               trust|access; Coverage when absent). ?node=<id> selects
//                               a piece (the graph's id, kind:name) and its passport
//                               rows sit beside the map; ?lane=sources|transforms|
//                               warehouse|models|reports focuses a lane. Every page's
//                               View lineage opens it on that page's node; /data?lens=,
//                               ?node= and ?lane= (the map was the home) land here
//            /data/sources      every connection and every file under inputs/, one
//                               list; /data/sources/<name> one connection's page,
//                               /data/sources/inputs the folder's
//            /data/sources/<connection>/<table>  one source table; under inputs
//                               the table is a path that keeps its slashes
//            /data/transforms   every file in transforms/; /data/transforms/<name>
//                               one transform's page, whether or not a pipeline runs it
//            /data/warehouse    every warehouse table, a list (?view=table) or the
//                               data browser grouped by the transform that wrote it
//                               (?view=schema; ?table=<id> selects a table, ?group=<id>
//                               a transform's group, and either alone opens it);
//                               /data/warehouse/<table> one warehouse table's page
//            /data/models       one row per model; /data/models/<m> one model's page,
//                               its Schema tab the data browser (?table=<t> selects a
//                               table, ?measure= its fact, ?view=measures|
//                               relationships|storage|code|agent opens that fold of
//                               the summary; any of them alone opens Schema).
//                               /data/models/<m>/transform is not a page: it lands on
//                               the transform the model's pipeline runs (else the model)
//            Nothing under /data is narrowed to a model: a page's Lineage tab says
//            what feeds it. The sidebar's four folders open their lists; every
//            list keeps its address, and ⌘K finds it.
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
// /data?view=map, /data/<model>/…, /data/tables/…, /data/sources?source=,
// /handbook, /getting-started, /reports?r=<name>) redirects into these (movedTo;
// Moved in components/Scope.jsx), keeping its query but ?model=.
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
    sub: 'The handbook: concepts, guides and reference, versioned with the workspace.' },
]

// Data's folders, in the order the data moves: the sidebar nests the four
// lists under Data (SIDEBAR_FOLDERS), and each is the h1 of its own page. The
// home is Data's own page, /data; Lineage, the map, is one click from every
// page (View lineage).
export const DATA_FOLDERS = [
  { key: 'overview',   label: 'Data',       path: '/data',
    sub: 'What feeds what, and what needs a person: every source, transform, table and model, with its status.' },
  { key: 'lineage',    label: 'Lineage',    path: '/data/lineage',
    sub: 'The workspace as one map, left to right: what feeds what, read through a lens. Select any piece for its rows.' },
  { key: 'sources',    label: 'Sources',    path: '/data/sources',
    sub: 'Where the data comes from: database connections, and files under inputs/.' },
  { key: 'transforms', label: 'Transforms', path: '/data/transforms',
    sub: 'The files in transforms/: each reads the sources and writes tables into the warehouse.' },
  { key: 'warehouse',  label: 'Warehouse',  path: '/data/warehouse',
    sub: 'Every table the transforms wrote, and the joins the models declare over them.' },
  { key: 'models',     label: 'Models',     path: '/data/models',
    sub: 'The models over the warehouse: what each is made from, and what reads it.' },
]
export const dataFolder = key => DATA_FOLDERS.find(f => f.key === key)

/** The folders the sidebar nests under Data: the four lists. */
export const SIDEBAR_FOLDERS = DATA_FOLDERS.filter(f => !['overview', 'lineage'].includes(f.key))

// Review's tabs, in order: Attention is /review itself.
export const REVIEW_TABS = [
  { key: 'review', label: 'Attention', path: '/review' },
  ...PAGES.filter(p => p.parent === 'review'),
]

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

const seg = s => encodeURIComponent(s)
// A path under inputs/ keeps its slashes, each segment encoded.
const segs = s => String(s).split('/').map(encodeURIComponent).join('/')

/** Data's own page: the home, a status board. */
export const overviewPath = () => '/data'

/** The map, with the graph node *node* (kind:name) selected when one is given. */
export const lineagePath = (node = '') => `/data/lineage${qs({ node })}`

/** Every connection and the inputs/ folder. */
export const sourcesPath = () => '/data/sources'

/** One connection, or the inputs/ folder (*name* `inputs`). */
export const sourcePath = name => `/data/sources/${seg(name)}`

/** One table of a connection, or (*conn* `inputs`) one file under inputs/. */
export const sourceTablePath = (conn, table) => `/data/sources/${seg(conn)}/${segs(table)}`

/** Every file in transforms/. */
export const transformsPath = () => '/data/transforms'

/** One transform's page. */
export const transformPath = name => `/data/transforms/${seg(name)}`

/** The warehouse browser. */
export const warehousePath = () => '/data/warehouse'

/**
 * One warehouse table's page. *warehouse* only when two warehouses hold a
 * table of that name; otherwise the page finds the one that holds it.
 */
export const warehouseTablePath = (table, warehouse = '') =>
  `/data/warehouse/${seg(table)}${qs({ warehouse })}`

/** Every model, one row each. */
export const modelsPath = () => '/data/models'

/** One model's page. */
export const modelPath = name => `/data/models/${seg(name)}`

/**
 * The older names for these, kept for their callers: the board, *model*'s
 * page, or what was one of its tabs (`transform` lands on the transform its
 * pipeline runs, `sources` on Sources, `runs` on History narrowed to it).
 */
export function dataPath(model = '', tab = '') {
  if (!model) return overviewPath()
  if (tab === 'transform') return `${modelPath(model)}/transform`
  if (tab === 'sources') return sourcesPath()
  if (tab === 'runs') return historyPath(model)
  return modelPath(model)
}

/**
 * One table's page, wherever it lives: *source* is a connector's name or
 * `inputs`. A warehouse table's page moves itself to /data/warehouse/<table>,
 * because only the table API knows which connectors are warehouses.
 */
export const tablePath = (source, table) => sourceTablePath(source, table)

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
 * page (placeOf gives Review). On Data, `tab` is the folder (DATA_FOLDERS)
 * the address sits in, whatever its depth, and `model` names the model on a
 * model's page; an older address under /data (one Moved sends on) is in no
 * folder.
 */
export function whereAmI(pathname) {
  const path = pathname.replace(/(.)\/+$/, '$1')
  const hit = PLACE_OF.find(([re]) => re.test(path))
  if (!hit) return null
  if (hit[1] !== 'data') return { page: hit[1], model: '', tab: null }
  const scoped = path.match(/^\/data\/([^/]+)(?:\/([^/]+))?/)
  if (!scoped) return { page: 'data', model: '', tab: 'overview' }
  const folder = dataFolder(scoped[1])
  if (!folder || folder.key === 'overview') return { page: 'data', model: '', tab: null }
  const model = folder.key === 'models' && scoped[2] ? decodeURIComponent(scoped[2]) : ''
  return { page: 'data', model, tab: folder.key }
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
  // A project's page keeps its address, /?folder=<path>; ?project=<path> is that page too.
  if (path === '/' && q.get('project') && !q.has('folder')) return to('/', { folder: q.get('project') }, ['project'])
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
  // The Map is Lineage; a model's map is its own page's Lineage tab.
  if (path === '/map' || path === '/data/map' || (path === '/data' && q.get('view') === 'map')) {
    return q.get('model') ? to(dataPath(q.get('model')), {}, ['model', 'view']) : to(lineagePath(), {}, ['view'])
  }
  // The map was Data's home: its lens, selection and lane are Lineage's now;
  // /data?model=<m> lit that model's path, its node selected under Flow.
  if (path === '/data' && q.get('model')) {
    return to(lineagePath(), { lens: 'flow', node: `model:${q.get('model')}` }, ['model'])
  }
  if (path === '/data' && ['lens', 'node', 'lane'].some(k => q.has(k))) return to(lineagePath())
  if (path === '/data' && q.get('m')) return to(modelPath(q.get('m')), {}, ['m'])
  // Data was five tabs, a model's page with four more (/data/<m>/model,
  // transform, sources, runs) and tables at /data/tables/…: each thing has a
  // page of its own now, and nothing under /data is narrowed to a model.
  const table = path.match(/^\/data\/tables\/([^/]+)\/(.+)$/)
  if (table) return to(`/data/sources/${table[1]}/${table[2]}`, {}, ['model'])
  if (/^\/data\/(sources|transforms|warehouse|models)$/.test(path) && ['model', 'source', 'file'].some(k => q.has(k))) {
    if (q.get('source')) return to(sourcePath(q.get('source')), {}, ['source', 'model'])
    if (q.get('file')) return to(transformPath(q.get('file')), {}, ['file', 'model'])
    return to(path, {}, ['model'])
  }
  const old = path.match(/^\/data\/([^/]+)(?:\/(model|transform|sources|runs))?$/)
  if (old && !dataFolder(old[1]) && old[1] !== 'tables') {
    const model = decodeURIComponent(old[1])
    if (old[2] === 'runs') return to('/runs', { model })
    return to(dataPath(model, old[2] === 'model' ? '' : old[2] || ''), {}, ['model'])
  }
  // The model list is Models, behind the board; /models?m=<model> was one model.
  if (path === '/models') return q.get('m') ? to(dataPath(q.get('m')), {}, ['m']) : to(modelsPath())
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
