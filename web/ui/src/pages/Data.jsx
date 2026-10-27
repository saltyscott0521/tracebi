import { Fragment } from 'react'
import { Link, Navigate, useLocation, useParams } from 'react-router-dom'

import { useAppStatus, useGraph, useModels, usePipelines, useReports } from '../api'
import { ProjectFeedFold } from '../components/Workbench'
import ResourceTable, { NameCell, StatusPill } from '../components/ResourceTable'
import { count } from '../format'
import { transformOf } from '../chain'
import { statusWords } from '../words'
import {
  askPath, dataFolder, libraryPath, lineagePath, modelPath, movedTo, reportBelongsToModel, transformPath,
} from '../nav'
import { PageSub, PageTitle, SkeletonCard, SkeletonList, Time } from '../components/Shared'

/**
 * "Data › Warehouse › fact_holdings": where a thing's page sits under Data.
 * *trail* is [[path, label], …] after Data; *here* is the thing's own name,
 * set as code when *code* (a table, a transform) and as words otherwise (a
 * model's label).
 */
export function DataCrumbs({ trail = [], here, code = false }) {
  return (
    <nav aria-label="Breadcrumb" className="rp__crumb tpage__crumb">
      <Link to="/data">Data</Link>
      {trail.map(([to, text]) => (
        <Fragment key={to}><span aria-hidden="true">›</span><Link to={to}>{text}</Link></Fragment>
      ))}
      {here && <>
        <span aria-hidden="true">›</span>
        <span aria-current="page" className={code ? 'tpage__crumb-here' : 'rp__crumb-here'}>{here}</span>
      </>}
    </nav>
  )
}

/**
 * Data's one frame, around every page under /data. A folder's page (*folder*,
 * a DATA_FOLDERS key) is headed by the folder's name and one line of what it
 * holds, its *actions* at the right; a thing's page by its breadcrumb
 * (*trail*, *here*, *code*: see DataCrumbs), and its own h1 is the page's.
 * The home (`overview`) draws its own title bar. The sidebar marks the
 * folder. An older address that only its query told apart (?source=, ?file=,
 * ?model=, the map's ?lens=) moves to the page that replaced it.
 */
export function DataFrame({ folder, trail, here, code, actions, children }) {
  const { pathname, search, hash } = useLocation()
  const { data: appStatus } = useAppStatus()
  const dev = !!appStatus?.build_mode
  const moved = movedTo(pathname, search)
  if (moved) return <Navigate to={moved + hash} replace />
  const f = folder && dataFolder(folder)
  return (
    <div className="fade-in">
      {folder === 'overview' ? null : f ? (
        <header className="page-header rlist-head">
          <div>
            <PageTitle>{f.label}</PageTitle>
            <PageSub>{f.sub}</PageSub>
          </div>
          {actions && <div className="rpage__acts">{actions}</div>}
        </header>
      ) : <DataCrumbs trail={trail} here={here} code={code} />}
      {children}
      {/* In dev mode (`tracebi dev`) the agent's exhibits and your notes to it
          are here, folded, before any report exists. */}
      {dev && <ProjectFeedFold />}
    </div>
  )
}

/**
 * /data/models/<m>/transform is not a page: it lands on the transform the
 * model's pipeline runs, or on the model when it has none. The model page's
 * old Transform tab and the Refresh links that knew only the model go there.
 */
export function ModelTransform() {
  const { model } = useParams()
  const { data: pipelines, isLoading } = usePipelines()
  if (isLoading) return <SkeletonCard />
  const transform = transformOf(pipelines, model)
  return <Navigate to={transform ? transformPath(transform) : modelPath(model)} replace />
}

/**
 * Data's Models folder (/data/models): every model, one row each in the
 * console's list: its status (the graph's words), its tables, measures and
 * reports, when it was last defined, and Ask in its row menu.
 */
export default function ModelList() {
  const { data, isLoading } = useModels()
  const { data: reports } = useReports()
  const { data: graph } = useGraph()
  const byId = Object.fromEntries((graph?.nodes || []).map(n => [n.id, n]))

  const rows = (data || []).map(m => {
    const node = byId[`model:${m.name}`]
    const mine = (reports || []).filter(r => reportBelongsToModel(r, m.name))
    return {
      key: m.name, label: m.label || m.name, m, node, status: statusWords(node), reports: mine.length,
      at: node?.passport?.moved?.at || null,
    }
  })
  return (
    <DataFrame folder="models">
      {isLoading ? <SkeletonList /> : (
        <ResourceTable
          label="Models" placeholder="Find a model or measure" rows={rows} defaultSort="name"
          empty="No models yet. Create one with tracebi new-model, in models/."
          search={r => [r.m.name, r.label, ...(r.m.measures || []).map(x => x.name)].join(' ')}
          filters={[
            { key: 'all', label: 'All' },
            { key: 'unread', label: 'Nobody reads it', test: r => !!r.node?.gap },
          ]}
          count={(n, of) => `${n === of ? '' : `${n} of `}${count(of, 'model')}`}
          rowProps={r => ({ 'data-model': r.key })}
          columns={[
            { key: 'name', label: 'Name', sort: r => r.label, render: r => <NameCell to={modelPath(r.key)} label={r.label} id={r.key} /> },
            { key: 'status', label: 'Status', sort: r => r.status.text, render: r => <StatusPill status={r.status} /> },
            { key: 'tables', label: 'Tables', num: true, sort: r => r.m.tables.length, render: r => r.m.tables.length },
            { key: 'measures', label: 'Measures', num: true, sort: r => r.m.measures.length,
              render: r => <Link to={`${modelPath(r.key)}?tab=measures`}>{r.m.measures.length}</Link> },
            { key: 'reports', label: 'Reports', num: true, sort: r => r.reports,
              render: r => (r.reports ? <Link to={libraryPath(r.key)}>{r.reports}</Link> : <StatusPill status={{ text: 'None', tone: 'warn' }} />) },
            { key: 'agents', label: 'Agents', render: r => <span className="wb-meta">{r.node?.passport?.agents?.text || '—'}</span> },
            { key: 'at', label: 'Last defined', sort: r => r.at, render: r => <Time iso={r.at} relative fallback="—" /> },
          ]}
          menu={r => [
            { label: 'Ask this model', to: askPath(r.key) },
            { label: 'Measures', to: `${modelPath(r.key)}?tab=measures` },
            { label: 'Schema', to: `${modelPath(r.key)}?tab=schema` },
            { label: 'View lineage', to: lineagePath(`model:${r.key}`) },
          ]}
        />
      )}
    </DataFrame>
  )
}
