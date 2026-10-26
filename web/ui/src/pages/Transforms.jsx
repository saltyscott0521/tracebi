import { Fragment } from 'react'
import { Link } from 'react-router-dom'

import { useMe, useStartPipelineRun, useTransforms } from '../api'
import { useModelLabel } from '../components/Scope'
import { FORM_LABEL } from '../chain'
import { modelPath, transformPath, warehouseTablePath } from '../nav'
import { Badge, Btn, Empty, ErrorDetail, SkeletonList, Time, useToast } from '../components/Shared'

// Data's Transforms folder (/data/transforms): every file in transforms/, one
// row each: its form, the models it feeds (through the pipeline that runs it,
// or the tables its certificate says it wrote), the tables it wrote, the
// file its checks are declared in, and when it last wrote. Its name opens its
// own page, which every transform has. An admin may run the pipeline that
// runs it, the same run as Refresh data on its page.

// A row names this many tables, then folds the rest into "+N".
const TABLES_SHOWN = 4

// Start the pipeline that runs a transform: Refresh data, from this list.
function RunButton({ pipeline, transform, model }) {
  const toast = useToast()
  const { mutate: start, isPending } = useStartPipelineRun()
  const page = <Link to={transformPath(transform)}>its page</Link>
  const run = () => start({ pipeline }, {
    onSuccess: res => toast(res.already_running
      ? <>Already running. Its log is on {page}.</>
      : <>Started. Its log is on {page}.</>, 'info'),
    onError: err => toast(`Could not start: ${err.message}`, 'error'),
  })
  return (
    <Btn size="sm" variant="outline" disabled={isPending} onClick={run}
         title={`Run pipeline ${pipeline}${model ? `, which refreshes ${model}` : ''}`}>
      Run
    </Btn>
  )
}

// The tables a transform wrote, each a link to its page, the rest folded.
function TableNames({ tables }) {
  const shown = tables.slice(0, TABLES_SHOWN)
  const rest = tables.length - shown.length
  return (
    <>
      {shown.map((name, i) => (
        <Fragment key={name}>{i > 0 && ', '}<Link to={warehouseTablePath(name)}><code>{name}</code></Link></Fragment>
      ))}
      {rest > 0 && <span className="wb-meta" title={tables.slice(TABLES_SHOWN).join(', ')}> +{rest}</span>}
    </>
  )
}

export default function Transforms() {
  const { data, isLoading, error } = useTransforms()
  const { data: me } = useMe()
  const admin = !!me && (!me.role || me.role === 'admin')
  const labelOf = useModelLabel()

  if (isLoading) return <SkeletonList />
  if (error) return <ErrorDetail error={error} />
  const rows = data || []

  return rows.length === 0 ? (
    <Empty title="No transforms yet"
           body="A transform reads the sources and writes clean tables into the warehouse, with a contract that checks what landed. Scaffold one in transforms/:"
           command={'tracebi new-transform "Holdings"'} />
  ) : (
    <div className="whlist">
      <table className="tb-list transforms">
        <thead>
          <tr>
            <th scope="col">Transform</th>
            <th scope="col">Form</th>
            <th scope="col">Feeds</th>
            <th scope="col">Tables</th>
            <th scope="col">Checks</th>
            <th scope="col">Last wrote</th>
            {admin && <th scope="col"><span className="sr-only">Actions</span></th>}
          </tr>
        </thead>
        <tbody>
          {rows.map(t => (
            <tr key={t.name} data-transform={t.name}>
              <td><Link to={transformPath(t.name)}><code>{t.name}</code></Link></td>
              <td><Badge>{FORM_LABEL[t.form] || t.form}</Badge></td>
              <td>
                {t.models.length
                  ? t.models.map((m, i) => <span key={m}>{i > 0 && ', '}<Link to={modelPath(m)}>{labelOf(m)}</Link></span>)
                  : <span className="wb-meta">no model</span>}
              </td>
              <td>
                {t.tables.length ? <TableNames tables={t.tables} /> : <span className="wb-meta">none recorded</span>}
              </td>
              <td title={t.note || undefined}>
                {t.contract_file ? <code>{t.contract_file.split('/').pop()}</code> : <span className="wb-meta">no contract</span>}
              </td>
              <td><Time iso={t.written_at} relative fallback={<span className="wb-meta">never, here</span>} /></td>
              {admin && (
                <td className="num">
                  {t.pipelines[0] && <RunButton pipeline={t.pipelines[0]} transform={t.name} model={t.models[0]} />}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
