import { useEffect, useRef } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'

import { useGraph, useModel, useReports, useRuns } from '../api'
import { useLineFacts } from '../components/TheLine'
import { checksWords, movedWords, refreshWords, statusWords } from '../words'
import EditAsDraft from '../components/EditAsDraft'
import CodeView from '../components/CodeView'
import { StateChip } from '../components/Passport'
import ResourcePage, { ActivityList, Details, Links } from '../components/ResourcePage'
import { AgentContext, ModelDetail, ModelMeasures, grainSentence } from './Models'
import { count } from '../format'
import { askPath, libraryPath, modelsPath, reportBelongsToModel, reportPagePath, transformPath } from '../nav'
import { BtnLink, SkeletonCard, useToast } from '../components/Shared'
import { DataFrame } from './Data'

// What changed when a run ends: every fact on the page may read differently.
const AFTER_A_RUN = ['pipelines', 'history', 'warehouse', 'warehouses', 'desk', 'reports', 'models', 'model', 'graph']

// The model page's older addresses: a table, a measure or a fold of the
// summary named alone opens Schema (the data browser that reads them);
// ?view=measures opens Measures.
function olderTab(params) {
  if (params.get('tab')) return null
  if (params.get('view') === 'measures' && !params.get('table')) return 'measures'
  return ['table', 'view', 'measure'].some(k => params.get(k)) ? 'schema' : null
}

/**
 * A model's page (/data/models/<m>), in the console's shape: Overview (the
 * Semantic layer's facts as a grid), Schema (the data browser: its tables,
 * joins and the Semantic layer), Measures, Lineage (what feeds it, what it
 * feeds), Activity (its reports' builds), Agents (what an agent receives),
 * Settings (the file it is defined in). Ask this model and Edit as a draft
 * are top right.
 */
function ModelPage({ model }) {
  const facts = useLineFacts(model)
  const { transform } = facts
  const { data: detail, isLoading } = useModel(model)
  const { data: graph } = useGraph()
  const { data: reports } = useReports()
  const { data: builds } = useRuns('report_build')
  const [params] = useSearchParams()
  const toast = useToast()
  const qc = useQueryClient()
  const label = detail?.label || model
  const file = transform.pipeline?.transform

  // A refresh started elsewhere (its transform's page, the folder) changes
  // what the page says; a toast says how it ended.
  const was = useRef(false)
  useEffect(() => {
    if (was.current && !transform.running) {
      AFTER_A_RUN.forEach(key => qc.invalidateQueries({ queryKey: [key] }))
      toast(transform.failed ? 'The refresh failed. Its transform’s page says why.' : `Refreshed ${label}.`,
        transform.failed ? 'error' : 'info')
    }
    was.current = transform.running
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [transform.running])

  if (isLoading || !detail) {
    return <DataFrame trail={[[modelsPath(), 'Models']]} here={label}><SkeletonCard /></DataFrame>
  }
  const node = (graph?.nodes || []).find(n => n.id === `model:${model}`)
  const p = node?.passport
  const mine = (reports || []).filter(r => reportBelongsToModel(r, model))
  const names = new Set(mine.map(r => r.name))
  const built = (builds || []).filter(r => names.has(r.target)).slice(0, 30)
  const grain = grainSentence(detail)

  const overview = () => (
    <>
      {transform.failed && (
        <p role="status" className="overview__alert">
          <strong>
            <span aria-hidden="true">✕</span> {refreshWords({ failedAt: transform.lastAt }).text}
            {transform.failure && <>: {checksWords({ failed: transform.failure.failed }).text}</>}.
          </strong>
          {transform.failure && facts.builtCount > 0 && <span>The built reports were made from the tables it replaced.</span>}
          {file && <Link to={transformPath(file)}>See why</Link>}
        </p>
      )}
      <Details items={[
        ['About', detail.description || null],
        ['Grain', grain || null],
        ['Shape', `${count(detail.tables.length, 'table')} · ${count((detail.measures || []).length, 'measure')} · ${count((detail.dimensions || []).length, 'dimension')}`],
        ['From', p?.origin ? <code>{p.origin}</code> : null],
        ['Read by', <Links items={mine.map(r => ({ key: r.name, to: reportPagePath(r.name), label: r.display_name || r.name }))}
                           none="No report" />],
        ['Last moved', p ? movedWords(p.moved, 'model') : null],
        ['Trust', <StateChip state={p?.trust} />],
        ['Agents', <StateChip state={p?.agents} />],
        ['Defined in', detail.source_file ? <code>{detail.source_file}</code> : null],
        (detail.owners || []).length > 0 && ['Owners', `${detail.owners.join(', ')} (only they or an admin publish changes to it)`],
        (detail.synonyms || []).length > 0 && ['Also called', detail.synonyms.join(', ')],
        (detail.questions || []).length > 0 && ['Questions', (detail.questions || []).map((q, i) => (
          <span key={q}>{i > 0 && ' · '}<Link to={askPath(model)}>{q}</Link></span>
        ))],
      ]} />
    </>
  )
  return (
    <ResourcePage
      trail={[[modelsPath(), 'Models']]} here={label}
      title={label} id={model} type="model" status={node ? statusWords(node) : null}
      sub={<>{node?.sub || `${count(detail.tables.length, 'table')} · ${count((detail.measures || []).length, 'measure')}`}
        {' · '}{mine.length ? <Link to={libraryPath(model)}>{count(mine.length, 'report')}</Link> : 'no report'}
        {detail.source_file && <> · <code>{detail.source_file}</code></>}</>}
      node={`model:${model}`} tab={olderTab(params)}
      actions={<>
        {/* A question is about one model, so it is asked from here (or its folder). */}
        <BtnLink size="sm" variant="primary" to={askPath(model)}>Ask this model</BtnLink>
        <EditAsDraft kind="models" path={model} size="sm" />
      </>}
      tabs={[
        { key: 'overview', label: 'Overview', render: overview },
        { key: 'schema', label: 'Schema', render: () => <ModelDetail name={model} /> },
        { key: 'measures', label: 'Measures', count: (detail.measures || []).length, render: () => <ModelMeasures name={model} /> },
        built.length > 0 && { key: 'activity', label: 'Activity', render: () => (
          <ActivityList items={built.map(r => ({
            key: r.id,
            status: r.status === 'succeeded' ? { text: 'Built', tone: 'ok' } : { text: 'Build failed', tone: 'bad' },
            what: r.display_name || r.target, to: reportPagePath(r.target), sub: r.actor ? `by ${r.actor}` : null, at: r.started,
          }))} />
        ) },
        { key: 'agents', label: 'Agents', render: () => <AgentContext name={model} /> },
        { key: 'settings', label: 'Settings', render: () => (
          <>
            <Details items={[
              ['Defined in', detail.source_file ? <code>{detail.source_file}</code> : null],
              ['Refreshed by', file ? <Link to={transformPath(file)}><code>{file}</code></Link> : 'No pipeline'],
            ]} />
            <CodeView kind="models" name={model} />
          </>
        ) },
      ]}
    />
  )
}

export default ModelPage
