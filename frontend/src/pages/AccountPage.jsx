import { useNavigate, useParams } from 'react-router-dom'
import { useApi } from '../hooks/useApi'
import { getAccount, getAccountTransactions, getCounterparties } from '../services/accountService'
import { Band, ErrorState, Loading, Panel, RowId, Section } from '../components/common/Primitives'
import RiskBreakdown from '../components/account/RiskBreakdown'
import DualSided from '../components/account/DualSided'
import { accountReportUrl } from '../services/documentService'
import { inr, inrShort, n, ts } from '../utils/format'

export default function AccountPage() {
  const { id } = useParams()
  const nav = useNavigate()
  const acc = useApi(() => getAccount(id), [id])
  const cps = useApi(() => getCounterparties(id, 12), [id])
  const txns = useApi(() => getAccountTransactions(id, { limit: 50 }), [id])

  if (acc.error) return <div className="page"><ErrorState error={acc.error} onRetry={acc.reload} /></div>
  if (acc.loading || !acc.data) return <div className="page"><Loading label={`Loading ${id}`} /></div>
  const a = acc.data

  return (
    <div className="page">
      <div className="page-head">
        <span className="idx">03</span>
        <h1 className="mono" style={{ fontFamily: 'var(--font-mono)', fontSize: 19 }}>{a.account_id}</h1>
        <Band band={a.risk.band} score={a.risk.mri} />
        <span className="role">{a.role.role}</span>
        <div className="sub">
          <button className="btn primary" onClick={() => nav(`/investigate/${a.account_id}`)}>
            Trace from this account
          </button>
          <a className="btn ghost" href={accountReportUrl(a.account_id)}
             target="_blank" rel="noreferrer"
             title="Server-generated PDF: observed behaviour, index components and the rows behind them">
            Export PDF
          </a>
        </div>
      </div>

      <div className="grid g-2-1">
        <div>
          <Section title="Both sides of the ledger">
            <Panel><DualSided account={a} /></Panel>
          </Section>
          <Section title="Counterparties">
            <div className="grid g2">
              <Panel pad={false}>
                <table className="ledger">
                  <thead><tr><th>Top senders</th><th className="n">Txns</th><th className="n">Value</th></tr></thead>
                  <tbody>{(cps.data?.inbound || []).map((c) => (
                    <tr key={c.account_id} className="clickable" onClick={() => nav(`/accounts/${c.account_id}`)}>
                      <td className="id">{c.account_id}</td><td className="n">{c.transactions}</td>
                      <td className="n">{inrShort(c.amount)}</td></tr>))}</tbody>
                </table>
              </Panel>
              <Panel pad={false}>
                <table className="ledger">
                  <thead><tr><th>Top receivers</th><th className="n">Txns</th><th className="n">Value</th></tr></thead>
                  <tbody>{(cps.data?.outbound || []).map((c) => (
                    <tr key={c.account_id} className="clickable" onClick={() => nav(`/accounts/${c.account_id}`)}>
                      <td className="id">{c.account_id}</td><td className="n">{c.transactions}</td>
                      <td className="n">{inrShort(c.amount)}</td></tr>))}</tbody>
                </table>
              </Panel>
            </div>
          </Section>
          <Section title="Source rows" count={txns.data ? `${txns.data.transactions.length} of ${n(txns.data.total)}` : ''}>
            <Panel pad={false}>
              <table className="ledger">
                <thead><tr><th>Timestamp</th><th>From</th><th>To</th><th className="n">Amount</th>
                  <th>Mode</th><th>Narration</th><th>Device</th><th>Provenance</th></tr></thead>
                <tbody>
                  {(txns.data?.transactions || []).map((t) => (
                    <tr key={t.source_row_id}>
                      <td className="mono" style={{ fontSize: 11 }}>{t.timestamp.slice(0, 16)}</td>
                      <td className="id" style={{ fontSize: 11 }}>{t.sender_account}</td>
                      <td className="id" style={{ fontSize: 11 }}>{t.receiver_account}</td>
                      <td className="n">{inr(t.amount)}</td>
                      <td className="mono" style={{ fontSize: 11 }}>{t.payment_mode}</td>
                      <td className="mono" style={{ fontSize: 11 }}>{t.narration}</td>
                      <td className="mono" style={{ fontSize: 11 }}>{t.device_type}</td>
                      <td>
                        <RowId id={t.source_row_id} />
                        {t.duplicate_transaction_id && <span className="tiny" title="This Transaction_ID appears on more than one row"> dup-id</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Panel>
          </Section>
        </div>
        <div>
          <Section title="Assessment"><Panel><RiskBreakdown risk={a.risk} /></Panel></Section>
          <Section title="Role reasoning">
            <Panel>
              <div className="role" style={{ fontSize: 12 }}>{a.role.role}</div>
              <ul style={{ margin: '7px 0 0 15px', padding: 0, fontSize: 11.5, color: 'var(--text-2)' }}>
                {a.role.reasons.map((r, i) => <li key={i} style={{ marginBottom: 4 }}>{r}</li>)}
              </ul>
              <div className="tiny" style={{ marginTop: 8 }}>{a.role.note}</div>
              <div className="note" style={{ marginTop: 8 }}>{a.layer_note}</div>
            </Panel>
          </Section>
          <Section title="Context">
            <Panel>
              <div className="tiny">Payment modes</div>
              {Object.entries(a.context.payment_modes).map(([k, v]) => (
                <div className="fieldrow" key={k}><span className="k">{k}</span><span className="v">{n(v)}</span></div>))}
              <div className="tiny" style={{ marginTop: 9 }}>Devices (as sender)</div>
              {Object.entries(a.context.devices).map(([k, v]) => (
                <div className="fieldrow" key={k}><span className="k">{k}</span><span className="v">{n(v)}</span></div>))}
              <div className="tiny" style={{ marginTop: 9 }}>Observed</div>
              <div className="fieldrow"><span className="k">First seen</span><span className="v">{ts(a.identity.first_seen_ts)}</span></div>
              <div className="fieldrow"><span className="k">Last seen</span><span className="v">{ts(a.identity.last_seen_ts)}</span></div>
              <div className="fieldrow"><span className="k">Active days</span><span className="v">{a.identity.active_days}</span></div>
            </Panel>
          </Section>
        </div>
      </div>
    </div>
  )
}
