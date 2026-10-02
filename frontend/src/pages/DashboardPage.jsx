import { useApi } from '../hooks/useApi'
import { getRiskDistribution, getTopAccounts } from '../services/datasetService'
import DatasetStatusCard from '../components/dashboard/DatasetStatusCard'
import { ModeAndDevice, SignalPanel } from '../components/dashboard/DistributionPanel'
import RiskLedger, { ScoreDistribution } from '../components/dashboard/RiskLedger'
import IngestProgress from '../components/dashboard/IngestProgress'
import { ErrorState, Loading } from '../components/common/Primitives'

export default function DashboardPage({ dataset }) {
  const ready = dataset.ready
  const top = useApi(() => getTopAccounts(20), [ready], { enabled: ready })
  const dist = useApi(() => getRiskDistribution(), [ready], { enabled: ready })

  return (
    <div className="page">
      <div className="page-head">
        <span className="idx">01</span>
        <h1>Dataset standing</h1>
        <div className="sub">
          Everything below is measured by the backend from the loaded file. Figures are
          observations, not findings.
        </div>
      </div>

      {!ready && <IngestProgress status={dataset.status} />}
      {dataset.error && <ErrorState error={dataset.error} />}

      {ready && (
        <>
          <DatasetStatusCard summary={dataset.summary} status={dataset.status} />
          <div className="grid g-2-1">
            <div>
              <ModeAndDevice summary={dataset.summary} />
              {dist.data && <ScoreDistribution distribution={dist.data} />}
            </div>
            <SignalPanel summary={dataset.summary} />
          </div>
          {top.loading && <Loading label="Ranking accounts" />}
          {top.error && <ErrorState error={top.error} onRetry={top.reload} />}
          {top.data && <RiskLedger top={top.data} />}
        </>
      )}
    </div>
  )
}
