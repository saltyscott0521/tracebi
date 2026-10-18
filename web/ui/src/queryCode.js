// An Ask query, as the code that runs it: Python against the model, and
// the binding a report.json figure uses. Both come from the request Ask
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
  if (body.order_by?.length) out.order_by = body.order_by
  if (body.limit != null) out.limit = body.limit
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

// The query in one line, as the receipt writes it (tracebi.js queryLine):
// "fair_value by dim_issuer.sector · order fair_value desc · limit 8".
const valueText = v => (Array.isArray(v) ? `(${v.join(', ')})` : String(v))

export function queryLineOf(body) {
  const names = Array.isArray(body.measures) ? body.measures : Object.keys(body.measures || {})
  let line = names.join(', ')
  if (body.dimensions?.length) line += `${line ? ' by ' : 'by '}${body.dimensions.join(', ')}`
  const where = Object.entries(body.filters || {}).map(([k, v]) => (
    Array.isArray(v) ? `${k} in ${valueText(v)}`
      : v && typeof v === 'object' ? Object.entries(v).map(([op, x]) => `${k} ${op} ${valueText(x)}`).join(', ')
        : `${k} = ${v}`))
  if (where.length) line += ` · where ${where.join(', ')}`
  if (body.order_by?.length) {
    line += ` · order ${body.order_by.map(o => (typeof o === 'string'
      ? (o.startsWith('-') ? `${o.slice(1)} desc` : o) : `${o.column}${o.desc ? ' desc' : ''}`)).join(', ')}`
  }
  if (body.limit != null) line += ` · limit ${body.limit}`
  return line
}
