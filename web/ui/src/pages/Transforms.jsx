import { Link } from 'react-router-dom'

import { useGraph, useMe, useStartPipelineRun, useTransforms } from '../api'
import { useModelLabel } from '../components/Scope'
import ResourceTable, { NameCell, StatusPill, TypeChip } from '../components/ResourceTable'
import { Links } from '../components/ResourcePage'
import { count } from '../format'
import { FORM_LABEL, refreshWords, statusWords } from '../words'
import { lineagePath, modelPath, transformPath } from '../nav'
import { isoTitle } from '../when'
import { Empty, ErrorDetail, SkeletonList, useToast } from '../components/Shared'

// Data's Transforms folder (/data/transforms): every file in transforms/, one
// row each in the console's list: its form, its status (its checks in their
// own words, or that no pipeline runs it), how many tables it writes, the
// models it feeds, what agents may do with it, and when it last wrote. Its
// name opens its own page, which every transform has. An admin's row menu
// runs the pipeline that runs it, the same run as Refresh data on its page.

// Start the pipeline that runs a transform: Refresh data, from the row menu.
function useRun() {
  const toast = useToast()
  const { mutate: start } = useStartPipelineRun()
  return (pipeline, transform) => start({ pipeline }, {
    onSuccess: res => toast(<>{res.already_running ? 'Already running.' : 'Started.'} Its log is on{' '}
      <Link to={`${transformPath(transform)}?tab=steps`}>its page</Link>.</>, 'info'),
    onError: err => toast(`Could not start: ${err.message}`, 'error'),
  })
}

// When it last wrote: the age alone, from refreshWords (the certificate's
// time), else that phrase in full ("Not refreshed yet", "No refresh pipeline").
function LastWrote({ t }) {
  const w = refreshWords({ pipeline: t.pipelines.length > 0, writtenAt: t.written_at })
  return w.ago
    ? <time dateTime={isoTitle(w.at)} title={isoTitle(w.at)}>{w.ago}</time>
    : <span className="wb-meta">{w.text}</span>
}

export default function Transforms() {
  const { data, isLoading, error } = useTransforms()
  const { data: graph } = useGraph()
  const { data: me } = useMe()
  const admin = !!me && (!me.role || me.role === 'admin')
  const labelOf = useModelLabel()
  const run = useRun()

  if (isLoading) return <SkeletonList />
  if (error) return <ErrorDetail error={error} />
  const byId = Object.fromEntries((graph?.nodes || []).map(n => [n.id, n]))
  const rows = (data || []).map(t => {
    const node = byId[`transform:${t.name}`]
    return { key: t.name, label: t.name, t, node, status: node ? statusWords(node) : { text: '', tone: 'none' } }
  })

  return rows.length === 0 ? (
    <Empty title="No transforms yet"
           body="A transform reads the sources and writes clean tables into the warehouse, with a contract that checks what landed. Scaffold one in transforms/:"
           command={'tracebi new-transform "Holdings"'} />
  ) : (
    <ResourceTable
      label="Transforms" placeholder="Find a transform or table" rows={rows} defaultSort="name"
      search={r => [r.t.name, ...r.t.tables, ...r.t.models].join(' ')}
      filters={[
        { key: 'all', label: 'All' },
        { key: 'sql', label: 'SQL', test: r => r.t.form === 'sql' },
        { key: 'python', label: 'Python', test: r => r.t.form !== 'sql' },
        { key: 'unrun', label: 'No pipeline runs it', test: r => !r.t.pipelines.length },
      ]}
      count={(n, of) => `${n === of ? '' : `${n} of `}${count(of, 'transform')}`}
      rowProps={r => ({ 'data-transform': r.key })}
      columns={[
        { key: 'name', label: 'Name', sort: r => r.key, render: r => <NameCell to={transformPath(r.key)} label={r.key} code /> },
        { key: 'form', label: 'Form', sort: r => r.t.form, render: r => <TypeChip>{FORM_LABEL[r.t.form] || r.t.form}</TypeChip> },
        { key: 'status', label: 'Status', sort: r => r.status.text, render: r => <StatusPill status={r.status} /> },
        { key: 'writes', label: 'Writes', num: true, sort: r => r.t.tables.length,
          render: r => (r.t.tables.length
            ? <span title={r.t.tables.join(', ')}>{count(r.t.tables.length, 'table')}</span>
            : <span className="wb-meta">none recorded</span>) },
        { key: 'feeds', label: 'Feeds', wrap: true, render: r => (
          <Links items={r.t.models.map(m => ({ key: m, to: modelPath(m), label: labelOf(m) }))}
                 none={<span className="wb-meta">no model</span>} />
        ) },
        { key: 'agents', label: 'Agents', render: () => <span className="wb-meta">May propose a change</span> },
        { key: 'wrote', label: 'Last wrote', sort: r => r.t.written_at || '', render: r => <LastWrote t={r.t} /> },
      ]}
      menu={r => [
        { label: 'Open', to: transformPath(r.key) },
        { label: 'View code', to: `${transformPath(r.key)}?tab=code` },
        admin && r.t.pipelines[0] && { label: 'Refresh data', onClick: () => run(r.t.pipelines[0], r.key) },
        { label: 'View lineage', to: lineagePath(`transform:${r.key}`) },
      ]}
    />
  )
}
