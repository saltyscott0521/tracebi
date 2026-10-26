// A connection's fields and its URL, both ways: the form's Fields and URL
// tabs are two views of one connection, and typing in either changes the
// other. The same mapping as tracebi.connections.build_url / parse_url (the
// server's, which the loader uses and the unit tests hold); this copy only
// draws the form and sends nothing, so a password never makes a round trip.

const SCHEME = { postgres: 'postgresql+psycopg', mysql: 'mysql+pymysql', snowflake: 'snowflake' }
const SCHEMES = {
  postgres: ['postgresql+psycopg', 'postgresql', 'postgres'],
  mysql: ['mysql+pymysql', 'mysql'],
  snowflake: ['snowflake'],
}
const REF = /^\$\{[A-Z_][A-Z0-9_]*\}$/
// What the URL view shows for a password while Show is off.
export const MASK = '•••'

const enc = v => (REF.test(v) || v === MASK ? v : encodeURIComponent(v))
const dec = v => { try { return decodeURIComponent(v) } catch { return v } }

/** The URL *fields* say for a postgres, mysql or snowflake connection. */
export function buildUrl(type, fields) {
  const f = {}
  Object.entries(fields || {}).forEach(([k, v]) => { if (typeof v === 'string' && v.trim()) f[k] = v.trim() })
  let auth = ''
  if (f.user) auth = enc(f.user) + (f.password ? `:${enc(f.password)}` : '') + '@'
  const query = []
  let where, path
  if (type === 'snowflake') {
    where = f.account || ''
    path = ['database', 'schema'].filter(k => f[k]).map(k => enc(f[k])).join('/')
    ;['warehouse', 'role'].forEach(k => { if (f[k]) query.push(`${k}=${encodeURIComponent(f[k])}`) })
    if (f.authenticator === 'externalbrowser') query.push('authenticator=externalbrowser')
    else if (f.authenticator === 'key_pair') {
      query.push('authenticator=snowflake_jwt')
      if (f.private_key_path) query.push(`private_key_file=${encodeURIComponent(f.private_key_path).replace(/%2F/g, '/')}`)
    }
  } else {
    where = (f.host || '') + (f.port ? `:${f.port}` : '')
    path = f.database ? enc(f.database) : ''
    if (f.ssl && type === 'postgres') query.push(`sslmode=${f.ssl}`)
    else if (f.ssl === 'on') query.push('ssl_check_hostname=true')
    if (f.connect_timeout) query.push(`connect_timeout=${f.connect_timeout}`)
    if (f.options) query.push(f.options.replace(/^[?&]+/, ''))
  }
  return `${SCHEME[type]}://${auth}${where}${path ? `/${path}` : ''}${query.length ? `?${query.join('&')}` : ''}`
}

/**
 * The fields a URL says, or null when the fields cannot say it (another
 * database or driver, no host): then it is kept as one URL.
 */
export function parseUrl(type, url) {
  const m = /^([^:/?#]+):\/\/(.*)$/.exec((url || '').trim())
  if (!m || !(SCHEMES[type] || []).includes(m[1].toLowerCase())) return null
  let rest = m[2].split('#')[0]
  const qi = rest.indexOf('?')
  const query = qi >= 0 ? rest.slice(qi + 1) : ''
  if (qi >= 0) rest = rest.slice(0, qi)
  const si = rest.indexOf('/')
  const netloc = si >= 0 ? rest.slice(0, si) : rest
  const path = si >= 0 ? rest.slice(si + 1) : ''
  const at = netloc.lastIndexOf('@')
  const hostport = at >= 0 ? netloc.slice(at + 1) : netloc
  const out = {}
  if (at >= 0) {
    const userinfo = netloc.slice(0, at)
    const ci = userinfo.indexOf(':')
    const user = ci >= 0 ? userinfo.slice(0, ci) : userinfo
    const password = ci >= 0 ? userinfo.slice(ci + 1) : ''
    if (user) out.user = dec(user)
    if (password) out.password = dec(password)
  }
  const pieces = query.split('&').filter(Boolean).map(raw => {
    const i = raw.indexOf('=')
    return [dec(i >= 0 ? raw.slice(0, i) : raw), dec(i >= 0 ? raw.slice(i + 1) : ''), raw]
  })
  if (type === 'snowflake') {
    if (!hostport) return null
    out.account = hostport
    const parts = path.split('/').filter(Boolean).map(dec)
    if (parts[0]) out.database = parts[0]
    if (parts[1]) out.schema = parts[1]
    pieces.forEach(([k, v]) => {
      if (k === 'warehouse' || k === 'role') out[k] = v
      else if (k === 'authenticator') out.authenticator = v.toLowerCase() === 'snowflake_jwt' ? 'key_pair' : v.toLowerCase()
      else if (k === 'private_key_file') out.private_key_path = v
    })
    return out
  }
  const ci = hostport.lastIndexOf(':')
  let host = hostport, port = ''
  if (ci >= 0 && /^\d+$/.test(hostport.slice(ci + 1))) { host = hostport.slice(0, ci); port = hostport.slice(ci + 1) }
  if (!host) return null
  out.host = host
  if (port) out.port = port
  if (path) out.database = dec(path)
  const options = []
  pieces.forEach(([k, v, raw]) => {
    if (type === 'postgres' && k === 'sslmode') out.ssl = v
    else if (type === 'mysql' && k === 'ssl_check_hostname' && v.toLowerCase() === 'true') out.ssl = 'on'
    else if (k === 'connect_timeout') out.connect_timeout = v
    else options.push(raw)
  })
  if (options.length) out.options = options.join('&')
  return out
}
