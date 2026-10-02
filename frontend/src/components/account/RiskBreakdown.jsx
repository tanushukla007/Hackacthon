import { Band, Bar } from '../common/Primitives'

/** The score is never shown without its components (§15). */
export default function RiskBreakdown({ risk }) {
  if (!risk) return null
  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 9, marginBottom: 7 }}>
        <span className="mono" style={{ fontSize: 26 }}>{risk.mri}</span>
        <Band band={risk.band} />
        <span className="tiny" style={{ marginLeft: 'auto' }}>MRI / 100</span>
      </div>
      <Bar value={risk.mri} band={risk.band} />
      {risk.solo_cap_applied && (
        <div className="note warn" style={{ marginTop: 8 }}>
          Capped: terminal signals alone cannot produce a critical assessment.
        </div>
      )}
      <div style={{ marginTop: 11 }}>
        {risk.components.map((c) => (
          <div className="comp" key={c.key}>
            <span className="lab">{c.label}</span>
            <span className="sc">{c.score}<span className="dim">/{c.weight}</span></span>
            <span style={{ gridColumn: '1 / -1' }}><Bar value={c.score} max={c.weight} /></span>
            <span className="why">{c.reason}</span>
          </div>
        ))}
      </div>
      <div className="tiny" style={{ marginTop: 9 }}>calibration · {risk.calibration_regime}</div>
      <div className="note" style={{ marginTop: 6 }}>{risk.disclaimer}</div>
    </div>
  )
}
