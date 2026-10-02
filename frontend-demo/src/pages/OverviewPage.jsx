import { useEffect, useState } from 'react'
import * as api from '../api'
import { Card, Stat, Band, ErrorBox, Loading, Empty } from '../components/ui'
import { num, inr, dt, dur } from '../format'

/** Dataset overview: what was loaded, and which accounts the backend ranks highest. */
export default function OverviewPage({ onOpenAccount }) {
  const [summary, setSummary] = useState(null)
  const [dist, setDist] = useState(null)
  const [top, setTop] = useState(null)
  const [err, setErr] = useState(null)
  const [loading, setLoading] = useState(true)

  const load = async () => {
    setLoading(true)
    setErr(null)
    try {
      const [s, d, t] = await Promise.all([
        api.getDatasetSummary(),
        api.getRiskDistribution(),
        api.getTopAccounts(25),
      ])
      setSummary(s.data)
      setDist(d.data)
      setTop(t.data)
    } catch (e) {
      setErr(e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  if (loading) return <Loading what="Loading dataset overview" />
  if (err) return <ErrorBox error={err} onRetry={load} />
  if (!summary) return <Empty>No dataset.</Empty>

  const maxBucket = Math.max(...(dist?.histogram || [{ count: 1 }]).map((b) => b.count))

  return (
    <>
      <h1>Overview</h1>
      <p className="page-sub">
        {summary.source_file} · {summary.fingerprint} · window {dt(summary.time_window?.from)} to{' '}
        {dt(summary.time_window?.to)}
      </p>

      <div className="grid four">
        <Stat label="Rows" value={num(summary.rows)} sub={`ingested in ${dur(summary.ingest_seconds)}`} />
        <Stat label="Accounts" value={num(summary.accounts)} />
        <Stat
          label="Duplicate txn ids"
          value={num(summary.duplicates?.duplicate_transaction_ids)}
          sub={`${num(summary.duplicates?.rows_with_duplicate_id)} rows, all retained`}
        />
        <Stat
          label="Hub accounts"
          value={num(summary.hub_accounts)}
          sub={`degree ≥ ${num(summary.hub_threshold_degree)}`}
        />
      </div>

      <div style={{ height: 16 }} />

      <div className="grid two">
        <Card title="Risk bands">
          {dist && (
            <>
              <div className="grid four" style={{ gap: 8 }}>
                {['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'].map((b) => (
                  <div className="card" key={b} style={{ padding: 10 }}>
                    <Band band={b} />
                    <div style={{ fontSize: 18, fontWeight: 650, marginTop: 6 }}>
                      {num(dist.bands?.[b] || 0)}
                    </div>
                  </div>
                ))}
              </div>
              <h3>MRI distribution</h3>
              {dist.histogram?.map((b) => (
                <div key={b.from} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 3 }}>
                  <span className="mono small muted" style={{ width: 54 }}>
                    {b.from}–{b.to}
                  </span>
                  <span className="bar" style={{ flex: 1 }}>
                    <span style={{ width: `${(b.count / maxBucket) * 100}%` }} />
                  </span>
                  <span className="mono small" style={{ width: 48, textAlign: 'right' }}>{num(b.count)}</span>
                </div>
              ))}
              <h3>Observed roles</h3>
              <div>
                {Object.entries(dist.roles || {}).map(([r, c]) => (
                  <span className="tag" key={r}>{r} {num(c)}</span>
                ))}
              </div>
              <div className="disclaimer">
                Roles describe the shape of flow through an account. Collector and
                Distributor both send and receive; they are descriptors, not capabilities.
              </div>
            </>
          )}
        </Card>

        <Card title="Payment modes and devices">
          <h3>Payment modes</h3>
          {Object.entries(summary.payment_modes || {}).map(([k, v]) => (
            <div key={k} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 3 }}>
              <span className="small" style={{ width: 70 }}>{k}</span>
              <span className="bar" style={{ flex: 1 }}>
                <span style={{ width: `${(v / summary.rows) * 100}%` }} />
              </span>
              <span className="mono small" style={{ width: 86, textAlign: 'right' }}>{num(v)}</span>
            </div>
          ))}
          <h3>Devices</h3>
          {Object.entries(summary.devices || {}).map(([k, v]) => (
            <div key={k} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 3 }}>
              <span className="small" style={{ width: 120 }}>{k}</span>
              <span className="bar" style={{ flex: 1 }}>
                <span style={{ width: `${(v / summary.rows) * 100}%` }} />
              </span>
              <span className="mono small" style={{ width: 86, textAlign: 'right' }}>{num(v)}</span>
            </div>
          ))}
        </Card>
      </div>

      <div style={{ height: 16 }} />

      <Card title="Highest ranked accounts">
        <div className="scroll">
          <table>
            <thead>
              <tr>
                <th>Account</th>
                <th>Assessment</th>
                <th>Role</th>
                <th className="num">In / Out degree</th>
                <th className="num">Received</th>
                <th>Reason (from backend)</th>
              </tr>
            </thead>
            <tbody>
              {top?.accounts?.map((a) => (
                <tr key={a.account_id} className="clickable" onClick={() => onOpenAccount(a.account_id)}>
                  <td className="mono">{a.account_id}</td>
                  <td><Band band={a.band} score={a.mri} /></td>
                  <td className="small">{a.role}</td>
                  <td className="num mono">{a.in_degree} / {a.out_degree}</td>
                  <td className="num mono">{inr(a.total_in)}</td>
                  <td className="small muted">{a.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="disclaimer">{top?.disclaimer}</div>
      </Card>
    </>
  )
}
