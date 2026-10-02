/**
 * API service layer for the demo UI.
 *
 * Every network call lives here as a named function. Components never call
 * fetch directly. The backend is the only source of truth: this file reads
 * values, it never computes risk, layers or money flow.
 */

const BASE = '/api'

async function request(path, options = {}) {
  const res = await fetch(BASE + path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })

  let body
  try {
    body = await res.json()
  } catch {
    throw Object.assign(new Error(`Server returned ${res.status} with a non-JSON body.`), {
      code: 'BAD_RESPONSE',
      status: res.status,
    })
  }

  if (!res.ok || body.success === false) {
    const err = body.error || {}
    throw Object.assign(new Error(err.message || `Request failed (${res.status}).`), {
      code: err.code || 'UNKNOWN_ERROR',
      status: res.status,
      detail: err.detail || null,
      hint: err.hint || null,
    })
  }

  // Envelope: { success, data, meta }
  return { data: body.data, meta: body.meta || {} }
}

/* ------------------------------------------------------------------ system */
export const getSystemStatus = () => request('/system/status')
export const getHealth = () => request('/system/health')

/* ------------------------------------------------------------------ ingest */
export const getIngestStatus = () => request('/ingest/status')
export const startIngest = (filename) =>
  request('/ingest', { method: 'POST', body: JSON.stringify(filename ? { filename } : {}) })
export const getProfile = () => request('/ingest/profile')

/* ----------------------------------------------------------------- dataset */
export const getDatasetSummary = () => request('/dataset/summary')
export const getRiskDistribution = () => request('/accounts/risk-distribution')
export const getTopAccounts = (limit = 25) => request(`/accounts/top?limit=${limit}`)

/* ---------------------------------------------------------------- accounts */
export const searchAccounts = (q) => request(`/accounts/search?q=${encodeURIComponent(q)}`)
export const getAccount = (id) => request(`/accounts/${encodeURIComponent(id)}`)
export const getAccountTransactions = (id, limit = 25) =>
  request(`/accounts/${encodeURIComponent(id)}/transactions?limit=${limit}`)
export const getAccountCounterparties = (id) =>
  request(`/accounts/${encodeURIComponent(id)}/counterparties`)

/* ------------------------------------------------------------------- trace */
export const runTrace = (victimAccount, options = {}) =>
  request('/trace', {
    method: 'POST',
    body: JSON.stringify({ victim_account: victimAccount, ...options }),
  })
export const getTrace = (traceId) => request(`/trace/${traceId}`)

/* ------------------------------------------------------------------- cases */
export const listCases = () => request('/cases')
export const createCase = (body) =>
  request('/cases', { method: 'POST', body: JSON.stringify(body) })
export const getCase = (id) => request(`/cases/${id}`)
export const updateCaseDetails = (id, body) =>
  request(`/cases/${id}/details`, { method: 'POST', body: JSON.stringify(body) })
export const addDiaryEntry = (id, body) =>
  request(`/cases/${id}/diary`, { method: 'POST', body: JSON.stringify(body) })
export const addCaseEvidence = (id, items) =>
  request(`/cases/${id}/evidence`, { method: 'POST', body: JSON.stringify({ items }) })

/* --------------------------------------------------------------- documents */
export const listDocuments = (caseId) => request(`/cases/${caseId}/documents`)

/** slug: freeze-requisition | covering-letter | victim-acknowledgement */
export const generateDocument = (caseId, slug, body = {}) =>
  request(`/cases/${caseId}/documents/${slug}`, { method: 'POST', body: JSON.stringify(body) })

/* PDF endpoints are plain URLs so the browser can download or print them
   directly - no blob juggling, and the file keeps its filename. */
export const documentPdfUrl = (caseId, documentId) =>
  `${BASE}/cases/${caseId}/documents/${documentId}?format=pdf`
export const documentHtmlUrl = (caseId, documentId) =>
  `${BASE}/cases/${caseId}/documents/${documentId}?format=html`
export const traceReportUrl = (traceId, caseId) =>
  `${BASE}/reports/trace/${traceId}?format=pdf` + (caseId ? `&case_id=${caseId}` : '')
export const accountReportUrl = (accountId, caseId) =>
  `${BASE}/reports/account/${accountId}?format=pdf` + (caseId ? `&case_id=${caseId}` : '')

/* ------------------------------------------------------------ bank gateway */
export const getBankStatus = () => request('/bank/status')
export const getBankHistory = () => request('/bank/history')
export const sendFreezeToBank = (caseId, documentId) =>
  request('/bank/freeze', {
    method: 'POST',
    body: JSON.stringify({ case_id: caseId, document_id: documentId }),
  })

/* -------------------------------------------------------------- provenance */
export const getRow = (sourceRowId) => request(`/rows/${sourceRowId}`)
export const getTransaction = (txnId) => request(`/transactions/${encodeURIComponent(txnId)}`)
