import { useState } from 'react'
import { useApi } from '../../hooks/useApi'
import { getAccount, getAccountTransactions } from '../../services/accountService'
import { Band, ClaimType, EmptyState, ErrorState, Loading, RowId } from '../common/Primitives'
import RiskBreakdown from '../account/RiskBreakdown'
import DualSided from '../account/DualSided'
import { inr, ts } from '../../utils/format'

export default function NodeInspector({ accountId, traceNode, onAddEvidence, onTraceFrom }) {
  const [tab, setTab] = useState('risk')
  const acc = useApi(() => getAccount(accountId), [accountId], { enabled: !!accountId })
  const txns = useApi(() => getAccountTransactions(accountId, { limit: 60 }),
    [accountId, tab], { enabled: !!accountId && tab === 'txns' })

  if (!accountId) {
    return <EmptyState title="No account selected"
      hint="Pick a node in the graph or a row in the ledger to inspect it." />
  }
  if (acc.error) return <ErrorState error={acc.error} onRetry={acc.reload} />
  if (acc.loading || !acc.data) return <Loading label="Loading account" />
  const a = acc.data

  return (
    <div>
      <div className="colbody" style={{ paddingBottom: 6 }}>
        <div className="mono" style={{ fontSize: 15 }}>{a.account_id}</div>
        <div style={{ display: 'flex', gap: 7, alignItems: 'center', marginTop: 5, flexWrap: 'wrap' }}>
          <Band band={a.risk.band} score={a.risk.mri} />
          <span className="role">{a.role.role}</span>
          {traceNode && <span className="mono tiny">{traceNode.layer} · hop {traceNode.hop_distance}</span>}
          {a.topology.is_hub && <span className="tiny">HUB</span>}
        </div>
        <div className="tiny" style={{ marginTop: 6 }}>{a.identity.banks_used.join(' · ')}</div>
        {traceNode && (
          <div className="note" style={{ marginTop: 8 }}>
            <b>{traceNode.layer}</b> relative to victim <span className="mono">{traceNode.relative_to_victim}</span>.{' '}
            {traceNode.layer_reason}
          </div>
        )}
        <div style={{ display: 'flex', gap: 6, marginTop: 9 }}>
          <button className="btn" onClick={() => onTraceFrom?.(a.account_id)}>Trace from here</button>
          <button className="btn" onClick={() => onAddEvidence?.(a)}>Add to basket</button>
        </div>
      </div>

      <div className="insp-tabs">
        {[['risk', 'Risk'], ['flow', 'Flow'], ['signals', 'Signals'], ['txns', 'Rows']].map(([k, l]) => (
          <button key={k} className={tab === k ? 'on' : ''} onClick={() => setTab(k)}>{l}</button>
        ))}
      </div>

      <div className="colbody">
        {tab === 'risk' && (
          <>
            <RiskBreakdown risk={a.risk} />
            <div className="tiny" style={{ marginTop: 12 }}>Role reasoning (from the backend)</div>
            <ul style={{ margin: '5px 0 0 15px', padding: 0, fontSize: 11.5, color: 'var(--text-2)' }}>
              {a.role.reasons.map((r, i) => <li key={i} style={{ marginBottom: 3 }}>{r}</li>)}
            </ul>
            <div className="tiny" style={{ marginTop: 8 }}>{a.role.note}</div>
          </>
        )}
        {tab === 'flow' && <DualSided account={a} />}
        {tab === 'signals' && (
          <>
            <div className="fieldrow"><span className="k">Signal families present</span>
              <span className="v">{a.signals.distinct_families} / 3</span></div>
            <div className="fieldrow"><span className="k">Foreign-prefix IP rows</span><span className="v">{a.signals.foreign_ip_txns}</span></div>
            <div className="fieldrow"><span className="k">Automation device rows</span><span className="v">{a.signals.automation_txns}</span></div>
            <div className="fieldrow"><span className="k">Crypto narration</span><span className="v">{a.signals.crypto_txns}</span></div>
            <div className="fieldrow"><span className="k">Wallet narration</span><span className="v">{a.signals.wallet_txns}</span></div>
            <div className="fieldrow"><span className="k">Cash-out narration</span><span className="v">{a.signals.cashout_txns}</span></div>
            {a.signals.distinct_families > 0 ? (
              <>
                <div className="tiny" style={{ marginTop: 10 }}>Possible readings</div>
                <ul style={{ margin: '5px 0 0 15px', padding: 0, fontSize: 11.5, color: 'var(--text-2)' }}>
                  {a.signals.possible_readings.map((r, i) => <li key={i} style={{ marginBottom: 3 }}>{r}</li>)}
                </ul>
                <div className="note stop" style={{ marginTop: 8 }}>
                  <b>Verdict: null.</b> The system does not decide which reading is correct.
                </div>
              </>
            ) : (
              <div className="note" style={{ marginTop: 9 }}>
                No terminal signals. Collectors and distributors normally carry none — their
                evidence is topological, not keyword-based.
              </div>
            )}
          </>
        )}
        {tab === 'txns' && (
          <>
            {txns.loading && <Loading label="Loading rows" />}
            {txns.error && <ErrorState error={txns.error} />}
            {txns.data && (
              <table className="ledger">
                <thead><tr><th>Time</th><th>Counterparty</th><th className="n">Amount</th><th>Row</th></tr></thead>
                <tbody>
                  {txns.data.transactions.map((t) => {
                    const out = t.sender_account === accountId
                    return (
                      <tr key={t.source_row_id}>
                        <td className="mono" style={{ fontSize: 10.5 }}>{t.timestamp.slice(5, 16)}</td>
                        <td className="id" style={{ fontSize: 10.5 }}>
                          <span className="dim">{out ? '→' : '←'}</span>{' '}
                          {out ? t.receiver_account : t.sender_account}
                        </td>
                        <td className="n" style={{ fontSize: 11 }}>{inr(t.amount)}</td>
                        <td><RowId id={t.source_row_id} /></td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            )}
          </>
        )}
      </div>
    </div>
  )
}
