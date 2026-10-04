import { Navigate, useSearchParams } from 'react-router-dom'

/**
 * /explore and /pipelines used to be peer nav destinations. They now live
 * inside a model home. Old bookmarks with ?model= land on that model's tab;
 * everything else goes to the models index.
 */
export function ExploreRedirect() {
  const [params] = useSearchParams()
  const model = params.get('model')
  if (model) {
    return <Navigate to={`/models/${encodeURIComponent(model)}?tab=explore`} replace />
  }
  return <Navigate to="/models" replace />
}

export function PipelinesRedirect() {
  const [params] = useSearchParams()
  const model = params.get('model')
  if (model) {
    return <Navigate to={`/models/${encodeURIComponent(model)}?tab=refresh`} replace />
  }
  return <Navigate to="/models" replace />
}
