import { useState } from 'react'
import { useApi } from '../hooks/useApi'
import { addDiary, addEvidence, createCase, getCase, listCases } from '../services/caseService'
import { ClaimType, EmptyState, ErrorState, Loading, Panel, RowId, Section } from '../components/common/Primitives'
import { DOCUMENT_SLUGS, documentUrl, generateDocument, listDocuments }
  from '../services/documentService'
import { n } from '../utils/format'

export default function CasesPage({ dataset }) {
  const cases = useApi(() => listCases(), [])
  const [open, setOpen] = useState(null)
  const [detail, setDetail] = useState(null)
  const [doc, setDoc] = useState(null)
  const [form, setForm] = useState({ title: '', victim_account: '', officer: 'Investigating Officer' })
  const [note, setNote] = useState('')
  const [basketAccount, setBasketAccount] = useState('')
  const [picked, setPicked] = useState([])
  const [docs, setDocs] = useState([])
  const [pdfAvailable, setPdfAvailable] = useState(true)
  const [busy, setBusy] = useState(null)
  const [err, setErr] = useState(null)

  const load = async (id) => {
    setOpen(id); setDoc(null); setPicked([])
    try {
      const { data } = await getCase(id)
      setDetail(data)
      await loadDocs(id)
    } catch (e) { setErr(e) }
  }

  const loadDocs = async (id) => {
    try {
      const { data } = await listDocuments(id)
      setDocs(data.documents || [])
      setPdfAvailable(data.pdf_available)
    } catch (e) { setErr(e) }
  }

  /* Generation is a server call. The browser does not build documents - it
     asks for one and then links to it. */
  const makeDoc = async (slug) => {
    setBusy(slug); setErr(null)
    try {
      const body = slug === 'freeze-requisition' ? { accounts: picked } : {}
      const { data } = await generateDocument(open, slug, body)
      setDoc(data)
      await loadDocs(open)
      await load2()
    } catch (e) { setErr(e) } finally { setBusy(null) }
  }
  const load2 = async () => {
    try { const { data } = await getCase(open); setDetail(data) } catch { /* shown above */ }
  }
  const make = async (e) => {
    e.preventDefault()
    try { const { data } = await createCase(form); await cases.reload(); load(data.case_id) }
    catch (e2) { setErr(e2) }
  }
  const diary = async () => {
    if (!note.trim()) return
    await addDiary(open, { text: note, officer: detail.officer }); setNote(''); load(open)
  }
  const accountsInBasket = [...new Set((detail?.basket || []).map((b) => b.account_id).filter(Boolean))]
  const addAccountToBasket = async (e) => {
    e.preventDefault()
    const account = basketAccount.trim()
    if (!/^\d{12}$/.test(account)) {
      setErr({ message: 'Account numbers must be exactly 12 digits.' })
      return
    }
    if (accountsInBasket.includes(account)) {
      setErr({ message: `${account} is already in this case basket.` })
      return
    }
    setErr(null)
    try {
      await addEvidence(open, [{
        evidence_id: `manual_${account}_${Date.now()}`,
        claim: `${account} selected for freeze review.`,
        claim_type: 'SELECTED',
        account_id: account,
        source_row_ids: [],
        source_row_count: 0,
        dataset_fingerprint: detail.dataset_fingerprint,
      }])
      setBasketAccount('')
      await load2()
    } catch (e2) { setErr(e2) }
  }

  return (
    <div className="page">
      <div className="page-head">
        <span className="idx">04</span><h1>Cases</h1>
        <div className="sub">Case state is mutable and per-investigation. Dataset facts are
          immutable and shared. Nothing here can alter a measurement.</div>
      </div>
      {err && <ErrorState error={err} />}
      <div className="grid g-1-2">
        <div>
          <Section title="Open a case" count={cases.data?.cases.length}>
            <Panel pad={false}>
              <table className="ledger">
                <thead><tr><th>Case</th><th>Victim</th><th className="n">Evidence</th></tr></thead>
                <tbody>
                  {(cases.data?.cases || []).map((c) => (
                    <tr key={c.case_id} className={`clickable ${open === c.case_id ? 'sel' : ''}`}
                        onClick={() => load(c.case_id)}>
                      <td className="id">{c.case_id}<div className="dim" style={{ fontSize: 11 }}>{c.title}</div></td>
                      <td className="id">{c.victim_account}</td>
                      <td className="n">{c.evidence_count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!cases.data?.cases.length && <div className="colbody tiny">No cases yet.</div>}
            </Panel>
          </Section>
          <Section title="New case">
            <Panel>
              <form onSubmit={make}>
                <label className="lbl">Title</label>
                <input className="inp" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
                <label className="lbl" style={{ marginTop: 8 }}>Victim account</label>
                <input className="inp" value={form.victim_account}
                       onChange={(e) => setForm({ ...form, victim_account: e.target.value })} />
                <label className="lbl" style={{ marginTop: 8 }}>Officer</label>
                <input className="inp" value={form.officer} onChange={(e) => setForm({ ...form, officer: e.target.value })} />
                <button className="btn primary" style={{ width: '100%', marginTop: 10 }}>Create case</button>
              </form>
            </Panel>
          </Section>
        </div>

        <div>
          {!detail && <EmptyState title="No case open" hint="Select a case to see its basket and diary." />}
          {detail && (
            <>
              <Section title={`${detail.case_id} · ${detail.title}`}>
                <Panel>
                  <div className="fieldrow"><span className="k">Victim</span><span className="v mono">{detail.victim_account}</span></div>
                  <div className="fieldrow"><span className="k">Officer</span><span className="v">{detail.officer}</span></div>
                  <div className="fieldrow"><span className="k">Opened</span><span className="v">{detail.created_at}</span></div>
                  <div className="fieldrow"><span className="k">Dataset fingerprint</span><span className="v mono">{detail.dataset_fingerprint}</span></div>
                </Panel>
              </Section>

              <Section title="Evidence basket" count={detail.basket.length}>
                <Panel pad={false}>
                  {!detail.basket.length && <div className="colbody tiny">Empty. Add claims from the investigation page.</div>}
                  {detail.basket.map((b) => (
                    <div className="docket-item" key={b.basket_item_id}>
                      <ClaimType type={b.claim_type} />
                      <div>
                        <div className="claim">{b.claim}</div>
                        <div className="meta">
                          {b.account_id && <span className="mono">{b.account_id}</span>}
                          <span>{b.source_row_count ?? 0} source rows</span>
                          {(b.source_row_ids || []).slice(0, 4).map((r) => <RowId key={r} id={r} />)}
                        </div>
                      </div>
                      <span className="tiny">{b.added_at?.slice(11, 16)}</span>
                    </div>
                  ))}
                </Panel>
              </Section>

              <Section title="Freeze requisition">
                <Panel>
                  <div className="tiny" style={{ marginBottom: 6 }}>
                    Pick the accounts to requisition. Totals are recomputed with exact decimal
                    arithmetic from the cited source rows.
                  </div>
                  <form onSubmit={addAccountToBasket} style={{ display: 'flex', gap: 6, marginBottom: 8 }}>
                    <input className="inp" value={basketAccount}
                           onChange={(e) => setBasketAccount(e.target.value.replace(/\D/g, '').slice(0, 12))}
                           placeholder="12-digit account" aria-label="Account to add to basket" />
                    <button className="btn" type="submit" disabled={!basketAccount}>Add</button>
                  </form>
                  {!accountsInBasket.length && <div className="tiny">No accounts in the basket yet.</div>}
                  {accountsInBasket.map((a) => (
                    <label key={a} style={{ display: 'flex', gap: 8, alignItems: 'center', padding: '3px 0' }}>
                      <input type="checkbox" checked={picked.includes(a)}
                             onChange={(e) => setPicked((p) => e.target.checked ? [...p, a] : p.filter((x) => x !== a))} />
                      <span className="mono">{a}</span>
                    </label>
                  ))}
                  <button className="btn" disabled={!picked.length || busy === 'freeze-requisition'}
                          onClick={() => makeDoc('freeze-requisition')}
                          style={{ marginTop: 8 }}>
                    {busy === 'freeze-requisition' ? 'Generating…' : 'Generate'}
                  </button>
                  {doc && (
                    <div style={{ marginTop: 11 }}>
                      <div className="note">
                        <b>{doc.type}</b> · {doc.document_id}<br />
                        Legal basis: {doc.legal_basis}<br />
                        Seizure: {doc.seizure_basis}
                      </div>
                      {doc.type === 'FREEZE_REQUISITION' && Array.isArray(doc.accounts) ? (
                        <table className="ledger" style={{ marginTop: 8 }}>
                          <thead><tr><th>Account</th><th>Bank</th><th className="n">Credited (exact)</th>
                            <th className="n">Rows cited</th><th className="n">MRI</th></tr></thead>
                          <tbody>
                            {doc.accounts.map((b) => (
                              <tr key={b.account_id}>
                                <td className="id">{b.account_id}</td><td className="mono">{b.bank}</td>
                                <td className="n">₹{b.credited_total}</td>
                                <td className="n">{n(b.transactions_cited)}</td><td className="n">{b.mri}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      ) : (
                        <div className="tiny" style={{ marginTop: 8 }}>
                          Document generated successfully. Open it from the document ledger to
                          view the complete rendered content.
                        </div>
                      )}
                      <div className="tiny" style={{ marginTop: 7 }}>{doc.disclaimer}</div>
                    </div>
                  )}
                </Panel>
              </Section>

              <Section title="Documents" count={docs.length}>
                <Panel>
                  <div className="tiny" style={{ marginBottom: 7 }}>
                    Every document is produced by the backend: numbered, fingerprinted, and
                    printing the <span className="mono">source_row_id</span> of each fact it
                    cites. The browser only links to the result.
                  </div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                    {DOCUMENT_SLUGS.map((d) => (
                      <button key={d.slug} className="btn sm" title={d.note}
                              disabled={busy === d.slug ||
                                (d.slug === 'freeze-requisition' && !picked.length)}
                              onClick={() => makeDoc(d.slug)}>
                        {busy === d.slug ? 'Generating…' : d.label}
                      </button>
                    ))}
                  </div>
                  {!pdfAvailable && (
                    <div className="note warn" style={{ marginTop: 8 }}>
                      The PDF engine is not installed on the server, so documents are offered
                      as HTML. The content is identical.
                    </div>
                  )}
                  {docs.length > 0 ? (
                    <table className="ledger" style={{ marginTop: 9 }}>
                      <thead>
                        <tr><th>Reference</th><th>Type</th><th>Generated</th><th>Open</th></tr>
                      </thead>
                      <tbody>
                        {docs.map((d) => (
                          <tr key={d.document_id}>
                            <td className="id">{d.reference}</td>
                            <td className="tiny">{d.type.replace(/_/g, ' ').toLowerCase()}</td>
                            <td className="mono tiny">{(d.generated_at || '').replace('T', ' ')}</td>
                            <td>
                              {pdfAvailable && (
                                <a className="btn sm" target="_blank" rel="noreferrer"
                                   href={documentUrl(open, d.document_id, 'pdf')}>PDF</a>
                              )}{' '}
                              <a className="btn sm ghost" target="_blank" rel="noreferrer"
                                 href={documentUrl(open, d.document_id, 'html')}>HTML</a>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  ) : (
                    <div className="tiny" style={{ marginTop: 8 }}>
                      Nothing issued on this case yet.
                    </div>
                  )}
                </Panel>
              </Section>

              <Section title="Case diary" count={detail.diary.length}>
                <Panel>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <input className="inp" value={note} onChange={(e) => setNote(e.target.value)}
                           placeholder="What did you do, and why?" />
                    <button className="btn" onClick={diary}>Add</button>
                  </div>
                  <div style={{ marginTop: 9 }}>
                    {detail.diary.map((d) => (
                      <div key={d.entry_id} className="fieldrow">
                        <span className="k">{d.text}</span>
                        <span className="v" style={{ fontSize: 11 }}>{d.at.replace('T', ' ')}</span>
                      </div>
                    ))}
                    {!detail.diary.length && <div className="tiny">No entries yet.</div>}
                  </div>
                </Panel>
              </Section>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
