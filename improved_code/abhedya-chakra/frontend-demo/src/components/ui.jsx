/** Small shared presentational pieces for the demo UI. */

export function Card({ title, right, children, className = '' }) {
  return (
    <section className={`card ${className}`}>
      {(title || right) && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          {title && <h2 style={{ flex: 1 }}>{title}</h2>}
          {right}
        </div>
      )}
      {children}
    </section>
  )
}

export function Stat({ label, value, sub }) {
  return (
    <div className="card stat">
      <div className="label">{label}</div>
      <div className="value">{value}</div>
      {sub && <div className="sub">{sub}</div>}
    </div>
  )
}

/**
 * Risk band. The band string comes from the backend; the UI only renders it.
 * Colour is never the only carrier of meaning - the band word is always shown.
 */
export function Band({ band, score }) {
  if (!band) return <span className="badge plain">not scored</span>
  return (
    <span className={`badge ${band.toLowerCase()}`}>
      {band}
      {score !== undefined && score !== null && <span className="mono"> {score}</span>}
    </span>
  )
}

export function KV({ k, v }) {
  return (
    <div className="kv">
      <span className="k">{k}</span>
      <span className="v">{v === null || v === undefined || v === '' ? <span className="muted">null</span> : v}</span>
    </div>
  )
}

export function ErrorBox({ error, onRetry }) {
  if (!error) return null
  return (
    <div className="notice error">
      <strong>{error.code || 'ERROR'}</strong> — {error.message}
      {error.hint && <div style={{ marginTop: 4 }}>{error.hint}</div>}
      {onRetry && (
        <div style={{ marginTop: 8 }}>
          <button onClick={onRetry}>Retry</button>
        </div>
      )}
    </div>
  )
}

export function Loading({ what = 'Loading' }) {
  return <div className="empty">{what}…</div>
}

export function Empty({ children }) {
  return <div className="empty">{children}</div>
}
