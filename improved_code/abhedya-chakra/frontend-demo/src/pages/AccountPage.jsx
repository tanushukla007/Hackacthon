import { useEffect, useState } from 'react'
import * as api from '../api'
import { Card, Band, KV, ErrorBox, Loading, Empty } from '../components/ui'
import { num, inr, inrExact, dt } from '../format'

/** One account: both sides of the ledger, the backend's score, and raw rows. */
export default function AccountPage({ accountId, onOpenAccount, onTrace, caseId }) {
  const [query, setQuery] = useState(accountId || '')
  const [acct, setAcct] = useState(null)
  const [cp, setCp] = useState(null)
  const [txns, setTxns] = useState(null)
  const [err, setErr] = useState(null)
  const [loading, setLoading] = useState(false)

  const load = async (id) => {
    if (!id) return
    setLoading(true)
    setErr(null)
    setAcct(null)
    try {
      const a = await api.getAccount(id)
      setAcct(a.data)
      const [c, t] = await Promise.all([
        api.getAccountCounterparties(id),
        api.getAccountTransactions(id, 25),
      ])
      setCp(c.data)
      setTxns(t.data)
    } catch (e) {
      setErr(e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (accountId) {
      setQuery(accountId)
      load(accountId)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accountId])

  return (
    <>
      <h1>Account</h1>
      <p className="page-sub">Everything the dataset observed about one account, in both directions.</p>

      <Card>
        <form
          className="row"
          onSubmit={(e) => {
            e.preventDefault()
            load(query.trim())
          }}
        >
          <div style={{ flex: '1 1 240px' }}>
            <label className="field" htmlFor="acct">Account number</label>
            <input
              id="acct"
              type="text"
              inputMode="numeric"
              placeholder="545470146222"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              style={{ width: '100%' }}
            />
          </div>
          <button className="primary" type="submit" disabled={loading}>Open</button>
          {acct && <button onClick={() => onTrace(acct.account_id)}>Trace from here</button>}
          {acct && (
            <a className="btnlink" target="_blank" rel="noreferrer"
               href={api.accountReportUrl(acct.account_id, caseId)}
               title="Backend-generated PDF of this account's observed behaviour">
              PDF report
            </a>
          )}
        </form>
      </Card>

      <div style={{ height: 16 }} />
      <ErrorBox error={err} />
      {loading && <Loading what="Loading account" />}

      {acct && (
        <>
          <div className="grid two">
            <Card title="Both sides of the ledger">
              <div className="grid two" style={{ gap: 10 }}>
                <div>
                  <h3 style={{ marginTop: 0 }}>Inbound</h3>
                  <KV k="distinct senders" v={`${num(acct.topology.in_degree)} (p${acct.topology.in_degree_percentile})`} />
                  <KV k="transactions" v={num(acct.topology.in_txn_count)} />
                  <KV k="total received" v={inrExact(acct.value.total_in)} />
                  <KV k="peak / hour" v={num(acct.temporal.peak_in_count_3600)} />
                </div>
                <div>
                  <h3 style={{ marginTop: 0 }}>Outbound</h3>
                  <KV k="distinct receivers" v={`${num(acct.topology.out_degree)} (p${acct.topology.out_degree_percentile})`} />
                  <KV k="transactions" v={num(acct.topology.out_txn_count)} />
                  <KV k="total sent" v={inrExact(acct.value.total_out)} />
                  <KV k="peak / hour" v={num(acct.temporal.peak_out_count_3600)} />
                </div>
              </div>
              <div style={{ marginTop: 10 }}>
                <KV k="forward ratio" v={acct.flow.forward_ratio ?? 'null'} />
                <KV k="split ratio" v={acct.flow.split_ratio ?? 'null'} />
                <KV k="net flow residual" v={inrExact(acct.value.net_balance)} />
                <KV k="hub" v={acct.topology.is_hub ? 'yes' : 'no'} />
                <KV k="banks used" v={(acct.identity.banks_used || []).join(', ')} />
                <KV k="active days" v={num(acct.identity.active_days)} />
              </div>
              <div className="disclaimer">{acct.value.net_balance_note}</div>
            </Card>

            <Card
              title="Assessment"
              right={<Band band={acct.risk.band} score={acct.risk.mri} />}
            >
              {acct.risk.components?.map((c) => (
                <div key={c.key} style={{ marginBottom: 10 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}>
                    <span>{c.label || c.key}</span>
                    <span className="mono">{c.score}/{c.weight}</span>
                  </div>
                  <span className="bar"><span style={{ width: `${(c.score / c.weight) * 100}%` }} /></span>
                  <div className="small muted" style={{ marginTop: 3 }}>{c.reason}</div>
                </div>
              ))}
              <h3>Role</h3>
              <div><span className="tag">{acct.role.role}</span></div>
              <ul className="small muted" style={{ margin: '6px 0 0 16px', padding: 0 }}>
                {(acct.role.reasons || []).map((r, i) => <li key={i}>{r}</li>)}
              </ul>
              <div className="notice" style={{ marginTop: 12 }}>{acct.risk.disclaimer}</div>
              <div className="disclaimer">
                calibration: {acct.risk.calibration_regime} · {acct.layer_note}
              </div>
            </Card>
          </div>

          <div style={{ height: 16 }} />

          <div className="grid two">
            <Card title="Top senders">
              {!cp?.inbound?.length ? <Empty>No inbound counterparties.</Empty> : (
                <table>
                  <thead><tr><th>Account</th><th className="num">Txns</th><th className="num">Value</th></tr></thead>
                  <tbody>
                    {cp.inbound.map((r) => (
                      <tr key={r.account_id} className="clickable" onClick={() => onOpenAccount(r.account_id)}>
                        <td className="mono">{r.account_id}</td>
                        <td className="num mono">{r.transactions}</td>
                        <td className="num mono">{inr(r.amount)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </Card>
            <Card title="Top receivers">
              {!cp?.outbound?.length ? <Empty>No outbound counterparties.</Empty> : (
                <div className="scroll">
                  <table>
                    <thead><tr><th>Account</th><th className="num">Txns</th><th className="num">Value</th></tr></thead>
                    <tbody>
                      {cp.outbound.map((r) => (
                        <tr key={r.account_id} className="clickable" onClick={() => onOpenAccount(r.account_id)}>
                          <td className="mono">{r.account_id}</td>
                          <td className="num mono">{r.transactions}</td>
                          <td className="num mono">{inr(r.amount)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>
          </div>

          <div style={{ height: 16 }} />

          <Card title={`Source rows (${num(txns?.transactions?.length)} of ${num(txns?.total)})`}>
            <div className="scroll">
              <table>
                <thead>
                  <tr>
                    <th>Timestamp</th>
                    <th>From</th>
                    <th>To</th>
                    <th className="num">Amount</th>
                    <th>Mode</th>
                    <th>Narration</th>
                    <th>Device</th>
                    <th className="num">row id</th>
                  </tr>
                </thead>
                <tbody>
                  {txns?.transactions?.map((t) => (
                    <tr key={t.source_row_id}>
                      <td className="mono small">{t.timestamp}</td>
                      <td className="mono small">{t.sender_account}</td>
                      <td className="mono small">{t.receiver_account}</td>
                      <td className="num mono">{inrExact(t.amount)}</td>
                      <td className="small">{t.payment_mode}</td>
                      <td className="small">{t.narration}</td>
                      <td className="small">{t.device_type}</td>
                      <td className="num mono small">
                        {t.source_row_id}
                        {t.duplicate_transaction_id && <span className="tag" style={{ marginLeft: 4 }}>dup id</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="disclaimer">
              Rows are identified by source_row_id, not by Transaction_ID. Duplicate
              transaction ids are kept and flagged, never removed.
            </div>
          </Card>
        </>
      )}

      {!acct && !loading && !err && <Empty>Enter an account number, or click one from another page.</Empty>}
    </>
  )
}
