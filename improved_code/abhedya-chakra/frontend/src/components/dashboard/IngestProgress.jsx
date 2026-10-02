import { Panel, Section } from '../common/Primitives'

/**
 * Honest staged indicator (§8): the backend reports which stage it is in and
 * how long each completed stage took. It does NOT report a percentage, so we
 * do not draw one.
 */
export default function IngestProgress({ status }) {
  const stages = ['fingerprint', 'normalize', 'encode', 'facts', 'graph', 'features', 'profile', 'score']
  const done = Object.fromEntries((status?.stages || []).map((s) => [s.stage, s.ms]))
  return (
    <Section title="Ingest" count={status?.state}>
      <Panel>
        <div className="stagelist">
          {stages.map((s) => {
            const ms = done[s]
            const current = status?.current_stage === s
            return (
              <div key={s}>
                <span className="dot">{ms !== undefined ? '●' : current ? '◐' : '○'}</span>
                <span style={{ color: ms !== undefined ? 'var(--text)' : 'var(--muted)' }}>{s}</span>
                <span className="ms">{ms !== undefined ? `${ms} ms` : current ? 'running' : 'queued'}</span>
              </div>
            )
          })}
        </div>
        <div className="tiny" style={{ marginTop: 10 }}>
          No percentage is shown because the backend does not report one. Each line appears
          when that stage actually completes, with its measured duration.
        </div>
        {status?.error && <div className="note stop" style={{ marginTop: 8 }}>{status.error}</div>}
      </Panel>
    </Section>
  )
}
