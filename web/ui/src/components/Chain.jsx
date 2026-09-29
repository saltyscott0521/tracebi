import { Link } from 'react-router-dom'
import { CHAIN } from './chainSteps'

// "You are here": the whole chain in one line, this page marked, every other
// step a link. Hover a step to read what it is for.
export default function Chain({ current }) {
  return (
    <nav aria-label="Where this page sits" style={{
      display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '2px 4px',
      fontSize: 11.5, marginBottom: 10,
    }}>
      {CHAIN.map((s, i) => (
        <span key={s.key} style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
          {i > 0 && <span aria-hidden style={{ color: 'var(--border)', fontSize: 13 }}>›</span>}
          {s.key === current
            ? <strong aria-current="page" title={s.hint} style={{
                color: 'var(--accent-text)', background: 'var(--blue-lt)', border: '1px solid var(--blue-br)',
                borderRadius: 20, padding: '1px 10px' }}>{s.label}</strong>
            : <Link to={s.path} title={`${s.ask} ${s.hint}`} style={{
                color: 'var(--muted)', textDecoration: 'none', padding: '1px 6px', borderRadius: 20 }}>{s.label}</Link>}
        </span>
      ))}
    </nav>
  )
}
