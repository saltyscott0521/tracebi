// What a model is made from, upstream of its warehouse: the transform its
// pipeline runs, and the connections and input files that transform reads
// (the API's read_by, from the transform files themselves). The Models
// folder's chain rows and stage ⓪ of a model's line both read it here, so
// they never disagree.

import { pipelineBelongsToModel } from './nav'

/** A transform's form (the API's sql | python | notebook) as its chip says it. */
export const FORM_LABEL = { sql: 'SQL', python: 'Python', notebook: 'notebook' }

/** The pipeline that refreshes a model: the one made for it, else any that touches it. */
export const pipelineFor = (pipelines, model) =>
  pipelines.find(p => p.model === model) || pipelines.find(p => pipelineBelongsToModel(p, model))

/** The transform *model*'s pipeline runs, by name, or null. */
export function transformOf(pipelines, model) {
  const p = pipelineFor(pipelines || [], model)
  return p ? (p.transform || null) : null
}

/**
 * {transform, connections, files}: the connections whose tables *transform*
 * reads (each with those tables) and the input files it names. With no
 * transform, nothing is known upstream of the model.
 */
export function upstreamOf({ model, pipelines, connectors, inputs }) {
  const transform = transformOf(pipelines, model)
  if (!transform) return { transform: null, connections: [], files: [] }
  const connections = (connectors || []).flatMap(c => {
    const hit = (c.read_by?.transforms || []).find(t => t.name === transform)
    return hit ? [{ name: c.name, tables: hit.tables }] : []
  })
  const files = (inputs?.files || []).filter(f => (f.read_by || []).includes(transform))
  return { transform, connections, files }
}
