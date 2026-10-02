import { useCallback, useEffect, useRef, useState } from 'react'

/** Generic request hook: {data, error, loading, reload}. Never caches silently. */
export function useApi(fn, deps = [], { enabled = true, pollMs = 0 } = {}) {
  const [state, setState] = useState({ data: null, error: null, loading: enabled })
  const mounted = useRef(true)
  const run = useCallback(async () => {
    if (!enabled) return
    setState((s) => ({ ...s, loading: true }))
    try {
      const { data } = await fn()
      if (mounted.current) setState({ data, error: null, loading: false })
    } catch (e) {
      if (mounted.current) setState({ data: null, error: e, loading: false })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, enabled])

  useEffect(() => { mounted.current = true; run(); return () => { mounted.current = false } }, [run])
  useEffect(() => {
    if (!pollMs || !enabled) return
    const t = setInterval(run, pollMs)
    return () => clearInterval(t)
  }, [pollMs, run, enabled])
  return { ...state, reload: run }
}
