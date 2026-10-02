import { useState } from 'react'
import * as api from '../api'
import { Card, Band, ErrorBox, Empty } from '../components/ui'
import TraceGraph from '../components/TraceGraph'
import { num, inr, dt, ms } from '../format'

/**
 * Trace money out of a victim account.
 *
 * The backend decides hops, layers, which edges are worth following and when
 * to stop. This page submits the request and renders what comes back. There
 * is no graph canvas in the demo UI - the full workstation has that.
 */
export default function InvestigatePage({ onOpenAccount, caseId, initialVictim, onTrace }) {
  const [victim, setVictim] = useState(initialVictim || '')
  const [maxHops, setMaxHops] = useState(4)
  const [trace, setTrace] = useState(null)
  const [meta, setMeta] = useState(null)
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)
  const [tab, setTab] = useState('graph')
  const [picked, setPicked] = useState(null)

  const submit = async (e) => {
    e.preventDefault()
    setErr(null)
    setBusy(true)
    setTrace(null)
    try {
      const { data, meta } = await api.runTrace(victim.trim(), { max_hops: Number(maxHops) })
      setTrace(data)
      setMeta(meta)
      setPicked(null)
      onTrace?.(data)
    } catch (e2) {
      setErr(e2)
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <h1>Investigate</h1>
      <p className="page-sub">
        Enter the victim account. The backend traces value forward and returns every
        account and transaction it reached.
      </p>

      <Card>
        <form className="row" onSubmit={submit}>
          <div style={{ flex: '1 1 240px' }}>
            <label className="field" htmlFor="victim">Victim account (12 digits)</label>
            <input
              id="victim"
              type="text"
              inputMode="numeric"
              placeholder="327091122305"
              value={victim}
              onChange={(e) => setVictim(e.target.value)}
              style={{ width: '100%' }}
            />
          </div>
          <div>
            <label className="field" htmlFor="hops">Max hops</label>
            <input
              id="hops"
              type="number"
              min="1"
              max="6"
              value={maxHops}
              onChange={(e) => setMaxHops(e.target.value)}
              style={{ width: 90 }}
            />
          </div>
          <button className="primary" type="submit" disabled={busy || victim.trim().length === 0}>
            {busy ? 'Tracing…' : 'Trace'}
          </button>
        </form>
        {busy && (
          <div className="notice" style={{ marginTop: 12 }}>
            Waiting for the backend. The trace runs server-side over the encoded graph;
            no elapsed estimate is shown because none is reported.
          </div>
        )}
      </Card>

      <div style={{ height: 16 }} />
      <ErrorBox error={err} />

      {trace && (
        <>
          <div className="notice" style={{ marginBottom: 16 }}>
            {trace.summary?.statement}
          </div>

          {trace.truncated && (
            <div className="notice warn" style={{ marginBottom: 16 }}>
              This trace was truncated — reason <strong>{trace.truncation_reason}</strong>. Caps:{' '}
              {trace.caps?.max_nodes} nodes / {trace.caps?.max_edges} edges. What you see below is
              a complete answer up to that limit, not the whole network.
            </div>
          )}

          <div className="grid four">
            <div className="card stat">
              <div className="label">Accounts reached</div>
              <div className="value">{num(trace.summary?.accounts_reached)}</div>
            </div>
            <div className="card stat">
              <div className="label">Transactions traced</div>
              <div className="value">{num(trace.summary?.transactions_traced)}</div>
            </div>
            <div className="card stat">
              <div className="label">Value traced</div>
              <div className="value">{inr(trace.summary?.value_traced)}</div>
              <div className="sub">seed {inr(trace.seed_amount)} · {trace.seed_basis}</div>
            </div>
            <div className="card stat">
              <div className="label">Export</div>
              <div style={{ marginTop: 6 }}>
                <a className="btnlink primary" target="_blank" rel="noreferrer"
                   href={api.traceReportUrl(trace.trace_id, caseId)}>PDF report</a>
              </div>
              <div className="sub">server-generated, cites every row</div>
            </div>
            <div className="card stat">
              <div className="label">Backend time</div>
              <div className="value">{ms(trace.processing_ms ?? meta?.processing_ms)}</div>
              <div className="sub">{trace.trace_id}</div>
            </div>
          </div>

          <div style={{ height: 16 }} />

          <Card
            title="Result"
            right={
              <div className="tabs">
                {['graph', 'accounts', 'transactions', 'layers', 'evidence'].map((t) => (
                  <button key={t} className={`tab ${tab === t ? 'active' : ''}`} onClick={() => setTab(t)}>
                    {t}
                  </button>
                ))}
              </div>
            }
          >
            {tab === 'graph' && (
              <div className="grid" style={{ gridTemplateColumns: 'minmax(0, 1fr) 280px', gap: 14 }}>
                <TraceGraph trace={trace} selected={picked} onSelect={setPicked}
                            exportUrl={api.traceReportUrl(trace.trace_id, caseId)}
                            onOpenAccount={onOpenAccount} />
                <div>
                  {!picked ? (
                    <div className="notice">
                      Click any account in the graph to see what the backend measured about it.
                      Columns are hops from the victim; nothing about a node's position is an
                      analytical claim.
                    </div>
                  ) : (
                    (() => {
                      const n = trace.nodes.find((x) => x.account_id === picked)
                      if (!n) return null
                      return (
                        <div className="card">
                          <div className="mono" style={{ fontSize: 15 }}>{n.account_id}</div>
                          <div style={{ margin: '8px 0' }}>
                            <Band band={n.band} score={n.mri} />{' '}
                            <span className="tag">{n.layer}</span>
                            <span className="tag">hop {n.hop_distance}</span>
                            {n.is_hub && <span className="tag">hub</span>}
                          </div>
                          <div className="small muted">{n.layer_reason}</div>
                          <div style={{ marginTop: 10 }}>
                            <div className="kv"><span className="k">role</span><span className="v">{n.role}</span></div>
                            <div className="kv"><span className="k">in / out degree</span><span className="v">{n.in_degree} / {n.out_degree}</span></div>
                            <div className="kv"><span className="k">value traced here</span><span className="v">{inr(n.attributed_value)}</span></div>
                            <div className="kv"><span className="k">total received</span><span className="v">{inr(n.total_in)}</span></div>
                            <div className="kv"><span className="k">total sent</span><span className="v">{inr(n.total_out)}</span></div>
                            <div className="kv"><span className="k">signal families</span><span className="v">{n.signal_families}</span></div>
                          </div>
                          <ul className="small muted" style={{ margin: '8px 0 0 16px', padding: 0 }}>
                            {(n.role_reasons || []).map((r, i) => <li key={i}>{r}</li>)}
                          </ul>
                          <div className="row" style={{ marginTop: 10 }}>
                            <button onClick={() => onOpenAccount(n.account_id)}>Open account</button>
                          </div>
                        </div>
                      )
                    })()
                  )}
                </div>
              </div>
            )}

            {tab === 'accounts' && (
              <div className="scroll">
                <table>
                  <thead>
                    <tr>
                      <th className="num">Hop</th>
                      <th>Layer</th>
                      <th>Account</th>
                      <th>Assessment</th>
                      <th>Role</th>
                      <th className="num">Value traced</th>
                      <th>Why this layer (from backend)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {trace.nodes.map((n) => (
                      <tr key={n.account_id} className="clickable" onClick={() => onOpenAccount(n.account_id)}>
                        <td className="num mono">{n.hop_distance}</td>
                        <td className="mono">{n.layer}</td>
                        <td className="mono">
                          {n.account_id}
                          {n.is_hub && <span className="tag" style={{ marginLeft: 6 }}>hub</span>}
                        </td>
                        <td><Band band={n.band} score={n.mri} /></td>
                        <td className="small">{n.role}</td>
                        <td className="num mono">{inr(n.attributed_value)}</td>
                        <td className="small muted">{n.layer_reason}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {tab === 'transactions' && (
              <div className="scroll">
                <table>
                  <thead>
                    <tr>
                      <th className="num">Hop</th>
                      <th>From</th>
                      <th>To</th>
                      <th className="num">Amount</th>
                      <th>Timestamp</th>
                      <th className="num">source_row_id</th>
                    </tr>
                  </thead>
                  <tbody>
                    {trace.edges.map((e) => (
                      <tr key={e.edge_id}>
                        <td className="num mono">{e.hop}</td>
                        <td className="mono">{e.from}</td>
                        <td className="mono">{e.to}</td>
                        <td className="num mono">{inr(e.amount)}</td>
                        <td className="mono small">{dt(e.ts_epoch)}</td>
                        <td className="num mono">{e.source_row_id}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <div className="disclaimer">
                  Every traced transaction carries its source_row_id, so any row here can be
                  found again in the original CSV.
                </div>
              </div>
            )}

            {tab === 'layers' && (
              <>
                <table>
                  <thead>
                    <tr><th>Layer</th><th className="num">Accounts</th><th>Meaning</th></tr>
                  </thead>
                  <tbody>
                    {Object.entries(trace.summary?.layers || {}).map(([l, c]) => (
                      <tr key={l}>
                        <td className="mono">{l}</td>
                        <td className="num mono">{num(c)}</td>
                        <td className="small muted">
                          {l === 'VICTIM' && 'the account money left from'}
                          {l === 'L1' && 'first receiving layer'}
                          {l === 'L2' && 'second layer'}
                          {l === 'L3' && 'third layer / exit side'}
                          {l.startsWith('H') && `hop ${l.slice(1)}, no distinctive flow shape measured`}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <div className="disclaimer">
                  Layers are assigned for this trace only, relative to this victim. They are
                  not stored on the account and will differ in another investigation.
                </div>
              </>
            )}

            {tab === 'evidence' && (
              <>
                {(trace.evidence || []).length === 0 ? (
                  <Empty>No evidence objects were produced for this trace.</Empty>
                ) : (
                  trace.evidence.map((ev) => (
                    <div className="card" key={ev.evidence_id} style={{ marginBottom: 10 }}>
                      <span className="tag">{ev.claim_type}</span>
                      <span className="mono small muted">{ev.evidence_id}</span>
                      <div style={{ marginTop: 6 }}>{ev.claim}</div>
                      <div className="small muted mono" style={{ marginTop: 6 }}>
                        {(ev.source_row_ids || []).slice(0, 8).map((r) => (
                          <span className="tag" key={r}>row {r}</span>
                        ))}
                        {(ev.source_row_ids || []).length > 8 && `+${ev.source_row_ids.length - 8} more`}
                      </div>
                    </div>
                  ))
                )}
              </>
            )}
          </Card>

          <div className="disclaimer">
            Dataset fingerprint {trace.dataset_fingerprint}. Observations and assessments
            only — nothing here is a finding of fact about any person.
          </div>
        </>
      )}
    </>
  )
}
