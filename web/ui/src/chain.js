// What a model is made from, upstream of its warehouse: the transform its
// pipeline runs, and the connections and input files that transform reads
// (the API's read_by, from the transform files themselves). The Models tab's
// chain rows, stage ⓪ of a model's line and the Sources tab's ?model= filter
// all read it here, so they never disagree.

import { pipelineFor } from './components/map/project'

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

/**
 * Whether connector *c* belongs on *model*'s Sources: the model reads it
 * (its warehouse), or the model's transform reads it.
 */
export function feedsModel(c, model, upstream) {
  return (c.used_by || []).includes(model) || upstream.connections.some(u => u.name === c.name)
}
