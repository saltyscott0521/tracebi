// The app's frame: a model switcher, and the same pages beneath it for every
// model. Pick a model and every page narrows to it; pick "All models" and
// every row says which model it belongs to.
//
//   /m/<model>            Data model        /models     (all: pick a model)
//   /m/<model>/explore    Explore           /explore    (all: pick a model)
//   /m/<model>/refresh    Refresh           /refresh
//   /m/<model>/reports    Reports           /reports
//   /m/<model>/sources    Sources           /sources
//   /m/<model>/runs       Runs              /runs
//
// The convention that ties them (and what model_pipeline stamps): the model
// file models/<model>.py, its pipeline pipelines/<model>.py, its reports
// under reports/<model>/.

export const PAGES = [
  { key: 'model',   label: 'Data model', icon: 'models',     all: '/models',
    sub: 'Its tables, how they join, and the measures it defines.' },
  { key: 'explore', label: 'Explore',    icon: 'explore',    all: '/explore',
    sub: 'Ask a question and see the query behind the answer.' },
  { key: 'refresh', label: 'Refresh',    icon: 'pipelines',  all: '/refresh',
    sub: 'Rebuild the data, then the reports that read it.' },
  { key: 'reports', label: 'Reports',    icon: 'reports',    all: '/reports',
    sub: 'What people read. Every number carries its receipt.' },
  { key: 'sources', label: 'Sources',    icon: 'connectors', all: '/sources',
    sub: 'Where the data is kept: a file, a folder or a database.' },
  { key: 'runs',    label: 'Runs',       icon: 'runs',       all: '/runs',
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

/** A report's model is its folder: reports/<model>/<name>. */
export function modelOfReport(name) {
  const i = (name || '').indexOf('/')
  return i === -1 ? '' : name.slice(0, i)
}

export const reportBelongsToModel = (name, model) =>
  !model || modelOfReport(name) === model

/** A pipeline's model: the one model_pipeline stamped, else its name. */
export const modelOfPipeline = p => (p && (p.model || p.pipeline)) || ''

export const pipelineBelongsToModel = (p, model) =>
  !model || modelOfPipeline(p) === model

/** Where to open a report: in its model's frame when it has one. */
export function reportPath(name) {
  const model = modelOfReport(name)
  return `${pagePath('reports', model)}?${new URLSearchParams({ r: name })}`
}

const LAST = 'tracebi-model'
export function rememberModel(model) {
  try { localStorage.setItem(LAST, model || '') } catch { /* private window */ }
}
export function lastModel() {
  try { return localStorage.getItem(LAST) || '' } catch { return '' }
}
