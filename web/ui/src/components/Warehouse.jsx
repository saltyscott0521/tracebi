import { Fragment } from 'react'
import { Link } from 'react-router-dom'

import { useWarehouses } from '../api'
import { useModelLabel } from './Scope'
import { KindGlyph } from './DataBrowser'
import { TransformName, useTransformHome } from '../pages/Connectors'
import { Chip, ErrorDetail, Spinner, Time } from './Shared'
import { count } from '../format'
import { dataPath, tablePath } from '../nav'

// What a warehouse holds, as a list of its tables grouped by the transform
// that wrote them: each group says once what that transform's run read and
// what its checks say; each row is a table (its name opens the table page)
// with its rows, columns, readers and its checks' state. The contract line is
// what the sink said about itself (never "verified") and it does not colour
// anything else.

export const CONTRACT = {
  satisfied: { tone: '', label: 'Checks passed', title: 'The sink satisfied its contract, and the table is unchanged since.' },
  stale: { tone: 'warn', label: 'Changed since checked', title: 'The table changed after its checks last passed: they no longer describe this data.' },
  no_contract: { tone: 'none', label: 'No checks', title: 'No checks cover this table.' },
}

// The contract's note is what the transform says it did, in its author's
// words: shown as stated, never as a check.
function ContractNote({ note }) {
  if (!note) return null
  return <p className="wb-meta" style={{ whiteSpace: 'pre-line' }}>The transform's note, as it states it: {note}</p>
}

/**
 * A sink contract in words: its checks named by the file that declares them
 * (`contract.file`, else the record's name), and its note. *subject* is what
 * changed when it is stale: one table, or a table of a transform's group.
 */
export function ContractLine({ contract, subject = 'This table' }) {
  const where = <code>{contract.file || contract.transform}</code>
  if (contract.status === 'satisfied') {
    return (
      <>
        <p className="wb-meta">
          The sink satisfied its contract: {count(contract.checks, 'check')} in{' '}
          {where}{contract.checked_at && <>, checked <Time iso={contract.checked_at} /></>}.
        </p>
        <ContractNote note={contract.note} />
      </>
    )
  }
  if (contract.status === 'stale') {
    return (
      <>
        <p className="wb-meta">
          {subject} changed after the checks in {where} last passed
          {contract.checked_at && <> (<Time iso={contract.checked_at} />)</>}. Re-run the transform to check it again.
        </p>
        <ContractNote note={contract.note} />
      </>
    )
  }
  return <p className="wb-meta">No checks cover this table: its transform declares none for it.</p>
}

// What one outside input was on the run: the connection's table (its own
// page), live with its fingerprint, or the committed snapshot that stood in.
export function ReadInput({ src }) {
  const dot = src.ref.indexOf('.')
  const ref = dot > 0
    ? <Link to={tablePath(src.ref.slice(0, dot), src.ref.slice(dot + 1))}><code>{src.ref}</code></Link>
    : <code>{src.ref}</code>
  return src.snapshot
    ? <>{ref} (snapshot <code>{src.snapshot}</code>)</>
    : <>{ref} <span title={src.fingerprint ? `fingerprint ${src.fingerprint}` : undefined}>(live)</span></>
}

// The dense list: one row per table, its name the link to its page; a view
// marked, and the tables it reads named after it. *readBy* false drops the
// models column, for a page that names them once already.
export function TableList({ warehouse, tables, readBy = true }) {
  const labelOf = useModelLabel()
  return (
    <div className="whlist">
      <table className="tb-list">
        <thead>
          <tr>
            <th scope="col">Table</th>
            <th scope="col" className="num">Rows</th>
            <th scope="col" className="num">Columns</th>
            {readBy && <th scope="col">Read by</th>}
            <th scope="col">Checks</th>
          </tr>
        </thead>
        <tbody>
          {tables.map(t => {
            const c = CONTRACT[t.contract?.status] || CONTRACT.no_contract
            return (
              <tr key={t.name} data-table={t.name}>
                <td>
                  {t.kind === 'view' && <><KindGlyph view />{' '}</>}
                  <Link to={tablePath(warehouse, t.name)}><code>{t.name}</code></Link>
                  {t.bases?.length > 0 && <span className="wb-meta"> over {t.bases.join(', ')}</span>}
                </td>
                <td className="num">{t.rows == null ? '—' : Number(t.rows).toLocaleString('en-US')}</td>
                <td className="num">{t.columns}</td>
                {readBy && <td>
                  {t.read_by.length
                    ? t.read_by.map((m, i) => <Fragment key={m}>{i > 0 && ', '}<Link to={dataPath(m)}>{labelOf(m)}</Link></Fragment>)
                    : <span className="wb-meta">no model</span>}
                </td>}
                <td><Chip tone={c.tone} title={c.title}>{c.label}</Chip></td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

/** The checks of a transform's group: satisfied while every table it wrote is unchanged. */
export function groupContract(writer, tables) {
  const stale = tables.some(t => t.contract?.status === 'stale')
  return { status: stale ? 'stale' : 'satisfied', checks: writer.checks, file: writer.file,
           transform: writer.contract, note: writer.note, checked_at: writer.at }
}

/**
 * A warehouse's *tables* (a section of /api/warehouse, or a part of one)
 * grouped by the transform that wrote them, each group headed by that
 * transform, how many tables it wrote, what its run read and its checks.
 * Tables no certificate covers come last, under a header that says so.
 */
export function ByWriter({ w, tables }) {
  const home = useTransformHome()
  const shown = new Set(tables.map(t => t.name))
  const groups = (w.writers || [])
    .map(wr => ({ wr, tables: tables.filter(t => t.written_by?.contract === wr.contract) }))
    .filter(g => g.tables.length)
  const loose = tables.filter(t => !t.written_by?.contract)
  return (
    <>
      {groups.map(({ wr, tables: own }) => (
        <section key={wr.contract} className="whgroup" data-writer={wr.transform || wr.contract}
                 aria-label={`Written by ${wr.transform || wr.contract}`}>
          <p className="whgroup__head">
            {wr.transform ? <TransformName name={wr.transform} home={home} /> : <code>{wr.contract}</code>}
            {' · '}wrote {count(wr.tables.length, 'table')}
            {wr.tables.length > own.length && ` (${own.length} shown)`}
            {wr.read.length > 0 && <> · read {wr.read.map((src, i) => (
              <Fragment key={src.ref}>{i > 0 && ', '}<ReadInput src={src} /></Fragment>))} on that run</>}
            {wr.at && <> · <Time iso={wr.at} /></>}
          </p>
          <ContractLine contract={groupContract(wr, own)} subject="A table it wrote" />
          <TableList warehouse={w.name} tables={own} />
        </section>
      ))}
      {loose.length > 0 && (
        <section className="whgroup" aria-label="Written by no recorded transform">
          <p className="whgroup__head">
            No transform's checks cover {loose.length === 1 ? 'this table' : `these ${count(loose.length, 'table')}`},
            so who wrote {loose.length === 1 ? 'it' : 'them'} is not recorded.
          </p>
          <TableList warehouse={w.name} tables={loose} />
        </section>
      )}
      {shown.size === 0 && <p className="src-quiet">No table matches.</p>}
    </>
  )
}

/**
 * The Transform tab's Produces: the warehouse *connector* writes, from the
 * Warehouse tab's own listing. *only*: the table names to list (a file can
 * hold other models' tables); the rest are counted.
 */
export default function Warehouse({ connector, only }) {
  const { data, isLoading, error } = useWarehouses()
  if (isLoading) return <div className="codeview__hint"><Spinner /> Reading the warehouse…</div>
  if (error) return <ErrorDetail error={error} />
  const w = (data?.warehouses || []).find(x => x.name === connector.name)
  if (!w) return <div className="codeview__hint">This source is not a warehouse.</div>
  const model = connector.used_by?.[0] || '<model>'
  if (!w.exists) {
    return (
      <div className="codeview__hint">
        Nothing is built here yet. Run the transform: <code>tracebi run-pipeline {model}</code>
      </div>
    )
  }
  if (w.error) return <div className="codeview__hint">Could not read the warehouse: {w.error}</div>
  // TraceBi's own tables (the state store's) are never listed as data.
  const n = w.hidden_framework_tables || 0
  const hidden = n > 0 && <p className="wb-meta" title="TraceBi's own tables (tracebi_*, alembic_version) are not shown as data.">{count(n, 'framework table')} hidden</p>
  if (!w.tables.length) return <div className="codeview__hint">The warehouse has no tables yet.{hidden}</div>
  const shown = only ? w.tables.filter(t => only.has(t.name)) : w.tables
  const others = w.tables.length - shown.length
  return (
    <div className="fade-in">
      <ByWriter w={w} tables={shown} />
      {others > 0 && (
        <p className="wb-meta">The same file also holds {count(others, 'other table')}.</p>
      )}
      {hidden}
    </div>
  )
}
