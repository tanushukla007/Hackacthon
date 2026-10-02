import { useEffect, useState } from 'react'
import { getIngestStatus, getDatasetSummary } from '../services/datasetService'

/**
 * Dataset readiness. Polls the ingest status so a new load can be detected even
 * after the previous dataset reached READY, and shows real backend stages.
 */
export function useDataset() {
  const [status, setStatus] = useState(null)
  const [summary, setSummary] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    let alive = true
    let timer
    const tick = async () => {
      try {
        const { data } = await getIngestStatus()
        if (!alive) return
        setStatus(data); setError(null)
        if (data.state === 'READY' && !summary) {
          const s = await getDatasetSummary()
          if (alive) setSummary(s.data)
        }
        timer = setTimeout(tick, data.state === 'LOADING' ? 900 : 2500)
      } catch (e) {
        if (!alive) return
        setError(e); timer = setTimeout(tick, 2500)
      }
    }
    tick()
    return () => { alive = false; clearTimeout(timer) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return { status, summary, error, ready: status?.state === 'READY' }
}
