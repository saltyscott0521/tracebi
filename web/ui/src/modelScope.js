/**
 * Shared model scope — drill the chain on one connected model.
 *
 * Convention (and what model_pipeline stamps): pipeline.model / pipeline name
 * ↔ models/<name> ↔ reports/<name>/…. URL: ?model=<name>, kept across nav.
 */

export function reportBelongsToModel(reportName, model) {
  if (!model) return true
  return reportName === model || reportName.startsWith(`${model}/`)
}

export function pipelineBelongsToModel(pipeline, model) {
  if (!model) return true
  if (!pipeline) return false
  // Prefer the stamped connection; fall back to the file/registry name.
  const connected = pipeline.model || pipeline.pipeline
  return connected === model
}

export function modelBelongsToScope(modelName, model) {
  if (!model) return true
  return modelName === model
}

/** Keep ?model= when moving between chain pages; drop page-local keys. */
export function pathWithModelScope(path, model) {
  if (!model) return path
  const q = new URLSearchParams({ model })
  return `${path}?${q}`
}
