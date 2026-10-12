// The app's frame: a model switcher, and beneath it the pages of one model.
// Pick a model and every page narrows to it; pick "All models" and the
// Overview lists the models, and every row says which model it belongs to.
//
//   /m/<model>             Overview, Reports stage    /models   (all: pick a model)
//   /m/<model>/reports     Overview, Reports stage    /reports
//   /m/<model>/model       Overview, Model stage
//   /m/<model>/transform   Overview, Transform stage
//   /m/<model>/explore     Explore                    /explore  (all: pick a model)
//   /m/<model>/runs        History                    /runs
//
// The Overview is "the line": ① transforms/ → ② models/ → ③ reports/, one stage
// shown at a time, each with an address of its own. /m/<model>/refresh and
// /m/<model>/sources are old addresses of the Transform stage.
//
// The convention that ties them (and what model_pipeline stamps): the model
// file models/<model>.py, its pipeline pipelines/<model>.py, its reports
// under reports/<model>/.

// Every addressable page. `all` is where it lives with no model picked; the
// stages of the Overview have no all-models page of their own, so they open
// the list of models.
export const PAGES = [
  { key: 'overview',  label: 'Overview',  all: '/models',
    sub: 'The tables a model reads, the numbers it names, and the reports that show them. Pick a model.' },
  { key: 'reports',   label: 'Reports',   all: '/reports',
    sub: 'What people read. Every number carries its receipt.' },
  { key: 'model',     label: 'Model',     all: '/models',
    sub: 'Its tables, how they join, and the measures it defines.' },
  { key: 'transform', label: 'Transform', all: '/models',
    sub: 'Rebuild the data, then the reports that read it.' },
  { key: 'explore',   label: 'Explore',   all: '/explore',
    sub: 'Ask a question and see the query behind the answer.' },
  { key: 'sources',   label: 'Sources',   all: '/sources',
    sub: 'Where the data is kept: a file, a folder or a database.' },
  { key: 'runs',      label: 'History',   all: '/runs',
    sub: 'What ran, when, for whom, and whether it reproduced.' },
]

// The three stations of the Overview's line, in the order a number is made.
export const STAGES = ['transform', 'model', 'reports']

export const page = key => PAGES.find(p => p.key === key)

/** Where *pageKey* lives for *model* ('' = all models). */
export function pagePath(pageKey, model) {
  if (!model) return page(pageKey).all
  const base = `/m/${encodeURIComponent(model)}`
  return pageKey === 'overview' ? base : `${base}/${pageKey}`
}

/**
 * Which page and model a pathname is, or null for pages outside the frame.
 * A stage of the Overview is that page, with `stage` saying which one.
 */
export function whereAmI(pathname) {
  const scoped = pathname.match(/^\/m\/([^/]+)(?:\/([^/]+))?\/?$/)
  if (scoped) {
    const model = decodeURIComponent(scoped[1])
    const key = scoped[2] || 'reports'
    if (STAGES.includes(key)) return { model, page: 'overview', stage: key }
    return ['explore', 'runs'].includes(key) ? { model, page: key, stage: null } : null
  }
  const all = PAGES.find(p => p.all === pathname.replace(/\/+$/, ''))
  return all ? { model: '', page: all.key, stage: null } : null
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
