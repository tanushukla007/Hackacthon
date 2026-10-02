import { Band } from '../common/Primitives'
import { inrShort } from '../../utils/format'

/**
 * Per-trace ledger of every account the backend reached.
 * Layer and hop_distance come from the trace response; the UI never derives
 * them. Two-line account cell keeps the traced value visible at 1280px.
 */
export default function NodeLedger({ trace, selected, onSelect }) {
  return (
    <table className="ledger ledger-nodes">
      <thead>
        <tr><th>Layer</th><th>Account · value traced</th><th>Assessment</th></tr>
      </thead>
      <tbody>
        {trace.nodes.map((nd) => (
          <tr key={nd.account_id}
              className={`clickable ${selected === nd.account_id ? 'sel' : ''}`}
              onClick={() => onSelect(nd.account_id)}
              title={`${nd.layer} · hop ${nd.hop_distance} · MRI ${nd.mri} ${nd.band}`}>
            <td className="mono layercell">{nd.layer}</td>
            <td>
              <div className="id">{nd.account_id}{nd.is_hub && <span className="dim"> ·hub</span>}</div>
              <div className="sub mono">
                hop {nd.hop_distance} · {inrShort(nd.attributed_value)}
              </div>
            </td>
            <td><Band band={nd.band} score={nd.mri} /></td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
