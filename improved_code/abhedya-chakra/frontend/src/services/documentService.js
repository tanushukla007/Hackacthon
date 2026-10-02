import { api } from './apiClient'

/**
 * Documents and reports.
 *
 * Generation, rendering and numbering all happen on the server: the browser
 * never builds a PDF, never formats a legal citation and never decides an
 * amount. These functions either ask the backend to produce a document, or
 * hand the user a URL the backend serves.
 */

/** The four documents this system produces. Slugs are a closed set. */
export const DOCUMENT_SLUGS = [
  { slug: 'case-diary', label: 'Case diary',
    note: 'Every entry, in order, with the references each one carries.' },
  { slug: 'freeze-requisition', label: 'Freeze requisition',
    note: 'Needs the accounts to requisition. Pass the trace to quote traced credit only.' },
  { slug: 'covering-letter', label: 'Covering letter',
    note: 'Forwards the most recent requisition to the bank.' },
  { slug: 'victim-acknowledgement', label: 'Acknowledgement to the complainant',
    note: 'Confirms what was received and what was asked of the bank.' },
]

export const listDocuments = (caseId) => api.get(`/cases/${caseId}/documents`)

export const generateDocument = (caseId, slug, body = {}) =>
  api.post(`/cases/${caseId}/documents/${slug}`, body)

/* URL builders. These are hrefs, not fetches: the browser downloads straight
   from the backend, so a 40-page report never passes through React state. */
export const documentUrl = (caseId, documentId, format = 'pdf') =>
  `/api/cases/${caseId}/documents/${documentId}?format=${format}`

export const traceReportUrl = (traceId, caseId) =>
  `/api/reports/trace/${traceId}?format=pdf${caseId ? `&case_id=${caseId}` : ''}`

export const accountReportUrl = (accountId, caseId) =>
  `/api/reports/account/${accountId}?format=pdf${caseId ? `&case_id=${caseId}` : ''}`

/* Bank transmission. Status is checked before anything is offered, because a
   freeze must never be reported as sent when there is no endpoint. */
export const getBankStatus = () => api.get('/bank/status')
export const sendFreezeToBank = (caseId, documentId) =>
  api.post('/bank/freeze', { case_id: caseId, document_id: documentId })
