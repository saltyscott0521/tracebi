import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'

import { useModels, usePipelines, useReports } from '../api'
import { MODEL_TABS } from '../components/chainSteps'
import { pipelineBelongsToModel, reportBelongsToModel } from '../modelScope'
import {
  PageTitle, PageSub, Card, Empty, Tabs, ListItem, SkeletonCard, Badge,
} from '../components/Shared'
import { ModelDetail } from './Models'
import { PipelineDetail } from './Pipelines'
import Explore from './Explore'

const TAB_LABELS = MODEL_TABS.map(t => t.label)
const KEY_BY_LABEL = Object.fromEntries(MODEL_TABS.map(t => [t.label, t.key]))
const LABEL_BY_KEY = Object.fromEntries(MODEL_TABS.map(t => [t.key, t.label]))

/**
 * One model as the unit of work.
 * Route: /models/:name?tab=contract|refresh|explore|reports
 */
export default function ModelHome() {
  const { name } = useParams()
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const { data: models, isLoading: loadingModels } = useModels()
  const { data: pipelines } = usePipelines()
  const { data: reports } = useReports()

  const known = (models || []).some(m => m.name === name)
  const tabKey = params.get('tab') || 'contract'
  const tab = LABEL_BY_KEY[tabKey] || 'Contract'
  const activeMeta = MODEL_TABS.find(t => t.label === tab) || MODEL_TABS[0]

  const setTab = (label) => {
    const next = new URLSearchParams(params)
    const key = KEY_BY_LABEL[label] || 'contract'
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
      <nav aria-label="Breadcrumb" style={{
        display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 6,
        fontSize: 11.5, color: 'var(--muted)', marginBottom: 10,
      }}>
        <Link to="/models" style={{ color: 'var(--muted)', textDecoration: 'none' }}>Models</Link>
        <span aria-hidden>›</span>
        <strong style={{ color: 'var(--accent-text)' }}>{name}</strong>
      </nav>

      <PageTitle>{name}</PageTitle>
      <PageSub>{activeMeta.ask} {activeMeta.hint}</PageSub>

      <Tabs tabs={TAB_LABELS} active={tab} onChange={setTab} />

      {tab === 'Contract' && <ModelDetail key={name} name={name} />}

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
                    navigate(`/reports?${new URLSearchParams({ r: r.name })}`)
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
