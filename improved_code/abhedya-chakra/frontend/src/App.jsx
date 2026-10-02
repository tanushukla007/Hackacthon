import { Navigate, Route, Routes } from 'react-router-dom'
import { ThemeProvider } from './theme'
import AppShell from './components/layout/AppShell'
import ErrorBoundary from './components/common/ErrorBoundary'
import { useDataset } from './hooks/useDataset'
import DashboardPage from './pages/DashboardPage'
import InvestigationPage from './pages/InvestigationPage'
import AccountPage from './pages/AccountPage'
import AccountsPage from './pages/AccountsPage'
import CasesPage from './pages/CasesPage'
import SystemPage from './pages/SystemPage'

export default function App() {
  const dataset = useDataset()
  return (
    <ThemeProvider>
    <AppShell dataset={dataset}>
      <ErrorBoundary>
      <Routes>
        <Route path="/" element={<DashboardPage dataset={dataset} />} />
        <Route path="/investigate" element={<InvestigationPage dataset={dataset} />} />
        <Route path="/investigate/:victim" element={<InvestigationPage dataset={dataset} />} />
        <Route path="/accounts" element={<AccountsPage dataset={dataset} />} />
        <Route path="/accounts/:id" element={<AccountPage dataset={dataset} />} />
        <Route path="/cases" element={<CasesPage dataset={dataset} />} />
        <Route path="/system" element={<SystemPage dataset={dataset} />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      </ErrorBoundary>
    </AppShell>
    </ThemeProvider>
  )
}
