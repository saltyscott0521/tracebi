import { useEffect } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'

import { useModels, usePipelines, useReports } from '../api'
import { useModelScope } from '../components/ModelScope'
import { pipelineBelongsToModel, reportBelongsToModel } from '../modelScope'
import {
  PageTitle, PageSub, Card, Empty, Tabs, ListItem, SkeletonCard, Badge,
} from '../components/Shared'
import { ModelDetail } from './Models'
import { PipelineDetail } from './Pipelines'
import Explore from './Explore'

const TABS = ['Refresh', 'Contract', 'Explore', 'Reports']
const TAB_KEYS = {
  Refresh: 'refresh',
  Contract: 'contract',
  Explore: 'explore',
  Reports: 'reports',
}
const KEY_TABS = Object.fromEntries(Object.entries(TAB_KEYS).map(([k, v]) => [v, k]))

/**
 * One model as the unit of work: its pipeline, contract, explore, and reports.
 * Route: /models/:name?tab=contract
 */
export default function ModelHome() {
  const { name } = useParams()
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const [modelScope, setModelScope] = useModelScope()
  const { data: models, isLoading: loadingModels } = useModels()
  const { data: pipelines } = usePipelines()
  const { data: reports } = useReports()

  const known = (models || []).some(m => m.name === name)
  const tabKey = params.get('tab') || 'contract'
  const tab = KEY_TABS[tabKey] || 'Contract'

  useEffect(() => {
    if (name && modelScope !== name) setModelScope(name)
  }, [name, modelScope, setModelScope])

  const setTab = (label) => {
    const next = new URLSearchParams(params)
    const key = TAB_KEYS[label] || 'contract'
    if (key === 'contract') next.delete('tab')
    else next.set('tab', key)
    setParams(next, { replace: true })
  }

  const pipeline = (pipelines || []).find(p => pipelineBelongsToModel(p, name))
  const modelReports = (reports || []).filter(r => reportBelongsToModel(r.name, name))

  if (loadingModels) {
    return <><PageTitle>{name}</PageTitle><SkeletonCard /></>
  }
  if (!known) {
    return (
      <>
        <PageTitle>Model not found</PageTitle>
        <Empty message={`No model named “${name}”.`} />
        <p style={{ marginTop: 12 }}>
          <Link to="/models" style={{ color: 'var(--accent-text)' }}>← All models</Link>
        </p>
      </>
    )
  }

  return (
    <>
      <nav aria-label="Model workspace" style={{
        display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 6,
        fontSize: 11.5, color: 'var(--muted)', marginBottom: 10,
      }}>
        <Link to="/connectors" style={{ color: 'var(--muted)', textDecoration: 'none' }}>Sources</Link>
        <span aria-hidden>›</span>
        <Link to="/models" style={{ color: 'var(--muted)', textDecoration: 'none' }}>Models</Link>
        <span aria-hidden>›</span>
        <strong style={{ color: 'var(--accent-text)' }}>{name}</strong>
      </nav>

      <PageTitle>{name}</PageTitle>
      <PageSub>
        One lineage: refresh its data, read the contract, explore, and open its reports.
      </PageSub>

      <Tabs tabs={TABS} active={tab} onChange={setTab} />

      {tab === 'Refresh' && (
        pipeline
          ? <PipelineDetail
              key={pipeline.pipeline}
              pipeline={pipeline.pipeline}
              layers={pipeline.layers || []}
            />
          : (
            <Card>
              <Empty message={`No pipeline connected to ${name}. Add pipelines/${name}.py with model_pipeline("${name}", …).`} />
            </Card>
          )
      )}

      {tab === 'Contract' && <ModelDetail key={name} name={name} />}

      {tab === 'Explore' && (
        <Explore key={name} lockedModel={name} embedded />
      )}

      {tab === 'Reports' && (
        <Card>
          {modelReports.length === 0 ? (
            <Empty message={`No reports in reports/${name}/.`} />
          ) : (
            modelReports.map((r, i) => (
              <div key={r.name} className="rise" style={{ '--i': i }}>
                <ListItem
                  name={r.name.slice(r.name.lastIndexOf('/') + 1)}
                  sub={r.description || r.name}
                  meta={<Badge variant="gray">{r.form}</Badge>}
                  onClick={() => {
                    const q = new URLSearchParams({
                      r: r.name,
                      model: name,
                    })
                    navigate(`/reports?${q}`)
                  }}
                />
              </div>
            ))
          )}
        </Card>
      )}
    </>
  )
}
