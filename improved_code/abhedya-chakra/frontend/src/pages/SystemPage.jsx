import { useApi } from '../hooks/useApi'
import { getIngestStatus, getProfile, getSystemStatus, startIngest } from '../services/datasetService'
import { ErrorState, Loading, Panel, Section } from '../components/common/Primitives'
import IngestProgress from '../components/dashboard/IngestProgress'
import { n } from '../utils/format'

export default function SystemPage({ dataset }) {
  const sys = useApi(() => getSystemStatus(), [dataset.status?.state])
  const ing = useApi(() => getIngestStatus(), [], { pollMs: 900 })

  return (
    <div className="page">
      <div className="page-head">
        <span className="idx">05</span><h1>System</h1>
        <div className="sub">Only measured values appear here. Fields the system has not
          measured are shown as null rather than filled with a plausible number.</div>
      </div>
      {sys.loading && <Loading />}
      {sys.error && <ErrorState error={sys.error} onRetry={sys.reload} />}
      {sys.data && (
        <div className="grid g3">
          <div>
            <Section title="Dataset">
              <Panel>
                {Object.entries(sys.data.dataset).filter(([k]) => k !== 'stage_timings_ms').map(([k, v]) => (
                  <div className="fieldrow" key={k}>
                    <span className="k">{k}</span>
                    <span className="v">
                      {v === null ? <span className="dim">null</span>
                        : k === 'loaded_at' ? new Date(v * 1000).toISOString().slice(0, 19).replace('T', ' ')
                        : k === 'ingest_seconds' ? `${v}s`
                        : typeof v === 'number' ? n(v) : String(v)}
                    </span>
                  </div>
                ))}
              </Panel>
            </Section>
            <Section title="Stage timings">
              <Panel>
                {Object.entries(sys.data.dataset.stage_timings_ms || {}).map(([k, v]) => (
                  <div className="fieldrow" key={k}><span className="k">{k}</span><span className="v">{v} ms</span></div>
                ))}
              </Panel>
            </Section>
            <Section title="Ingest control">
              <Panel>
                <div className="tiny" style={{ marginBottom: 7 }}>CSV files found in data/raw</div>
                {(ing.data?.available_files || []).map((f) => (
                  <div className="fieldrow" key={f}>
                    <span className="k mono" style={{ fontSize: 11 }}>{f}</span>
                    <span className="v">
                      <button className="linky" onClick={() => startIngest(f)}>ingest</button>
                    </span>
                  </div>
                ))}
                {!ing.data?.available_files?.length && (
                  <div className="note warn">No CSV in data/raw. Drop the dataset file there.</div>
                )}
              </Panel>
            </Section>
          </div>

          <div>
            <Section title="Risk model configuration">
              <Panel>
                {Object.entries(sys.data.config.mri_weights).map(([k, v]) => (
                  <div className="fieldrow" key={k}><span className="k">{k}</span><span className="v">{v}</span></div>
                ))}
                <div className="tiny" style={{ marginTop: 8 }}>Bands</div>
                {sys.data.config.mri_bands.map((b) => (
                  <div className="fieldrow" key={b.band}>
                    <span className="k">{b.band}</span><span className="v">{b.from}–{b.to - 1}</span>
                  </div>
                ))}
                <div className="tiny" style={{ marginTop: 8 }}>Caps and windows</div>
                <div className="fieldrow"><span className="k">max_nodes</span><span className="v">{sys.data.config.caps.max_nodes}</span></div>
                <div className="fieldrow"><span className="k">max_edges</span><span className="v">{sys.data.config.caps.max_edges}</span></div>
                <div className="fieldrow"><span className="k">max_hops</span><span className="v">{sys.data.config.caps.max_hops}</span></div>
                <div className="fieldrow"><span className="k">hub threshold (degree)</span><span className="v">{sys.data.config.hub_threshold_degree}</span></div>
                <div className="fieldrow"><span className="k">velocity windows</span>
                  <span className="v">{sys.data.config.velocity_windows.join(' · ')}s</span></div>
              </Panel>
            </Section>
            <Section title="Legal basis">
              <Panel>
                <div className="fieldrow"><span className="k">Production of records</span>
                  <span className="v" style={{ fontSize: 11 }}>{sys.data.legal_basis.production}</span></div>
                <div className="fieldrow"><span className="k">Seizure / freeze</span>
                  <span className="v" style={{ fontSize: 11 }}>{sys.data.legal_basis.seizure}</span></div>
              </Panel>
            </Section>
          </div>

          <div>
            <Section title="Performance budgets">
              <Panel>
                {Object.entries(sys.data.budgets_ms).map(([k, v]) => (
                  <div className="fieldrow" key={k}><span className="k">{k}</span><span className="v">{v}</span></div>
                ))}
                <div className="tiny" style={{ marginTop: 9 }}>Measured benchmarks</div>
                {!sys.data.benchmarks && (
                  <div className="note warn" style={{ marginTop: 5 }}>
                    <b>null.</b> No benchmark has been run on this machine yet, so no number is
                    shown. Run <span className="mono">make bench</span> to populate this.
                  </div>
                )}
                {sys.data.benchmarks?.stale && (
                  <div className="note warn" style={{ marginTop: 5 }}>
                    <b>Stale.</b> {sys.data.benchmarks.note}
                  </div>
                )}
                {sys.data.benchmarks && !sys.data.benchmarks.stale && (
                  <>
                    <div className="fieldrow"><span className="k">measured at</span>
                      <span className="v" style={{ fontSize: 11 }}>{sys.data.benchmarks.measured_at.replace('T', ' ')}</span></div>
                    <div className="fieldrow"><span className="k">ingest (full pipeline)</span>
                      <span className="v">{sys.data.benchmarks.ingest_seconds}s</span></div>
                    <div className="fieldrow"><span className="k">trace p50 / p95</span>
                      <span className="v">{sys.data.benchmarks.trace_ms.p50} / {sys.data.benchmarks.trace_ms.p95} ms</span></div>
                    <div className="fieldrow"><span className="k">trace max</span>
                      <span className="v">{sys.data.benchmarks.trace_ms.max} ms</span></div>
                    <div className="fieldrow"><span className="k">score an account p95</span>
                      <span className="v">{sys.data.benchmarks.score_account_ms.p95} ms</span></div>
                    <div className="fieldrow"><span className="k">samples</span>
                      <span className="v">{sys.data.benchmarks.trace_samples} traces</span></div>
                    <div className="tiny" style={{ marginTop: 6 }}>
                      Measured on this machine, on this dataset fingerprint. Not a published
                      claim, not an estimate.
                    </div>
                  </>
                )}
              </Panel>
            </Section>
            <Section title="Ground truth">
              <Panel>
                <div className="fieldrow"><span className="k">Labels available</span>
                  <span className="v">{String(sys.data.ground_truth.labels_available)}</span></div>
                <div className="fieldrow"><span className="k">Accuracy metrics</span>
                  <span className="v dim">null</span></div>
                <div className="note stop" style={{ marginTop: 8 }}>{sys.data.ground_truth.note}</div>
              </Panel>
            </Section>
            <IngestProgress status={ing.data || dataset.status} />
          </div>
        </div>
      )}
    </div>
  )
}
