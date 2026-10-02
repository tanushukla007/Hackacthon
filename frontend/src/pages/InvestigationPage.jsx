import { Suspense, lazy, useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import TraceForm from '../components/investigation/TraceForm'
import TraceSummary from '../components/investigation/TraceSummary'
import NodeLedger from '../components/investigation/NodeLedger'
import NodeInspector from '../components/investigation/NodeInspector'
const NetworkGraph = lazy(() => import('../components/graph/NetworkGraph'))
import TimelineScrubber from '../components/timeline/TimelineScrubber'
import EvidenceDocket from '../components/evidence/EvidenceDocket'
import { EmptyState, ErrorState } from '../components/common/Primitives'
import { getTimeline, runTrace } from '../services/traceService'
import { addEvidence, createCase, listCases } from '../services/caseService'
import { traceReportUrl } from '../services/documentService'

export default function InvestigationPage({ dataset }) {
  const { victim } = useParams()
  const nav = useNavigate()
  const [trace, setTrace] = useState(null)
  const [timeline, setTimeline] = useState(null)
  const [cursor, setCursor] = useState(null)
  const [selected, setSelected] = useState(null)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState(null)
  const [basket, setBasket] = useState([])
  const [flash, setFlash] = useState(null)

  const run = useCallback(async (payload) => {
    setRunning(true); setError(null); setSelected(null); setCursor(null); setTimeline(null)
    try {
      const { data } = await runTrace(payload)
      setTrace(data)
      const tl = await getTimeline(data.trace_id)
      setTimeline(tl.data)
    } catch (e) { setError(e); setTrace(null) } finally { setRunning(false) }
  }, [])

  useEffect(() => { if (victim && !trace) run({ victim_account: victim, max_hops: 4 }) },
    [victim]) // eslint-disable-line react-hooks/exhaustive-deps

  const selectedNode = useMemo(
    () => trace?.nodes.find((n) => n.account_id === selected) || null, [trace, selected])

  const addToBasket = (account) => {
    const node = trace?.nodes.find((n) => n.account_id === account.account_id)
    const fromTrace = (trace?.evidence || []).filter((e) => e.account_id === account.account_id)
    const items = fromTrace.length ? fromTrace : [{
      evidence_id: `local_${account.account_id}_${Date.now()}`,
      claim: `${account.account_id} is assessed at MRI ${account.risk.mri} (${account.risk.band}): ${account.risk.reason}`,
      claim_type: 'ASSESSED',
      account_id: account.account_id,
      source_row_ids: [],
      source_row_count: 0,
      dataset_fingerprint: dataset.summary?.fingerprint,
    }]
    setBasket((b) => [...b, ...items.filter((i) => !b.some((x) => x.evidence_id === i.evidence_id))])
  }

  const commit = async () => {
    try {
      const { data: list } = await listCases()
      let caseId = list.cases.find((c) => c.victim_account === trace.victim_account)?.case_id
      if (!caseId) {
        const { data: c } = await createCase({
          title: `Money trail from ${trace.victim_account}`,
          victim_account: trace.victim_account,
          officer: 'Investigating Officer',
        })
        caseId = c.case_id
      }
      await addEvidence(caseId, basket)
      setFlash(`${basket.length} item(s) attached to ${caseId}`)
      setBasket([])
      setTimeout(() => setFlash(null), 4000)
    } catch (e) { setError(e) }
  }

  return (
    <div className="work">
      <div className="col">
        <div className="colhead"><h3>Trace</h3><span className="rule" /></div>
        <div className="colbody">
          <TraceForm onRun={run} running={running} defaults={{ victim }} />
        </div>
        {trace && (
          <>
            <div className="colhead"><h3>Result</h3><span className="rule" />
              <a className="btn ghost sm" href={traceReportUrl(trace.trace_id)}
                 target="_blank" rel="noreferrer"
                 title="Server-generated PDF: every account reached and every transaction traced, each citing its source_row_id">
                Export PDF
              </a>
            </div>
            <div className="colbody"><TraceSummary trace={trace} /></div>
            <div className="colhead"><h3>Accounts reached</h3><span className="rule" />
              <span className="mono dim" style={{ fontSize: 11 }}>{trace.node_count}</span></div>
            <NodeLedger trace={trace} selected={selected} onSelect={setSelected} />
          </>
        )}
      </div>

      <div className="col centre">
        {error && <ErrorState error={error} />}
        {!trace && !error && (
          <EmptyState title="No trace yet"
            hint="Enter a victim account on the left. The backend walks the money forward in time from that account." />
        )}
        {trace && (
          <>
            <Suspense fallback={<div className="state dim">Loading graph engine…</div>}>
              <NetworkGraph trace={trace} selected={selected} onSelect={setSelected}
                            timeCursor={cursor} />
            </Suspense>
            <TimelineScrubber timeline={timeline} cursor={cursor} onCursor={setCursor} />
            <EvidenceDocket items={basket} onCommit={commit}
                            onRemove={(id) => setBasket((b) => b.filter((x) => x.evidence_id !== id))} />
          </>
        )}
        {flash && <div className="note" style={{ margin: 10 }}>{flash}</div>}
      </div>

      <div className="col">
        <div className="colhead"><h3>Inspector</h3><span className="rule" />
          {selected && <button className="btn ghost" onClick={() => nav(`/accounts/${selected}`)}>Open</button>}
        </div>
        <NodeInspector accountId={selected} traceNode={selectedNode}
                       onAddEvidence={addToBasket}
                       onTraceFrom={(a) => run({ victim_account: a, max_hops: 4 })} />
      </div>
    </div>
  )
}
