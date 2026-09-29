import { Badge } from './Shared'

// Where a connector's data physically lives: a file, a folder, a database,
// a cloud warehouse, or memory. The model file is code; this is the data.

export const KIND_LABEL = {
  file: 'File', directory: 'Folder', database: 'Database',
  cloud: 'Cloud warehouse', memory: 'Memory', unknown: 'Unknown',
}

export function fmtBytes(n) {
  if (n == null) return ''
  if (n < 1024) return `${n} B`
  if (n < 1024 ** 2) return `${(n / 1024).toFixed(0)} KB`
  return `${(n / 1024 ** 2).toFixed(1)} MB`
}

/** One line: the location, and whether it is there right now. */
export function StorageLine({ storage }) {
  if (!storage || !storage.where) return <span style={{ color: 'var(--muted)' }}>location not reported</span>
  const missing = storage.exists === false
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
      <code style={{ fontSize: 12 }}>{storage.where}</code>
      {missing && (
        <Badge variant="amber" title="Nothing at this location yet. Run the transform or pipeline that writes it.">
          not built yet
        </Badge>
      )}
      {storage.exists === true && storage.size != null && <Badge variant="gray">{fmtBytes(storage.size)}</Badge>}
    </span>
  )
}
