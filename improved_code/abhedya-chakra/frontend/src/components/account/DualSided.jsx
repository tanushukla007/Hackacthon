import { inrShort, n, dur } from '../../utils/format'

/**
 * Both sides of the ledger, always, for every role (§14).
 * Collectors send. Distributors receive. The UI never hides one direction.
 */
export default function DualSided({ account }) {
  const t = account.topology, v = account.value, tm = account.temporal, f = account.flow
  return (
    <>
      <div className="dual">
        <div>
          <h4>Inbound</h4>
          <div className="fieldrow"><span className="k">Distinct senders</span>
            <span className="v">{n(t.in_degree)} <small>p{t.in_degree_percentile}</small></span></div>
          <div className="fieldrow"><span className="k">Transactions</span><span className="v">{n(t.in_txn_count)}</span></div>
          <div className="fieldrow"><span className="k">Total received</span><span className="v">{inrShort(v.total_in)}</span></div>
          <div className="fieldrow"><span className="k">Peak / hour</span><span className="v">{n(tm.peak_in_count_3600)}</span></div>
          <div className="fieldrow"><span className="k">Collection window</span><span className="v">{dur(tm.collection_window_seconds)}</span></div>
        </div>
        <div>
          <h4>Outbound</h4>
          <div className="fieldrow"><span className="k">Distinct receivers</span>
            <span className="v">{n(t.out_degree)} <small>p{t.out_degree_percentile}</small></span></div>
          <div className="fieldrow"><span className="k">Transactions</span><span className="v">{n(t.out_txn_count)}</span></div>
          <div className="fieldrow"><span className="k">Total sent</span><span className="v">{inrShort(v.total_out)}</span></div>
          <div className="fieldrow"><span className="k">Peak / hour</span><span className="v">{n(tm.peak_out_count_3600)}</span></div>
          <div className="fieldrow"><span className="k">Median hold</span>
            <span className="v">{tm.median_hold_seconds === null ? 'not measurable' : dur(tm.median_hold_seconds)}</span></div>
        </div>
      </div>
      <div className="fieldrow" style={{ marginTop: 8 }}>
        <span className="k">Forward ratio</span><span className="v">{f.forward_ratio.toFixed(3)}</span>
      </div>
      <div className="fieldrow">
        <span className="k">Net flow residual</span><span className="v">{inrShort(v.net_balance)}</span>
      </div>
      <div className="tiny" style={{ marginTop: 4 }}>{v.net_balance_note}</div>
    </>
  )
}
