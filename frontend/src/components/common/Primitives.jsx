import { bandGlyph } from '../../utils/format'

export const Section = ({ title, count, right, children }) => (
  <section className="sec">
    <header>
      <span className="sq" aria-hidden />
      <h2>{title}</h2>
      <span className="rule" aria-hidden />
      {count !== undefined && <span className="count">{count}</span>}
      {right}
    </header>
    {children}
  </section>
)

export const Panel = ({ pad = true, children, style }) => (
  <div className="panel" style={style}>{pad ? <div className="panel-pad">{children}</div> : children}</div>
)

export const Field = ({ k, v, title }) => (
  <div className="fieldrow" title={title}>
    <span className="k">{k}</span>
    <span className="v">{v}</span>
  </div>
)

/** Risk band: colour + label + glyph. Never colour alone. */
export const Band = ({ band, score }) => (
  <span className={`band ${band}`} title={`Assessed band ${band}`}>
    <i aria-hidden>{bandGlyph(band)}</i>{band}{score !== undefined ? ` ${score}` : ''}
  </span>
)

export const ClaimType = ({ type }) => <span className={`claimtype ${type}`}>{type}</span>

export const RowId = ({ id, onClick }) => (
  <span className="provenance clickable" onClick={onClick} role={onClick ? 'button' : undefined}
        title="source_row_id — the immutable ordinal of this row in the source CSV">
    row {id}
  </span>
)

export const Bar = ({ value, max = 100, band }) => (
  <div className={`bar ${band || ''}`}><span style={{ width: `${Math.min(100, (value / max) * 100)}%` }} /></div>
)

export const ErrorState = ({ error, onRetry }) => {
  const copy = {
    DATASET_NOT_LOADED: 'No dataset is loaded yet. Ingest a CSV from the System page before investigating.',
    ACCOUNT_NOT_FOUND: 'That account number does not appear anywhere in this dataset — neither as a sender nor as a receiver.',
    INVALID_ACCOUNT_FORMAT: 'Account numbers are 12-digit strings. Leading zeros matter and must be typed.',
    TRANSACTION_NOT_FOUND: 'No source row carries that Transaction_ID.',
    AMBIGUOUS_TRANSACTION_ID: 'That Transaction_ID appears on more than one source row. Open a specific row by its source_row_id.',
    ROW_NOT_FOUND: 'That source_row_id is outside this dataset.',
    TRACE_NOT_FOUND: 'That trace is no longer held in memory. Re-run it.',
    NO_PATH_FOUND: 'No money path was found between those accounts within the hop limit.',
    GRAPH_TOO_LARGE: 'The result exceeds the render caps. Narrow the time window or reduce hops.',
    NETWORK: 'The backend is unreachable.',
    INTERNAL_ERROR: 'The backend hit an unhandled error. The request id below identifies it in the server log.',
  }[error?.code]
  return (
    <div className="state">
      <div className="big">{copy || error?.message || 'Something went wrong.'}</div>
      {error?.code && <div className="code">{error.code}</div>}
      {error?.hint && <div className="dim" style={{ marginTop: 6 }}>{error.hint}</div>}
      {onRetry && <div style={{ marginTop: 12 }}><button className="btn" onClick={onRetry}>Retry</button></div>}
    </div>
  )
}

export const EmptyState = ({ title, hint }) => (
  <div className="state"><div className="big">{title}</div>{hint && <div className="dim">{hint}</div>}</div>
)

export const Loading = ({ label = 'Querying backend' }) => (
  <div className="state">
    <div className="dim mono" style={{ marginBottom: 8 }}>{label}…</div>
    <div style={{ display: 'grid', gap: 6, maxWidth: 320, margin: '0 auto' }}>
      <div className="skel" /><div className="skel" style={{ width: '70%' }} />
    </div>
  </div>
)
