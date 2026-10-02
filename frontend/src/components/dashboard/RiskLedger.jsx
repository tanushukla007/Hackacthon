import { useNavigate } from 'react-router-dom'
import { Band, Panel, Section } from '../common/Primitives'
import { inrShort, n, pct } from '../../utils/format'

export default function RiskLedger({ top }) {
  const nav = useNavigate()
  if (!top) return null
  return (
      <Section title="Highest assessed behavioural risk" count={`${top.accounts.length} of ${n(top.ranked_from)} accounts`}>
        <Panel pad={false}>
          <table className="ledger">
            <thead>
              <tr>
                <th style={{ width: 28 }}>#</th>
                <th>Account</th><th>Assessment</th><th>Role (assessed)</th>
                <th className="n">In-deg</th><th className="n">Out-deg</th>
                <th className="n">Received</th><th className="n">Fwd</th><th className="n">Fam</th>
              </tr>
            </thead>
            <tbody>
              {top.accounts.map((a, i) => (
                <tr key={a.account_id} className="clickable"
                    onClick={() => nav(`/accounts/${a.account_id}`)}>
                  <td className="dim num">{i + 1}</td>
                  <td className="id">{a.account_id}{a.is_hub && <span className="dim"> ·hub</span>}</td>
                  <td><Band band={a.band} score={a.mri} /></td>
                  <td><span className="role">{a.role}</span></td>
                  <td className="n">{a.in_degree}</td>
                  <td className="n">{a.out_degree}</td>
                  <td className="n">{inrShort(a.total_in)}</td>
                  <td className="n">{a.forward_ratio.toFixed(2)}</td>
                  <td className="n">{a.signal_families}/3</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
        <Panel style={{ marginTop: -1 }}>
          <div className="tiny">Calibration regime: {top.calibration_regime}</div>
          <div className="note" style={{ marginTop: 6 }}>{top.disclaimer}</div>
        </Panel>
      </Section>
  )
}

export function ScoreDistribution({ distribution }) {
  const max = Math.max(...(distribution?.histogram.map((h) => h.count) || [1]))
  return (
      <Section title="Score distribution">
        <Panel>
          {distribution && (
            <>
              <div className="hist" role="img" aria-label="Distribution of mule risk index across all accounts">
                {distribution.histogram.map((h, i) => (
                  <div key={i} className="col" style={{ height: `${(h.count / max) * 100}%` }}
                       title={`MRI ${h.from.toFixed(0)}–${h.to.toFixed(0)}: ${n(h.count)} accounts`} />
                ))}
              </div>
              <div className="tiny" style={{ display: 'flex', justifyContent: 'space-between', marginTop: 4 }}>
                <span>MRI 0</span><span>50</span><span>100</span>
              </div>
              <div style={{ marginTop: 10, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 18px' }}>
                {['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'].map((b) => (
                  <div key={b} className="fieldrow">
                    <span className="k"><Band band={b} /></span>
                    <span className="v">
                      {n(distribution.bands[b] || 0)}
                      <small> · {pct(((distribution.bands[b] || 0) / distribution.accounts) * 100, 1)}</small>
                    </span>
                  </div>
                ))}
              </div>
              <div className="tiny" style={{ marginTop: 10 }}>Role shapes observed</div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 18px' }}>
                {Object.entries(distribution.roles).map(([r, c]) => (
                  <div key={r} className="fieldrow">
                    <span className="k"><span className="role">{r}</span></span>
                    <span className="v">{n(c)}</span>
                  </div>
                ))}
              </div>
            </>
          )}
        </Panel>
      </Section>
  )
}
