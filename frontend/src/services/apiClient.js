/**
 * The ONLY place in the frontend that performs HTTP.
 * No component calls fetch directly (FRONTEND_UI.md §26).
 * Every call unwraps the backend envelope and records backend-reported timing.
 */
const listeners = new Set()
export const onApiEvent = (fn) => { listeners.add(fn); return () => listeners.delete(fn) }
const emit = (e) => listeners.forEach((fn) => fn(e))

export class ApiError extends Error {
  constructor(code, message, detail, hint, status) {
    super(message); this.code = code; this.detail = detail; this.hint = hint; this.status = status
  }
}

async function request(path, { method = 'GET', body, signal } = {}) {
  const t0 = performance.now()
  let res, json
  try {
    res = await fetch(`/api${path}`, {
      method,
      headers: body ? { 'content-type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
      signal,
    })
  } catch (e) {
    if (e.name === 'AbortError') throw e
    emit({ path, ok: false, code: 'NETWORK' })
    throw new ApiError('NETWORK', 'The backend is unreachable. Is the API running on :8000?',
      null, 'Start it with: uvicorn app.main:app --port 8000', 0)
  }
  const wall = performance.now() - t0
  try { json = await res.json() } catch {
    throw new ApiError('INTERNAL_ERROR', 'The backend returned a non-JSON response.', null, null, res.status)
  }
  emit({
    path, ok: json.success, status: res.status,
    wallMs: Math.round(wall),
    processingMs: json?.meta?.processing_ms,
    requestId: json?.meta?.request_id,
    fingerprint: json?.meta?.dataset_fingerprint,
    warnings: json?.meta?.warnings,
    code: json?.error?.code,
  })
  if (!json.success) {
    throw new ApiError(json.error.code, json.error.message, json.error.detail, json.error.hint, res.status)
  }
  return { data: json.data, meta: json.meta }
}

export const api = {
  get: (p, o) => request(p, o),
  post: (p, body, o) => request(p, { ...o, method: 'POST', body }),
}
