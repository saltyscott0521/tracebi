// An Explore query, as the code that runs it: Python against the model, and
// the binding a report.json figure uses. Both come from the request Explore
// sent, so what you read is what ran.

const py = v => {
  if (v === null || v === undefined) return 'None'
  if (v === true) return 'True'
  if (v === false) return 'False'
  if (Array.isArray(v)) return `[${v.map(py).join(', ')}]`
  if (typeof v === 'object') return `{${Object.entries(v).map(([k, x]) => `${JSON.stringify(k)}: ${py(x)}`).join(', ')}}`
  return JSON.stringify(v)
}

/** The query as the keyword arguments of DataModel.query, leaving out what was not set. */
function spec(body) {
  const out = { fact: body.fact, measures: body.measures }
  if (body.dimensions?.length) out.dimensions = body.dimensions
  if (body.filters && Object.keys(body.filters).length) out.filters = body.filters
  return out
}

export function pythonOf(model, body) {
  const args = Object.entries(spec(body)).map(([k, v]) => `    ${k}=${py(v)},`).join('\n')
  return [
    'from tracebi.model_registry import get_model',
    '',
    `model = get_model(${JSON.stringify(model)})`,
    `ds = model.query(\n${args}\n)`,
    'df = ds.to_pandas()',
    '',
  ].join('\n')
}

export const bindingOf = (model, body) =>
  JSON.stringify({ my_query: { model, query: spec(body) } }, null, 2) + '\n'
