import { useCallback } from 'react'
import { useSearchParams, Link } from 'react-router-dom'
import { useModels } from '../api'
import { pathWithModelScope } from '../modelScope'

/** Read / write the shared `?model=` scope (survives chain navigation). */
export function useModelScope() {
  const [params, setParams] = useSearchParams()
  const model = params.get('model') || ''
  const setModel = useCallback((next) => {
    setParams(prev => {
      const copy = new URLSearchParams(prev)
      const cur = copy.get('model') || ''
      if ((next || '') === cur) return prev
      if (next) copy.set('model', next)
      else copy.delete('model')
      return copy
    }, { replace: true })
  }, [setParams])
  return [model, setModel]
}

/** Dropdown on the chain strip: All models, or one connected model. */
export function ModelScopeSelect() {
  const { data } = useModels()
  const names = (data || []).map(m => m.name).sort()
  const [model, setModel] = useModelScope()
  if (names.length < 2) return null
  return (
    <label style={{
      display: 'inline-flex', alignItems: 'center', gap: 6,
      marginLeft: 'auto', fontSize: 11.5, color: 'var(--muted)',
    }}>
      <span style={{ fontWeight: 600 }}>Model</span>
      <select
        value={model}
        onChange={e => setModel(e.target.value)}
        aria-label="Filter by connected model"
        style={{
          background: 'var(--surface)', color: 'var(--text)',
          border: '1px solid var(--border)', borderRadius: 6,
          fontSize: 12, padding: '3px 8px', maxWidth: 220,
        }}
      >
        <option value="">All models</option>
        {names.map(n => <option key={n} value={n}>{n}</option>)}
      </select>
    </label>
  )
}

/** Chain step link that keeps the current model scope. */
export function ScopedChainLink({ path, model, children, ...rest }) {
  return <Link to={pathWithModelScope(path, model)} {...rest}>{children}</Link>
}
