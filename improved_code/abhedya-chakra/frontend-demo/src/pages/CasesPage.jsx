import { useEffect, useState } from 'react'
import * as api from '../api'
import { Card, ErrorBox, Empty, Loading, Band } from '../components/ui'
import { inrExact, num } from '../format'

const DETAIL_FIELDS = [
  ['officer_rank', 'Rank / designation'],
  ['officer_contact', 'Officer contact'],
  ['police_station', 'Police station'],
  ['district', 'District / state'],
  ['fir_number', 'FIR number'],
  ['fir_date', 'FIR date'],
  ['complainant_name', 'Complainant name'],
  ['complainant_contact', 'Complainant contact'],
  ['complainant_address', 'Complainant address'],
  ['complaint_date', 'Complaint date'],
  ['response_days', 'Response deadline (days)'],
]

const DIARY_KINDS = ['NOTE', 'ACTION', 'DECISION', 'COMMUNICATION', 'EVIDENCE']

const DOCS = [
  ['freeze-requisition', 'Freeze requisition',
   'Requisition to the bank under S.94 BNSS listing the accounts and traced amounts.'],
  ['covering-letter', 'Covering letter',
   'Forwarding letter to the nodal officer; encloses the requisition.'],
  ['victim-acknowledgement', 'Acknowledgement to complainant',
   'Records the action taken on the complaint and what happens next.'],
]

/** Case file: details, diary, evidence, the three documents, and the bank hook. */
export default function CasesPage({ caseId, onSelectCase, lastTrace, onOpenAccount }) {
  const [list, setList] = useState([])
  const [active, setActive] = useState(null)
  const [docs, setDocs] = useState([])
  const [bank, setBank] = useState(null)
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState('diary')
  const [flash, setFlash] = useState(null)

  const [newCase, setNewCase] = useState({ title: '', victim_account: '', officer: '', reported_amount: '' })
  const [details, setDetails] = useState({})
  const [diary, setDiary] = useState({ kind: 'NOTE', text: '' })
  const [freezeAccounts, setFreezeAccounts] = useState('')

  const refreshList = async () => {
    const { data } = await api.listCases()
    setList(data.cases || [])
    return data.cases || []
  }

  const openCase = async (id) => {
    setErr(null)
    try {
      const [{ data: c }, { data: d }] = await Promise.all([api.getCase(id), api.listDocuments(id)])
      setActive(c)
      setDetails(c.details || {})
      setDocs(d.documents || [])
      onSelectCase?.(id)
      if (!freezeAccounts && lastTrace) {
        const top = (lastTrace.nodes || [])
          .filter((n) => n.band === 'HIGH' || n.band === 'CRITICAL')
          .map((n) => n.account_id)
        if (top.length) setFreezeAccounts(top.join(', '))
      }
    } catch (e) {
      setErr(e)
    }
  }

  useEffect(() => {
    (async () => {
      setLoading(true)
      try {
        const cases = await refreshList()
        const { data: b } = await api.getBankStatus()
        setBank(b)
        if (caseId) await openCase(caseId)
        else if (cases.length) await openCase(cases[0].case_id)
      } catch (e) {
        setErr(e)
      } finally {
        setLoading(false)
      }
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const say = (msg) => {
    setFlash(msg)
    setTimeout(() => setFlash(null), 4000)
  }

  const create = async (ev) => {
    ev.preventDefault()
    setErr(null)
    setBusy(true)
    try {
      const { data } = await api.createCase({
        ...newCase,
        reported_amount: newCase.reported_amount ? Number(newCase.reported_amount) : null,
      })
      setNewCase({ title: '', victim_account: '', officer: '', reported_amount: '' })
      await refreshList()
      await openCase(data.case_id)
      say(`${data.case_id} created.`)
    } catch (e) { setErr(e) } finally { setBusy(false) }
  }

  const saveDetails = async () => {
    setBusy(true)
    setErr(null)
    try {
      const { data } = await api.updateCaseDetails(active.case_id, { details })
      setActive(data)
      say('Case details saved. Letters will use them.')
    } catch (e) { setErr(e) } finally { setBusy(false) }
  }

  const addDiary = async (ev) => {
    ev.preventDefault()
    if (!diary.text.trim()) return
    setBusy(true)
    setErr(null)
    try {
      await api.addDiaryEntry(active.case_id, {
        text: diary.text, kind: diary.kind, officer: active.officer,
      })
      setDiary({ ...diary, text: '' })
      await openCase(active.case_id)
    } catch (e) { setErr(e) } finally { setBusy(false) }
  }

  const generate = async (slug) => {
    setBusy(true)
    setErr(null)
    try {
      const body = {}
      if (slug === 'freeze-requisition') {
        const accounts = freezeAccounts.split(/[\s,]+/).filter(Boolean)
        if (!accounts.length) throw Object.assign(new Error('Enter at least one account number.'),
          { code: 'NO_ACCOUNTS' })
        body.accounts = accounts
        if (lastTrace?.trace_id) body.trace_id = lastTrace.trace_id
      }
      const { data } = await api.generateDocument(active.case_id, slug, body)
      await openCase(active.case_id)
      setTab('documents')
      say(`${data.reference} generated.`)
    } catch (e) { setErr(e) } finally { setBusy(false) }
  }

  const sendToBank = async (documentId) => {
    setBusy(true)
    setErr(null)
    try {
      const { data } = await api.sendFreezeToBank(active.case_id, documentId)
      say(`Transmitted: ${data.outcome}.`)
      await openCase(active.case_id)
    } catch (e) { setErr(e) } finally { setBusy(false) }
  }

  if (loading) return <Loading what="Loading cases" />

  return (
    <>
      <h1>Cases</h1>
      <p className="page-sub">
        A case holds the diary, the evidence collected from traces, and the documents
        generated from it. Everything is written to disk under <code>data/cases/</code>.
      </p>

      {flash && <div className="notice" style={{ marginBottom: 12 }}>{flash}</div>}
      <ErrorBox error={err} />

      <div className="grid" style={{ gridTemplateColumns: '300px minmax(0, 1fr)', gap: 16 }}>
        <div>
          <Card title="Open cases">
            {list.length === 0 ? <Empty>No cases yet.</Empty> : (
              <div className="caselist">
                {list.map((c) => (
                  <div key={c.case_id}
                       className={`caseitem ${active?.case_id === c.case_id ? 'sel' : ''}`}
                       onClick={() => openCase(c.case_id)}>
                    <div className="mono small">{c.case_id}</div>
                    <div style={{ fontWeight: 600 }}>{c.title}</div>
                    <div className="small muted">
                      victim {c.victim_account} · {c.evidence_count} evidence ·{' '}
                      {c.diary_count} diary
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>

          <div style={{ height: 12 }} />

          <Card title="New case">
            <form onSubmit={create}>
              <label className="field">Title</label>
              <input type="text" required value={newCase.title} style={{ width: '100%' }}
                     placeholder="Digital arrest scam — Rs 2,50,000"
                     onChange={(e) => setNewCase({ ...newCase, title: e.target.value })} />
              <div style={{ height: 8 }} />
              <label className="field">Victim account</label>
              <input type="text" required value={newCase.victim_account} style={{ width: '100%' }}
                     placeholder="327091122305"
                     onChange={(e) => setNewCase({ ...newCase, victim_account: e.target.value })} />
              <div style={{ height: 8 }} />
              <label className="field">Investigating officer</label>
              <input type="text" value={newCase.officer} style={{ width: '100%' }}
                     placeholder="Inspector A. Sharma"
                     onChange={(e) => setNewCase({ ...newCase, officer: e.target.value })} />
              <div style={{ height: 8 }} />
              <label className="field">Reported amount</label>
              <input type="number" value={newCase.reported_amount} style={{ width: '100%' }}
                     placeholder="250000"
                     onChange={(e) => setNewCase({ ...newCase, reported_amount: e.target.value })} />
              <div style={{ height: 10 }} />
              <button className="primary" type="submit" disabled={busy}>Create case</button>
            </form>
          </Card>
        </div>

        <div>
          {!active ? (
            <Card><Empty>Select a case, or create one.</Empty></Card>
          ) : (
            <>
              <Card
                title={`${active.case_id} — ${active.title}`}
                right={
                  <div className="tabs">
                    {['diary', 'details', 'documents', 'evidence', 'bank'].map((t) => (
                      <button key={t} className={`tab ${tab === t ? 'active' : ''}`}
                              onClick={() => setTab(t)}>{t}</button>
                    ))}
                  </div>
                }
              >
                <div className="small muted">
                  victim <span className="mono">{active.victim_account}</span> ·{' '}
                  {active.officer} · opened {active.created_at} ·{' '}
                  {active.reported_amount ? inrExact(active.reported_amount) : 'amount not recorded'} ·
                  fingerprint <span className="mono">{active.dataset_fingerprint}</span>
                </div>

                {/* ------------------------------------------------ diary */}
                {tab === 'diary' && (
                  <>
                    <form onSubmit={addDiary} style={{ margin: '14px 0' }}>
                      <div className="row">
                        <div>
                          <label className="field">Entry type</label>
                          <select value={diary.kind}
                                  onChange={(e) => setDiary({ ...diary, kind: e.target.value })}>
                            {DIARY_KINDS.map((k) => <option key={k}>{k}</option>)}
                          </select>
                        </div>
                        <div style={{ flex: 1 }}>
                          <label className="field">What happened</label>
                          <input type="text" value={diary.text} style={{ width: '100%' }}
                                 placeholder="Traced the money trail; two accounts show HIGH behavioural risk."
                                 onChange={(e) => setDiary({ ...diary, text: e.target.value })} />
                        </div>
                        <button className="primary" type="submit" disabled={busy}>Add entry</button>
                      </div>
                    </form>

                    {(active.diary || []).length === 0 ? (
                      <Empty>No diary entries yet.</Empty>
                    ) : (
                      <div className="diary">
                        {[...active.diary].reverse().map((d) => (
                          <div className="entry" key={d.entry_id}>
                            <div className="when">
                              {d.at} · {d.officer} · <span className="tag">{d.kind}</span>
                            </div>
                            <div>{d.text}</div>
                            <div className="small muted mono">{d.entry_id}</div>
                          </div>
                        ))}
                      </div>
                    )}
                    <div className="disclaimer">
                      Entries are append-only: they are never edited or deleted, so the diary
                      stays a faithful record of what was done and when.
                    </div>
                  </>
                )}

                {/* ---------------------------------------------- details */}
                {tab === 'details' && (
                  <>
                    <p className="small muted" style={{ marginTop: 12 }}>
                      These fields are printed on the letterhead and in the body of the
                      generated documents. Blank fields are simply omitted — nothing is
                      invented to fill them.
                    </p>
                    <div className="formgrid">
                      {DETAIL_FIELDS.map(([k, label]) => (
                        <div key={k}>
                          <label className="field" htmlFor={k}>{label}</label>
                          <input id={k} type="text" style={{ width: '100%' }}
                                 value={details[k] ?? ''}
                                 onChange={(e) => setDetails({ ...details, [k]: e.target.value })} />
                        </div>
                      ))}
                    </div>
                    <div style={{ marginTop: 12 }}>
                      <button className="primary" onClick={saveDetails} disabled={busy}>
                        Save details
                      </button>
                    </div>
                  </>
                )}

                {/* -------------------------------------------- documents */}
                {tab === 'documents' && (
                  <>
                    <h3>Generate</h3>
                    <div style={{ marginBottom: 10 }}>
                      <label className="field">
                        Accounts to requisition (comma separated)
                        {lastTrace?.trace_id &&
                          ' — amounts will be limited to what the last trace followed into them'}
                      </label>
                      <input type="text" value={freezeAccounts} style={{ width: '100%' }}
                             placeholder="545470146222, 409802925607"
                             onChange={(e) => setFreezeAccounts(e.target.value)} />
                      {!lastTrace?.trace_id && (
                        <div className="small muted" style={{ marginTop: 4 }}>
                          No trace is loaded, so amounts would be each account's total credits in
                          the window, not funds attributed to this complainant. Run a trace first
                          for a requisition you can defend.
                        </div>
                      )}
                    </div>

                    {DOCS.map(([slug, title, desc]) => (
                      <div className="doccard" key={slug}>
                        <div className="docrow">
                          <div style={{ flex: 1 }}>
                            <strong>{title}</strong>
                            <div className="small muted">{desc}</div>
                          </div>
                          <button onClick={() => generate(slug)} disabled={busy}>Generate</button>
                        </div>
                      </div>
                    ))}

                    <h3>Generated ({docs.length})</h3>
                    {docs.length === 0 ? <Empty>Nothing generated for this case yet.</Empty> : (
                      docs.slice().reverse().map((d) => (
                        <div className="doccard" key={d.document_id}>
                          <div className="docrow">
                            <div style={{ flex: 1 }}>
                              <span className="tag">{d.type}</span>
                              <strong className="mono"> {d.reference}</strong>
                              <div className="small muted">
                                {d.generated_at} · <span className="mono">{d.document_id}</span>
                              </div>
                            </div>
                            <a className="btnlink" target="_blank" rel="noreferrer"
                               href={api.documentHtmlUrl(active.case_id, d.document_id)}>View</a>
                            <a className="btnlink primary" target="_blank" rel="noreferrer"
                               href={api.documentPdfUrl(active.case_id, d.document_id)}>PDF</a>
                            {d.type === 'FREEZE_REQUISITION' && (
                              <button onClick={() => sendToBank(d.document_id)} disabled={busy}
                                      title={bank?.connected
                                        ? 'Transmit to the configured bank endpoint'
                                        : 'No bank endpoint is configured'}>
                                Send to bank
                              </button>
                            )}
                          </div>
                        </div>
                      ))
                    )}
                  </>
                )}

                {/* --------------------------------------------- evidence */}
                {tab === 'evidence' && (
                  (active.basket || []).length === 0 ? (
                    <Empty>
                      No evidence attached. Evidence objects are produced by a trace and carry
                      their source_row_ids and the dataset fingerprint.
                    </Empty>
                  ) : (
                    <div style={{ marginTop: 12 }}>
                      {active.basket.map((b) => (
                        <div className="doccard" key={b.basket_item_id}>
                          <span className="tag">{b.claim_type}</span>
                          <span className="small muted mono"> {b.added_at}</span>
                          <div style={{ marginTop: 4 }}>{b.claim}</div>
                          <div className="small muted mono" style={{ marginTop: 4 }}>
                            {(b.source_row_ids || []).slice(0, 10).map((r) => (
                              <span className="tag" key={r}>row {r}</span>
                            ))}
                          </div>
                        </div>
                      ))}
                    </div>
                  )
                )}

                {/* ------------------------------------------------- bank */}
                {tab === 'bank' && (
                  <>
                    <div className={`notice ${bank?.connected ? '' : 'warn'}`}
                         style={{ marginTop: 12 }}>
                      <strong>{bank?.mode}</strong> — {bank?.note}
                    </div>
                    <div style={{ marginTop: 10 }}>
                      <div className="kv"><span className="k">endpoint</span>
                        <span className="v">{bank?.endpoint || 'none'}</span></div>
                      <div className="kv"><span className="k">bearer token set</span>
                        <span className="v">{bank?.auth ? 'yes' : 'no'}</span></div>
                      <div className="kv"><span className="k">attempts logged</span>
                        <span className="v">{num(bank?.attempts_logged)}</span></div>
                    </div>
                    <h3>How to connect a demo bank</h3>
                    <p className="small muted">
                      Start any HTTP server that accepts{' '}
                      <code>POST /freeze</code>, export{' '}
                      <code>ABHEDYA_BANK_URL=http://localhost:9000</code> and restart the
                      backend. The requisition is posted as JSON with the reference, the legal
                      basis, the dataset fingerprint and the per-account amounts. The bank's
                      reply is recorded verbatim in{' '}
                      <code>data/cases/bank_requests.jsonl</code>.
                    </p>
                    <div className="notice">
                      Until an endpoint is configured, "Send to bank" fails with
                      BANK_NOT_CONNECTED. There is no simulated success path — a freeze that
                      did not happen must never look like one that did.
                    </div>
                  </>
                )}
              </Card>
            </>
          )}
        </div>
      </div>
    </>
  )
}
