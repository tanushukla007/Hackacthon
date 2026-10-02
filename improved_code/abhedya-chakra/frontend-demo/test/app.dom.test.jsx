/**
 * Headless DOM test for the demo UI — no browser required.
 *
 *   npx esbuild test/app.dom.test.jsx --bundle --platform=node --format=cjs \
 *       --jsx=automatic --outfile=/tmp/app.cjs && node /tmp/app.cjs
 *
 * It mounts the real App against a stubbed backend and asserts the behaviour
 * that matters: ingestion gates the application, a loaded dataset unlocks it,
 * and the case documents can be generated and exported.
 */
import { JSDOM } from 'jsdom'
import React from 'react'

const dom = new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>', {
  url: 'http://localhost:5174/',
  pretendToBeVisual: true,
})
global.window = dom.window
global.document = dom.window.document
global.navigator = dom.window.navigator
global.HTMLElement = dom.window.HTMLElement
global.Node = dom.window.Node
global.getComputedStyle = dom.window.getComputedStyle
global.XMLSerializer = dom.window.XMLSerializer
global.Blob = dom.window.Blob
global.localStorage = dom.window.localStorage
global.requestAnimationFrame = (cb) => setTimeout(cb, 0)
global.IS_REACT_ACT_ENVIRONMENT = true
dom.window.matchMedia = () => ({ matches: false, addEventListener() {}, removeEventListener() {} })

const { createRoot } = await import('react-dom/client')
const { act } = await import('react')
const App = (await import('../src/App.jsx')).default

/* ------------------------------------------------------------ fake backend */
let datasetState = 'EMPTY'
const stages = [
  { name: 'fingerprint', ms: 42.5 }, { name: 'normalize', ms: 465.5 },
  { name: 'encode', ms: 30.5 }, { name: 'facts', ms: 202.6 },
]
const CASE = {
  case_id: 'CASE-2026-007', title: 'Test case', victim_account: '327091122305',
  officer: 'Inspector A. Sharma', created_at: '2026-10-01T10:00:00', reported_amount: 250000,
  dataset_fingerprint: 'sha256:deadbeef', details: { police_station: 'Cyber PS' },
  diary: [{ entry_id: 'dry_1', kind: 'ACTION', text: 'Trace run.', officer: 'IO',
            at: '2026-10-01T10:05:00' }],
  basket: [], documents: [],
}
const DOCS = [{ document_id: 'doc_1', type: 'FREEZE_REQUISITION',
                reference: 'CASE-2026-007/FRZ/01', title: 'Requisition',
                generated_at: '2026-10-01T10:10:00', dataset_fingerprint: 'sha256:deadbeef' }]

const envelope = (data) => ({ success: true, data, meta: { request_id: 'req_x', processing_ms: 1 } })

const routes = (path) => {
  if (path.startsWith('/api/system/status')) {
    return envelope({
      dataset: { state: datasetState, rows: 250000, accounts: 6069,
                 fingerprint: 'sha256:deadbeef', source_file: 'SYNTHETIC_DEV_250k.csv' },
      documents: { pdf_available: true, engine: 'weasyprint' },
      bank_gateway: { mode: 'DISCONNECTED', connected: false, note: 'no endpoint',
                      attempts_logged: 0 },
    })
  }
  if (path.startsWith('/api/ingest/status')) {
    return envelope({ state: datasetState, current_stage: null, stages,
                      error: null, source_file: 'SYNTHETIC_DEV_250k.csv',
                      available_files: ['SYNTHETIC_DEV_250k.csv'] })
  }
  if (path.startsWith('/api/dataset/summary')) {
    return envelope({ source_file: 'x.csv', fingerprint: 'sha256:deadbeef', rows: 250000,
                      accounts: 6069, time_window: { from: 1790000000, to: 1790900000 },
                      amount: { min: 50, median: 907, mean: 3365, max: 2026454 },
                      payment_modes: { UPI: 160000 }, devices: { Android: 90000 },
                      duplicates: { unique_transaction_ids: 249725, duplicate_transaction_ids: 275,
                                    rows_with_duplicate_id: 550, surplus: 275,
                                    exact_duplicate_rows: 0, policy: 'every row preserved' },
                      ingest_seconds: 3.0, hub_accounts: 33, hub_threshold_degree: 107 })
  }
  if (path.startsWith('/api/accounts/risk-distribution')) {
    return envelope({ bands: { LOW: 3833, MEDIUM: 2234, HIGH: 2 },
                      histogram: [{ from: 0, to: 5, count: 87 }],
                      roles: { COLLECTOR: 352 } })
  }
  if (path.startsWith('/api/accounts/top')) {
    return envelope({ accounts: [{ account_id: '545470146222', mri: 65.7, band: 'HIGH',
                                   role: 'DISTRIBUTOR', reason: 'because', in_degree: 2,
                                   out_degree: 49, total_in: 11424566 }],
                      disclaimer: 'aid, not a verdict' })
  }
  if (path.startsWith('/api/cases/') && path.endsWith('/documents')) return envelope({ documents: DOCS, pdf_available: true })
  if (path.startsWith('/api/cases/CASE')) return envelope(CASE)
  if (path.startsWith('/api/cases')) return envelope({ cases: [{ ...CASE, evidence_count: 0, diary_count: 1 }] })
  if (path.startsWith('/api/bank/status')) {
    return envelope({ mode: 'DISCONNECTED', connected: false, endpoint: null, auth: false,
                      attempts_logged: 0, note: 'No bank endpoint is configured' })
  }
  return envelope({})
}

global.fetch = async (path, options = {}) => {
  if (path === '/api/ingest' && options.method === 'POST') {
    datasetState = 'READY'
    return { ok: true, status: 202, json: async () => envelope({ accepted: true }) }
  }
  return { ok: true, status: 200, json: async () => routes(String(path)) }
}

/* ----------------------------------------------------------------- harness */
let failures = 0
const check = (name, cond, extra = '') => {
  if (!cond) failures += 1
  console.log(`${cond ? 'PASS' : 'FAIL'}  ${name}${extra ? '  ' + extra : ''}`)
}
const text = () => document.getElementById('root').textContent
const settle = async (ms = 60) => {
  await act(async () => { await new Promise((r) => setTimeout(r, ms)) })
}
const byText = (label) =>
  [...document.querySelectorAll('button, a')].find((b) => b.textContent.trim() === label)

const root = createRoot(document.getElementById('root'))

/* 1. cold start with no dataset -> gated on ingestion */
await act(async () => { root.render(React.createElement(App)) })
await settle(120)

check('startup asks the backend before showing anything', text().length > 0)
check('with no dataset the app lands on ingestion', text().includes('Data ingestion'))
check('the gate is explicit', text().includes('Step 1 of 1'))
const locked = [...document.querySelectorAll('nav .tab')].filter((b) => b.disabled).map((b) => b.textContent)
check('other sections are locked', locked.length === 4, locked.join(','))
check('no fake percentage anywhere', !/\d+\s?%/.test(text()))

/* 2. ingest -> unlocked */
const ingestBtn = byText('Ingest')
check('an ingest control exists', !!ingestBtn)
await act(async () => { ingestBtn.click() })
await settle(1600)
check('after ingest the dataset state is READY', text().includes('READY'))
const stillLocked = [...document.querySelectorAll('nav .tab')].filter((b) => b.disabled)
check('sections unlock once data is loaded', stillLocked.length === 0)

/* 3. navigate to cases, exercise the document surface */
const casesTab = [...document.querySelectorAll('nav .tab')].find((b) => b.textContent === 'Cases')
await act(async () => { casesTab.click() })
await settle(150)
check('case file opens', text().includes('CASE-2026-007'))
check('diary is shown by default', text().includes('Trace run.'))

const docsTab = [...document.querySelectorAll('.tab')].find((b) => b.textContent === 'documents')
await act(async () => { docsTab.click() })
await settle(80)
check('three document types are offered',
      text().includes('Freeze requisition') && text().includes('Covering letter') &&
      text().includes('Acknowledgement to complainant'))
const pdfLink = [...document.querySelectorAll('a')].find((a) => a.textContent === 'PDF')
check('generated documents expose a PDF link', !!pdfLink,
      pdfLink ? pdfLink.getAttribute('href') : 'missing')
check('PDF link points at the backend renderer',
      !!pdfLink && pdfLink.getAttribute('href').includes('format=pdf'))

/* Export links must point at the backend renderer, never at a client-side one. */
const allLinks = [...document.querySelectorAll('a')].map((a) => a.getAttribute('href') || '')
check('document PDF links target the API',
      allLinks.some((h) => /^\/api\/cases\/.+\/documents\/.+format=pdf$/.test(h)))
check('no export is built in the browser',
      !allLinks.some((h) => h.startsWith('blob:') || h.startsWith('data:application/pdf')))

const bankTab = [...document.querySelectorAll('.tab')].find((b) => b.textContent === 'bank')
await act(async () => { bankTab.click() })
await settle(80)
check('bank hook is shown as disconnected, not pretended', text().includes('DISCONNECTED'))
check('no simulated freeze success', !/frozen successfully|freeze complete/i.test(text()))

console.log(failures ? `\n${failures} check(s) failed` : '\nall checks passed')
process.exit(failures ? 1 : 0)
