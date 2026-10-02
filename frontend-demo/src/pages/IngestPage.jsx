import { useEffect, useRef, useState } from 'react'
import * as api from '../api'
import { Card, ErrorBox, KV, Empty } from '../components/ui'
import { num, ms, dur, dt, inrExact } from '../format'

/**
 * Data ingestion, as a separate explicit step.
 *
 * The user picks a CSV that the backend can see in data/raw and starts the
 * load. Progress is the real stage list the backend reports, with real
 * milliseconds. No percentage bar is drawn, because the backend does not
 * report a percentage and inventing one would be a lie.
 */
export default function IngestPage({ gated, state: outerState, onIngested }) {
  const [files, setFiles] = useState([])
  const [chosen, setChosen] = useState('')
  const [stages, setStages] = useState([])
  const [state, setState] = useState('UNKNOWN')
  const [stage, setStage] = useState(null)
  const [sourceFile, setSourceFile] = useState(null)
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)
  const [summary, setSummary] = useState(null)
  const poll = useRef(null)

  const refresh = async () => {
    try {
      const { data } = await api.getIngestStatus()
      setFiles(data.available_files || [])
      setState(data.state)
      setStage(data.current_stage)
      setStages(data.stages || [])
      setSourceFile(data.source_file)
      if (data.error) setErr({ code: 'INGEST_FAILED', message: data.error })
      setChosen((c) => c || (data.source_file ?? (data.available_files || [])[0] ?? ''))
      return data.state
    } catch (e) {
      setErr(e)
      return 'FAILED'
    }
  }

  const loadSummary = async () => {
    try {
      const { data } = await api.getDatasetSummary()
      setSummary(data)
    } catch {
      setSummary(null)
    }
  }

  useEffect(() => {
    refresh().then((s) => {
      if (s === 'READY') loadSummary()
      if (s === 'LOADING') startPolling()
    })
    return () => clearInterval(poll.current)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const startPolling = () => {
    clearInterval(poll.current)
    poll.current = setInterval(async () => {
      const s = await refresh()
      if (s === 'READY' || s === 'FAILED') {
        clearInterval(poll.current)
        setBusy(false)
        if (s === 'READY') {
          await loadSummary()
          onIngested?.()
        }
      }
    }, 700)
  }

  const ingest = async () => {
    setErr(null)
    setBusy(true)
    setSummary(null)
    try {
      await api.startIngest(chosen || undefined)
      startPolling()
    } catch (e) {
      setErr(e)
      setBusy(false)
    }
  }

  const loading = state === 'LOADING' || busy
  const totalMs = stages.reduce((a, s) => a + (s.ms || 0), 0)

  return (
    <>
      {gated ? (
        <div className="notice warn" style={{ marginBottom: 16 }}>
          <strong>Step 1 of 1 — ingest a dataset.</strong> The rest of the application stays
          locked until the backend reports a loaded dataset. Nothing is cached in the
          browser, so this is the only way in.
        </div>
      ) : null}

      <h1>Data ingestion</h1>
      <p className="page-sub">
        Load a transaction CSV into the backend. Nothing else in this app works until a
        dataset is loaded, and every number shown afterwards comes from this file.
      </p>

      <div className="grid two">
        <Card title="Source file">
          {files.length === 0 ? (
            <Empty>
              No CSV found in <code>data/raw/</code>. Copy the dataset there and press refresh.
            </Empty>
          ) : (
            <div className="row">
              <div style={{ flex: 1 }}>
                <label className="field" htmlFor="csv">CSV in data/raw</label>
                <select
                  id="csv"
                  value={chosen}
                  onChange={(e) => setChosen(e.target.value)}
                  disabled={loading}
                  style={{ width: '100%' }}
                >
                  {files.map((f) => (
                    <option key={f} value={f}>{f}</option>
                  ))}
                </select>
              </div>
              <button className="primary" onClick={ingest} disabled={loading || !chosen}>
                {loading ? 'Ingesting…' : 'Ingest'}
              </button>
              <button onClick={refresh} disabled={loading}>Refresh</button>
            </div>
          )}

          <div style={{ marginTop: 14 }}>
            <KV k="backend state" v={state} />
            <KV k="loaded file" v={sourceFile} />
            <KV k="current stage" v={stage || (state === 'READY' ? 'done' : '—')} />
          </div>

          <div className="disclaimer">
            The file is read by the backend from its own disk. The browser never parses
            the CSV and never holds the rows.
          </div>
        </Card>

        <Card title="Pipeline stages">
          {stages.length === 0 ? (
            <Empty>{loading ? 'Waiting for the first stage to report…' : 'No ingest has run in this session.'}</Empty>
          ) : (
            <>
              {stages.map((s) => (
                <div className="stage" key={s.name}>
                  <span className="name">{s.name}</span>
                  <span className="ms">{ms(s.ms)}</span>
                </div>
              ))}
              <div className="stage" style={{ borderTop: '1px solid var(--border)', marginTop: 6, paddingTop: 6 }}>
                <span className="name"><strong>total</strong></span>
                <span className="ms"><strong>{ms(totalMs)}</strong></span>
              </div>
            </>
          )}
          <div className="disclaimer">
            Each line appears when that stage finishes. No percentage is shown because the
            backend does not report one — a fake progress bar would be inventing data.
          </div>
        </Card>
      </div>

      <div style={{ height: 16 }} />
      <ErrorBox error={err} onRetry={refresh} />

      {summary && (
        <>
          <div style={{ height: 16 }} />
          <Card title="Loaded dataset">
            <div className="grid two">
              <div>
                <KV k="source file" v={summary.source_file} />
                <KV k="fingerprint" v={summary.fingerprint} />
                <KV k="rows" v={num(summary.rows)} />
                <KV k="accounts" v={num(summary.accounts)} />
                <KV k="ingest seconds" v={dur(summary.ingest_seconds)} />
                <KV k="window from" v={dt(summary.time_window?.from)} />
                <KV k="window to" v={dt(summary.time_window?.to)} />
              </div>
              <div>
                <KV k="amount min" v={inrExact(summary.amount?.min)} />
                <KV k="amount median" v={inrExact(summary.amount?.median)} />
                <KV k="amount mean" v={inrExact(summary.amount?.mean)} />
                <KV k="amount max" v={inrExact(summary.amount?.max)} />
                <KV k="unique transaction ids" v={num(summary.duplicates?.unique_transaction_ids)} />
                <KV k="duplicate id surplus" v={num(summary.duplicates?.surplus)} />
                <KV k="exact duplicate rows" v={num(summary.duplicates?.exact_duplicate_rows)} />
              </div>
            </div>
            <div className="notice" style={{ marginTop: 12 }}>
              {summary.duplicates?.policy}
            </div>
          </Card>
        </>
      )}
    </>
  )
}
