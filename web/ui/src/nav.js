// The app's frame: a model switcher, and the same pages beneath it for every
// model. Pick a model and every page narrows to it; pick "All models" and
// every row says which model it belongs to.
//
//   /m/<model>/sources    Sources           /sources
//   /m/<model>/refresh    Refresh           /refresh
//   /m/<model>            Data model        /models     (all: pick a model)
//   /m/<model>/explore    Explore           /explore    (all: pick a model)
//   /m/<model>/reports    Reports           /reports
//   /m/<model>/runs       Runs              /runs
//
// The convention that ties them (and what model_pipeline stamps): the model
// file models/<model>.py, its pipeline pipelines/<model>.py, its reports
// under reports/<model>/.

// In the order the data moves: where it is kept, how it is rebuilt, what it
// means; then what you do with it. The sidebar shows the two groups.
export const GROUPS = [
  { key: 'build', label: 'Build' },
  { key: 'use',   label: 'Use' },
]

export const PAGES = [
  { key: 'sources', group: 'build', label: 'Sources',    icon: 'connectors', all: '/sources',
    sub: 'Where the data is kept: a file, a folder or a database.' },
  { key: 'refresh', group: 'build', label: 'Refresh',    icon: 'pipelines',  all: '/refresh',
    sub: 'Rebuild the data, then the reports that read it.' },
  { key: 'model',   group: 'build', label: 'Data model', icon: 'models',     all: '/models',
    sub: 'Its tables, how they join, and the measures it defines.' },
  { key: 'explore', group: 'use',   label: 'Explore',    icon: 'explore',    all: '/explore',
    sub: 'Ask a question and see the query behind the answer.' },
  { key: 'reports', group: 'use',   label: 'Reports',    icon: 'reports',    all: '/reports',
    sub: 'What people read. Every number carries its receipt.' },
  { key: 'runs',    group: 'use',   label: 'Runs',       icon: 'runs',       all: '/runs',
    sub: 'What ran, when, for whom, and whether it reproduced.' },
]

export const page = key => PAGES.find(p => p.key === key)

/** Where *pageKey* lives for *model* ('' = all models). */
export function pagePath(pageKey, model) {
  if (!model) return page(pageKey).all
  const base = `/m/${encodeURIComponent(model)}`
  return pageKey === 'model' ? base : `${base}/${pageKey}`
}

/** Which page and model a pathname is, or null for pages outside the frame. */
export function whereAmI(pathname) {
  const scoped = pathname.match(/^\/m\/([^/]+)(?:\/([^/]+))?\/?$/)
  if (scoped) {
    const key = scoped[2] || 'model'
    return page(key) ? { model: decodeURIComponent(scoped[1]), page: key } : null
  }
  const all = PAGES.find(p => p.all === pathname.replace(/\/+$/, ''))
  return all ? { model: '', page: all.key } : null
}

/** The folder a report sits in: reports/<folder>/<name>. */
function folderOf(name) {
  const i = (name || '').indexOf('/')
  return i === -1 ? '' : name.slice(0, i)
}

/**
 * The models a report belongs to: the ones its data bindings read (the API's
 * `models`). Its folder is only the convention, used when nothing is known.
 */
export function reportModels(report) {
  if (report?.models?.length) return report.models
  const folder = folderOf(report?.name)
  return folder ? [folder] : []
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

/** Where to open a report: under its (first) model when one is known. */
export function reportPagePath(name, models = []) {
  return `${pagePath('reports', models[0] || '')}?${new URLSearchParams({ r: name })}`
}

const LAST = 'tracebi-model'
export function rememberModel(model) {
  try { localStorage.setItem(LAST, model || '') } catch { /* private window */ }
}
export function lastModel() {
  try { return localStorage.getItem(LAST) || '' } catch { return '' }
}
