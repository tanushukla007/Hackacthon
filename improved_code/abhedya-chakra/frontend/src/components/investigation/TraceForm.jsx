import { useState } from 'react'

export default function TraceForm({ onRun, running, defaults }) {
  const [victim, setVictim] = useState(defaults?.victim || '')
  const [amount, setAmount] = useState('')
  const [hops, setHops] = useState(4)

  const submit = (e) => {
    e.preventDefault()
    onRun({
      victim_account: victim.trim(),
      amount: amount ? Number(amount) : undefined,
      max_hops: Number(hops),
    })
  }
  return (
    <form onSubmit={submit}>
      <label className="lbl" htmlFor="victim">Victim account (12 digits)</label>
      <input id="victim" className="inp" value={victim} inputMode="numeric"
             placeholder="551100220033" onChange={(e) => setVictim(e.target.value)} />
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 70px', gap: 8, marginTop: 9 }}>
        <div>
          <label className="lbl" htmlFor="amt">Reported amount (optional)</label>
          <input id="amt" className="inp" value={amount} inputMode="decimal"
                 placeholder="largest debit" onChange={(e) => setAmount(e.target.value)} />
        </div>
        <div>
          <label className="lbl" htmlFor="hops">Hops</label>
          <select id="hops" className="inp" value={hops} onChange={(e) => setHops(e.target.value)}>
            {[1, 2, 3, 4, 5, 6].map((h) => <option key={h} value={h}>{h}</option>)}
          </select>
        </div>
      </div>
      <button className="btn primary" type="submit" disabled={running || victim.trim().length !== 12}
              style={{ width: '100%', marginTop: 11 }}>
        {running ? 'Tracing…' : 'Trace the money'}
      </button>
      <div className="tiny" style={{ marginTop: 8, lineHeight: 1.6 }}>
        Without a reported amount the backend seeds the trace with the victim's largest
        single outgoing transfer and follows value forward in time.
      </div>
    </form>
  )
}
