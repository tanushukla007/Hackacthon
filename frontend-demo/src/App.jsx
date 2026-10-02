import { useCallback, useEffect, useState } from 'react'
import * as api from './api'
import IngestPage from './pages/IngestPage'
import OverviewPage from './pages/OverviewPage'
import InvestigatePage from './pages/InvestigatePage'
import AccountPage from './pages/AccountPage'
import CasesPage from './pages/CasesPage'

const TABS = [
  { id: 'ingest', label: 'Data' },
  { id: 'overview', label: 'Overview', needsData: true },
  { id: 'investigate', label: 'Investigate', needsData: true },
  { id: 'account', label: 'Account', needsData: true },
  { id: 'cases', label: 'Cases', needsData: true },
]

function useTheme() {
  const [theme, setTheme] = useState(() => {
    const saved = localStorage.getItem('abhedya-demo-theme')
    if (saved === 'light' || saved === 'dark') return saved
    return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  })
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('abhedya-demo-theme', theme)
  }, [theme])
  return [theme, () => setTheme((t) => (t === 'dark' ? 'light' : 'dark'))]
}

export default function App() {
  const [theme, toggleTheme] = useTheme()
  const [tab, setTab] = useState('ingest')
  const [status, setStatus] = useState({ state: 'CHECKING' })
  const [booted, setBooted] = useState(false)
  const [account, setAccount] = useState(null)
  const [caseId, setCaseId] = useState(null)
  const [lastTrace, setLastTrace] = useState(null)

  const refreshStatus = useCallback(async () => {
    try {
      const { data } = await api.getSystemStatus()
      const d = data.dataset || {}
      setStatus({
        state: d.state,
        rows: d.rows,
        accounts: d.accounts,
        fingerprint: d.fingerprint,
        source: d.source_file,
        pdf: data.documents?.pdf_available,
        bank: data.bank_gateway?.mode,
      })
      return d.state
    } catch {
      setStatus({ state: 'UNREACHABLE' })
      return 'UNREACHABLE'
    }
  }, [])

  // Startup: decide where the user lands by asking the backend whether a
  // dataset is loaded. Ingestion is the gate; nothing else runs without data.
  useEffect(() => {
    refreshStatus().then((s) => {
      setTab(s === 'READY' ? 'overview' : 'ingest')
      setBooted(true)
    })
    const iv = setInterval(refreshStatus, 5000)
    return () => clearInterval(iv)
  }, [refreshStatus])

  const ready = status.state === 'READY'
  const openAccount = (id) => { setAccount(id); setTab('account') }
  const traceFrom = (id) => { setAccount(id); setTab('investigate') }

  if (!booted) {
    return (
      <div className="app">
        <main>
          <div className="gate">
            <div className="mark">AC</div>
            <h1><span className="spin" /> Checking the backend</h1>
            <p>Asking the API whether a dataset is already loaded.</p>
          </div>
        </main>
      </div>
    )
  }

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          ABHEDYA-CHAKRA
          <small>demo UI · backend is the source of truth</small>
        </div>

        <nav className="tabs" aria-label="Sections">
          {TABS.map((t) => (
            <button
              key={t.id}
              className={`tab ${tab === t.id ? 'active' : ''}`}
              onClick={() => setTab(t.id)}
              disabled={t.needsData && !ready}
              title={t.needsData && !ready ? 'Load a dataset first' : undefined}
            >
              {t.label}
            </button>
          ))}
        </nav>

        <span className="spacer" />

        {caseId && <span className="tag mono">{caseId}</span>}

        <span className="statepill" title={status.fingerprint || ''}>
          <span className={`dot ${(status.state || '').toLowerCase()}`} />
          {status.state}
          {ready && ` · ${Number(status.rows).toLocaleString('en-IN')} rows`}
        </span>

        <button onClick={toggleTheme} aria-label="Toggle light or dark theme"
                title="Switch between light and dark">
          {theme === 'dark' ? '☀ Light' : '☾ Dark'}
        </button>
      </header>

      <main>
        {status.state === 'UNREACHABLE' && (
          <div className="notice error" style={{ marginBottom: 16 }}>
            Cannot reach the backend on <code>/api</code>. Start it with{' '}
            <code>bash run.sh api</code> and this bar will go green by itself.
          </div>
        )}

        {/* The gate: without a dataset, the only thing the app will do is ingest one. */}
        {!ready && status.state !== 'UNREACHABLE' && tab !== 'ingest' && (
          <div className="notice warn" style={{ marginBottom: 16 }}>
            No dataset is loaded, so there is nothing to show here yet.{' '}
            <button className="link" onClick={() => setTab('ingest')}>Ingest one first.</button>
          </div>
        )}

        {tab === 'ingest' && (
          <IngestPage
            gated={!ready}
            state={status.state}
            onIngested={async () => { await refreshStatus(); setTab('overview') }}
          />
        )}
        {tab === 'overview' && ready && <OverviewPage onOpenAccount={openAccount} />}
        {tab === 'investigate' && ready && (
          <InvestigatePage
            onOpenAccount={openAccount}
            caseId={caseId}
            initialVictim={account}
            onTrace={setLastTrace}
          />
        )}
        {tab === 'account' && ready && (
          <AccountPage accountId={account} onOpenAccount={openAccount} onTrace={traceFrom}
                       caseId={caseId} />
        )}
        {tab === 'cases' && ready && (
          <CasesPage caseId={caseId} onSelectCase={setCaseId} lastTrace={lastTrace}
                     onOpenAccount={openAccount} />
        )}
      </main>

      <footer className="foot">
        Demo interface. All figures are read from the backend API — this UI does not
        compute risk, layers or money flow. A risk score is a prioritisation aid, never a
        finding of guilt.
      </footer>
    </div>
  )
}
