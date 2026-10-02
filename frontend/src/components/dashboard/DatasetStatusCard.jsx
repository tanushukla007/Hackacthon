import { Field, Panel, Section } from '../common/Primitives'
import { inr, n, ts } from '../../utils/format'

export default function DatasetStatusCard({ summary, status }) {
  if (!summary) return null
  const a = summary.amount
  const d = summary.duplicates
  return (
    <Section title="Dataset in evidence" count={summary.fingerprint}>
      <div className="grid g3">
        <Panel>
          <Field k="Source file" v={<span className="mono">{summary.source_file}</span>} />
          <Field k="Rows" v={n(summary.rows)} />
          <Field k="Accounts" v={n(summary.accounts)} />
          <Field k="Window" v={`${summary.time_window.days} days`} />
          <Field k="From" v={summary.time_window.start?.slice(0, 16)} />
          <Field k="To" v={summary.time_window.end?.slice(0, 16)} />
          <Field k="Ingest" v={`${summary.ingest_seconds}s`} />
        </Panel>
        <Panel>
          <Field k="Median amount" v={inr(a.median)} title="Every rupee threshold is calibrated against this" />
          <Field k="Mean amount" v={inr(a.mean)} />
          <Field k="Minimum" v={inr(a.min)} />
          <Field k="90th percentile" v={inr(a.p90)} />
          <Field k="99th percentile" v={inr(a.p99)} />
          <Field k="Maximum" v={inr(a.max)} />
          <Field k="Non-positive amounts" v={n(a.non_positive)} />
        </Panel>
        <Panel>
          <Field k="Unique Transaction_IDs" v={n(d.unique_transaction_ids)} />
          <Field k="Duplicated IDs" v={n(d.duplicate_transaction_ids)} />
          <Field k="Rows affected" v={n(d.rows_with_duplicate_id)} />
          <Field k="Row surplus" v={n(d.surplus)} />
          <Field k="Exact duplicate rows" v={n(d.exact_duplicate_rows)} />
          <Field k="Self-loops" v={n(summary.self_loops ?? 0)} />
          <div style={{ marginTop: 8 }} className="note">
            <b>Transaction_ID is not a key.</b> {d.policy} Every claim in this system cites a
            <span className="mono"> source_row_id</span>.
          </div>
        </Panel>
      </div>
    </Section>
  )
}
