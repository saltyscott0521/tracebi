import { useConnectorWarehouse } from '../api'
import { Badge, ErrorDetail, Spinner } from './Shared'

// What a file-backed warehouse holds and whether each table was certified:
// rows, columns with a profile, and the sink contract's status per table, in
// plain words ("checks passed when last written"). The contract line is what
// the sink said about itself (never "verified") and it does not colour
// anything else.

const CONTRACT = {
  satisfied: { variant: 'green', label: 'checks passed', title: 'The sink satisfied its contract, and the table is unchanged since.' },
  stale: { variant: 'amber', label: 'changed since checked', title: 'The table changed after its checks last passed: they no longer describe this data.' },
  no_contract: { variant: 'gray', label: 'no checks', title: 'No checks cover this table.' },
}

const when = iso => String(iso).slice(0, 16).replace('T', ' ') + ' UTC'
const num = v => (v == null ? '—' : Number(v).toLocaleString(undefined, { maximumFractionDigits: 2 }))

function ContractLine({ contract }) {
  if (contract.status === 'satisfied') {
    return (
      <p className="wb-meta">
        The sink satisfied its contract: {contract.checks} check{contract.checks === 1 ? '' : 's'} in{' '}
        <code>{contract.transform}</code>{contract.checked_at ? `, checked ${when(contract.checked_at)}` : ''}.
      </p>
    )
  }
  if (contract.status === 'stale') {
    return (
      <p className="wb-meta">
        This table changed after the checks in <code>{contract.transform}</code> last passed
        {contract.checked_at ? ` (${when(contract.checked_at)})` : ''}. Re-run the transform to check it again.
      </p>
    )
  }
  return <p className="wb-meta">No checks cover this table: its transform declares none for it.</p>
}

function Profile({ table }) {
  if (!table.profile) return <p className="wb-meta">{table.note || table.error || 'No profile.'}</p>
  return (
    <div style={{ overflowX: 'auto' }}>
      <table className="wb-table">
        <thead>
          <tr><th>Column</th><th>Type</th><th>Nulls</th><th>Distinct</th><th>Range / top values</th></tr>
        </thead>
        <tbody>
          {Object.entries(table.profile).map(([col, p]) => (
            <tr key={col}>
              <td><code>{col}</code></td>
              <td>{p.dtype}</td>
              <td>{num(p.nulls)}</td>
              <td>{num(p.distinct)}</td>
              <td style={{ whiteSpace: 'normal' }}>
                {p.min !== undefined
                  ? `${num(p.min)} to ${num(p.max)}, mean ${num(p.mean)}`
                  : (p.top || []).join(', ')}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** *only*: the table names to list (a file can hold other models' tables); the rest are counted. */
export default function Warehouse({ connector, only }) {
  const { data, isLoading, error } = useConnectorWarehouse(connector.name)
  if (isLoading) return <div className="codeview__hint"><Spinner /> Reading the warehouse…</div>
  if (error) return <ErrorDetail error={error} />
  if (!data?.supported) return <div className="codeview__hint">This source is not a file-backed warehouse.</div>
  const model = connector.used_by?.[0] || '<model>'
  if (!data.exists) {
    return (
      <div className="codeview__hint">
        Nothing is built here yet. Run the transform: <code>tracebi run-pipeline {model}</code>
      </div>
    )
  }
  if (data.error) return <div className="codeview__hint">Could not read the warehouse: {data.error}</div>
  if (!data.tables.length) return <div className="codeview__hint">The warehouse has no tables yet.</div>
  const shown = only ? data.tables.filter(t => only.has(t.name)) : data.tables
  const others = data.tables.length - shown.length
  return (
    <div className="fade-in">
      {shown.map(t => {
        const c = CONTRACT[t.contract?.status] || CONTRACT.no_contract
        return (
          <details key={t.name} className="wb-details" style={{ marginBottom: 6 }}>
            <summary>
              <code>{t.name}</code>{' '}
              <span className="wb-meta">{t.rows.toLocaleString()} rows · {Object.keys(t.columns).length} columns</span>{' '}
              <Badge variant={c.variant} title={c.title}>{c.label}</Badge>
            </summary>
            <div style={{ paddingLeft: 16 }}>
              <ContractLine contract={t.contract || { status: 'no_contract' }} />
              <Profile table={t} />
            </div>
          </details>
        )
      })}
      {others > 0 && (
        <p className="wb-meta">The same file also holds {others} other {others === 1 ? 'table' : 'tables'}.</p>
      )}
    </div>
  )
}
