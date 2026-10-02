import { useEffect, useState } from 'react'
import { onApiEvent } from '../../services/apiClient'
import { useTheme } from '../../theme'
import { n } from '../../utils/format'

/**
 * The instrument strip. Latency is taken from the backend's own
 * meta.processing_ms (§41) alongside measured wall time - nothing invented.
 */
export default function StatusStrip({ dataset }) {
  const { theme, toggle } = useTheme()
  const [last, setLast] = useState(null)
  useEffect(() => onApiEvent(setLast), [])
  const st = dataset?.status?.state ?? '—'
  const cls = st === 'READY' ? 'ok' : st === 'FAILED' ? 'bad' : 'warn'
  const s = dataset?.summary

  return (
    <div className="strip">
      <div className="mark">
        <span className="glyph" aria-hidden />
        <b>ABHEDYA-CHAKRA</b>
      </div>
      <div className="readouts">
        <div className={`readout ${cls}`}>
          <span className="k">dataset</span>
          <span className="v">{st}{dataset?.status?.current_stage ? ` · ${dataset.status.current_stage}` : ''}</span>
        </div>
        <div className="readout">
          <span className="k">rows</span><span className="v">{s ? n(s.rows) : '—'}</span>
        </div>
        <div className="readout">
          <span className="k">accounts</span><span className="v">{s ? n(s.accounts) : '—'}</span>
        </div>
        <div className="readout" title="sha256 of the raw source bytes — printed on every document">
          <span className="k">fingerprint</span><span className="v">{s?.fingerprint ?? '—'}</span>
        </div>
        <div className="readout">
          <span className="k">last call</span>
          <span className="v">{last ? `${last.processingMs ?? '?'} ms backend / ${last.wallMs} ms wall` : '—'}</span>
        </div>
        <div className="readout grow" title="request id of the last API call">
          <span className="k">request</span>
          <span className="v">{last?.requestId ?? '—'}{last?.code ? ` · ${last.code}` : ''}</span>
        </div>
        <button
          className="themeswitch"
          onClick={toggle}
          aria-label={`Switch to the ${theme === 'dark' ? 'light' : 'dark'} sheet`}
          title={`Switch to the ${theme === 'dark' ? 'light' : 'dark'} sheet`}
        >
          {theme === 'dark' ? 'LIGHT' : 'DARK'}
        </button>
      </div>
    </div>
  )
}
