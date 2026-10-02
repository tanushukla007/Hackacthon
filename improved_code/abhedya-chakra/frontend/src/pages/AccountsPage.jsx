import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useApi } from '../hooks/useApi'
import { getTopAccounts } from '../services/datasetService'
import { searchAccounts } from '../services/accountService'
import { Band, ErrorState, Loading, Panel, Section } from '../components/common/Primitives'
import { inrShort } from '../utils/format'

export default function AccountsPage({ dataset }) {
  const nav = useNavigate()
  const [q, setQ] = useState('')
  const [hits, setHits] = useState(null)
  const top = useApi(() => getTopAccounts(60), [dataset.ready], { enabled: dataset.ready })

  const search = async (e) => {
    e.preventDefault()
    if (q.trim().length < 2) return
    try { const { data } = await searchAccounts(q.trim()); setHits(data) } catch { setHits(null) }
  }

  return (
    <div className="page">
      <div className="page-head">
        <span className="idx">03</span><h1>Accounts</h1>
        <div className="sub">Search is an exact substring match over the account identifiers
          present in this dataset. Nothing is fuzzy-matched or guessed.</div>
      </div>
      <Section title="Find an account">
        <Panel>
          <form onSubmit={search} style={{ display: 'flex', gap: 8, maxWidth: 520 }}>
            <input className="inp" value={q} onChange={(e) => setQ(e.target.value)}
                   placeholder="digits of the account number" aria-label="Account search" />
            <button className="btn primary">Search</button>
          </form>
          {hits && (
            <div style={{ marginTop: 10 }}>
              <div className="tiny">{hits.count} match(es)</div>
              {hits.matches.map((m) => (
                <div key={m} className="fieldrow">
                  <span className="k mono">{m}</span>
                  <span className="v"><button className="linky" onClick={() => nav(`/accounts/${m}`)}>open</button></span>
                </div>
              ))}
              {!hits.count && <div className="tiny">No account in this dataset contains that string.</div>}
            </div>
          )}
        </Panel>
      </Section>

      <Section title="Ranked by assessed behavioural risk" count={top.data?.accounts.length}>
        {top.loading && <Loading />}
        {top.error && <ErrorState error={top.error} onRetry={top.reload} />}
        {top.data && (
          <Panel pad={false}>
            <table className="ledger">
              <thead><tr><th>#</th><th>Account</th><th>Assessment</th><th>Role</th>
                <th className="n">In</th><th className="n">Out</th><th className="n">Received</th>
                <th>Reason (from backend)</th></tr></thead>
              <tbody>
                {top.data.accounts.map((a, i) => (
                  <tr key={a.account_id} className="clickable" onClick={() => nav(`/accounts/${a.account_id}`)}>
                    <td className="dim num">{i + 1}</td>
                    <td className="id">{a.account_id}</td>
                    <td><Band band={a.band} score={a.mri} /></td>
                    <td><span className="role">{a.role}</span></td>
                    <td className="n">{a.in_degree}</td><td className="n">{a.out_degree}</td>
                    <td className="n">{inrShort(a.total_in)}</td>
                    <td className="dim" style={{ fontSize: 11 }}>{a.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Panel>
        )}
      </Section>
    </div>
  )
}
