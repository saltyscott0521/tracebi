import { useEffect } from 'react'
import { Navigate, useNavigate, useSearchParams } from 'react-router-dom'

import { useModels } from '../api'
import { PageHeader } from '../components/Scope'
import { SkeletonCard } from '../components/Shared'
import { askPath, rememberModel } from '../nav'
import Explore from './Explore'
import Models from './Models'

// Ask: one model at a time, picked here (?model=<name>). Until Step 4 rebuilds
// it, the answer comes from the query builder (Explore).
export default function Ask() {
  const { data, isLoading } = useModels()
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const models = data || []
  const asked = params.get('model') || ''
  const known = models.some(m => m.name === asked)
  useEffect(() => { if (known) rememberModel(asked) }, [known, asked])

  if (isLoading) return <SkeletonCard />
  if (!known && models.length === 1) return <Navigate to={askPath(models[0].name)} replace />
  if (!known) return <Models pageKey="ask" />
  return (
    <>
      <PageHeader pageKey="ask">
        {models.length > 1 && (
          <label className="ask-model">
            <span>Model</span>
            <select value={asked} onChange={e => navigate(askPath(e.target.value))}>
              {models.map(m => <option key={m.name} value={m.name}>{m.label || m.name}</option>)}
            </select>
          </label>
        )}
      </PageHeader>
      <Explore key={asked} model={asked} />
    </>
  )
}
