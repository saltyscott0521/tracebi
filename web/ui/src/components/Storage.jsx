import { Badge, Chip } from './Shared'

// Where a connector's data physically lives: a file, a folder, a database,
// a cloud warehouse, or memory. The model file is code; this is the data.

export const KIND_LABEL = {
  file: 'File', directory: 'Folder', database: 'Database',
  cloud: 'Cloud warehouse', memory: 'Memory', unknown: 'Unknown',
}

// The engine a connector type reads with, in a reader's words.
const ENGINE = {
  DuckDBConnector: 'DuckDB', CSVConnector: 'CSV', SQLConnector: 'SQL',
  BigQueryConnector: 'BigQuery', SnowflakeConnector: 'Snowflake',
}

// A SQL connection's database, from its URL's dialect (the API's `dialect`):
// "SQL database" alone does not tell Postgres from a SQLite file.
const DIALECT = {
  postgresql: 'Postgres', sqlite: 'SQLite file', mysql: 'MySQL', mariadb: 'MariaDB',
  mssql: 'SQL Server', oracle: 'Oracle', snowflake: 'Snowflake', bigquery: 'BigQuery',
  duckdb: 'DuckDB file',
}

/** What kind of source a connector is, in words: "Postgres", "SQLite file", "DuckDB file", "Built in Python". */
export function sourceKind(c) {
  const kind = c?.storage?.kind
  if (c?.type === 'MemoryConnector') return 'Built in Python'
  if (kind === 'memory') return 'In memory'
  if (c?.type === 'SQLConnector') return DIALECT[c.dialect] || 'SQL database'
  const engine = ENGINE[c?.type] || (c?.type || '').replace(/Connector$/, '')
  return ['file', 'directory', 'database'].includes(kind) ? `${engine} ${KIND_LABEL[kind].toLowerCase()}` : engine
}

export function fmtBytes(n) {
  if (n == null) return ''
  if (n < 1024) return `${n} B`
  if (n < 1024 ** 2) return `${(n / 1024).toFixed(0)} KB`
  return `${(n / 1024 ** 2).toFixed(1)} MB`
}

/**
 * One line: the location, and whether it is there right now. A place a
 * variable sets is named by the variable (the API never reads it to say more).
 */
export function StorageLine({ storage }) {
  if (!storage || !storage.where) return <span style={{ color: 'var(--muted)' }}>location not reported</span>
  const missing = storage.exists === false
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
      {storage.variable
        ? <span style={{ fontSize: 'var(--text-caption)' }}>Set by <code style={{ fontSize: 'var(--text-sm)' }}>{storage.variable}</code></span>
        : <code style={{ fontSize: 'var(--text-sm)' }}>{storage.where}</code>}
      {missing && (
        <Chip tone="warn" title="Nothing at this location yet. Run the transform or pipeline that writes it.">
          Not built yet
        </Chip>
      )}
      {storage.exists === true && storage.size != null && <Badge variant="gray">{fmtBytes(storage.size)}</Badge>}
    </span>
  )
}
