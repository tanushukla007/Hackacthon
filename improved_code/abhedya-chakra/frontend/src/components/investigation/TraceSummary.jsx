import { Field } from '../common/Primitives'
import { inrShort, n, ts } from '../../utils/format'

export default function TraceSummary({ trace }) {
  const s = trace.summary
  return (
    <>
      <Field k="Trace" v={<span className="mono">{trace.trace_id}</span>} />
      <Field k="Seed" v={`${inrShort(trace.seed_amount)}`} title={trace.seed_basis} />
      <Field k="Accounts reached" v={n(s.accounts_reached)} />
      <Field k="Transactions traced" v={n(s.transactions_traced)} />
      <Field k="Value traced" v={inrShort(s.value_traced)} />
      <Field k="High / critical" v={n(s.high_risk_accounts)} />
      <Field k="Terminal accounts" v={n(s.terminal_accounts)} />
      <Field k="Hubs encountered" v={n(s.hubs_encountered)} />
      <Field k="Span" v={`${ts(s.time_span.from)} → ${ts(s.time_span.to)}`} />
      <Field k="Backend time" v={`${trace.processing_ms} ms`} />
      <div className="note" style={{ marginTop: 9 }}>{s.statement}</div>
      <div style={{ marginTop: 9 }}>
        {Object.entries(s.layers).map(([l, c]) => (
          <div className="fieldrow" key={l}>
            <span className="k mono">{l}</span><span className="v">{c}</span>
          </div>
        ))}
      </div>
    </>
  )
}
