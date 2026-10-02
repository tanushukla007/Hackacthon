import { Panel, Section } from '../common/Primitives'
import { n, pct } from '../../utils/format'

const Rows = ({ obj, total }) => (
  <table className="ledger">
    <tbody>
      {Object.entries(obj).map(([k, v]) => (
        <tr key={k}>
          <td className="id">{k}</td>
          <td style={{ width: '45%' }}>
            <div className="bar"><span style={{ width: `${(v / total) * 100}%` }} /></div>
          </td>
          <td className="n">{n(v)}</td>
          <td className="n dim">{pct((v / total) * 100, 2)}</td>
        </tr>
      ))}
    </tbody>
  </table>
)

export function ModeAndDevice({ summary }) {
  if (!summary) return null
  const total = summary.rows
  return (
    <div className="grid g2">
      <Section title="Payment modes"><Panel pad={false}><Rows obj={summary.payment_modes} total={total} /></Panel></Section>
      <Section title="Devices"><Panel pad={false}><Rows obj={summary.devices} total={total} /></Panel></Section>
    </div>
  )
}

export function SignalPanel({ summary }) {
  if (!summary) return null
  const total = summary.rows
  const sig = summary.signals
  const co = summary.signal_cooccurrence
  const coRate = co?.cooccurrence_rate ?? 0
  return (
        <Section title="Terminal signals" count={pct(sig.share_of_rows, 4)}>
          <Panel pad={false}>
            <Rows obj={{
              'Foreign-prefix IP': sig.foreign_ip_rows,
              'Automation device': sig.automation_rows,
              'Crypto narration': sig.crypto_rows,
              'Wallet narration': sig.wallet_rows,
              'Cash-out narration': sig.cashout_rows,
            }} total={total} />
          </Panel>
          <Panel style={{ marginTop: -1 }}>
            <div className={`note ${coRate > 0.5 ? 'warn' : ''}`}>
              <b>Measured co-occurrence {coRate.toFixed(2)}.</b>{' '}
              {coRate > 0.5
                ? 'These signals arrive together, so they are one fact, not several. The risk model applies a co-occurrence discount and terminal evidence alone cannot reach CRITICAL.'
                : 'The signals appear largely independent in this file.'}
            </div>
            <div className="tiny" style={{ marginTop: 8 }}>
              Signals mark exit behaviour only. They cannot find collectors or distributors —
              those carry no signals at all.
            </div>
          </Panel>
        </Section>
  )
}
