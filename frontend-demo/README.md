# ABHEDYA-CHAKRA — demo UI

A deliberately plain React interface over the same FastAPI backend. It exists to
show the pipeline working end to end: load a CSV, look at what was loaded, trace
a victim account, inspect one account. The full investigator workstation
(`../frontend`) is the one intended for the final build.

## What is different from the main frontend

| | demo UI (`frontend-demo`, port 5174) | workstation UI (`frontend`, port 5173) |
|---|---|---|
| Look | plain, system fonts, light **and** dark | forensic ledger, dark only |
| Ingestion | explicit **Data** tab: pick the CSV, press Ingest, watch real stage timings | automatic at boot |
| Graph | plain SVG, hop columns, pan/zoom, full screen, SVG export, no dependency | Cytoscape + dagre, layer-as-shape, timeline playback |
| Cases / documents | full: case file, diary, evidence, document generation, bank hook | case diary, evidence basket, freeze requisition |
| Dependencies | react, react-dom, vite | + cytoscape, cytoscape-dagre, react-router |

## Run

```bash
# from the project root
ABHEDYA_NO_AUTOLOAD=1 bash run.sh api    # backend, no boot-time ingest
bash run.sh demo                         # http://localhost:5174
```

Setting `ABHEDYA_NO_AUTOLOAD=1` leaves the backend in the `EMPTY` state so the
Data tab actually does the loading. Without it the backend ingests the first CSV
in `data/raw` at boot and the demo opens straight on Overview.

The app checks `/api/system/status` before it renders anything. With no dataset
loaded it lands on **Data** and the other four tabs stay disabled, because a
screen full of dashes is a worse answer than one that says what is missing.

## Rules this UI follows

The same ones the main frontend follows, because they are properties of the
system and not of the skin:

- The browser never reads the CSV, DuckDB or Parquet. Every value arrives over
  `/api`.
- The UI computes no risk score, no layer, no money flow, no suspicion.
- Progress is the backend's real stage list with real milliseconds. No synthetic
  percentage bar is drawn, because the backend does not report one.
- A band is always shown as a word, never as colour alone.
- Layers are labelled as per-trace and relative to one victim.
- Rows are identified by `source_row_id`; duplicate transaction ids are flagged,
  never removed.
- Scores are prioritisation aids. The disclaimer the backend returns is rendered
  verbatim.

## Structure

```
src/
  api.js            every network call, one named function each
  format.js         display formatting only
  styles.css        light/dark variable blocks, flat surfaces
  components/ui.jsx Card, Stat, Band, KV, ErrorBox, Loading, Empty
  pages/
    IngestPage.jsx       data ingestion, stage timings, loaded-dataset facts
    OverviewPage.jsx     dataset summary, risk bands, modes/devices, top accounts
    InvestigatePage.jsx  trace form, accounts/transactions/layers/evidence tabs
    AccountPage.jsx      both sides of the ledger, MRI components, source rows
    CasesPage.jsx        case file: diary, details, documents, evidence, bank
  components/
    TraceGraph.jsx       dependency-free SVG graph with its own toolbar
test/
  fixtures/trace.json    a real trace response, committed so tests need no backend
  graph.render.test.jsx  SSR markup assertions (react-dom/server)
  app.dom.test.jsx       real DOM via jsdom against a stubbed backend
run_tests.sh             runs both suites
```

## Tests

```bash
bash run_tests.sh        # 31 checks: 16 SSR + 15 DOM
```

Playwright cannot run in this sandbox, so the UI is verified two ways instead:
the graph is rendered with `react-dom/server` and asserted on its markup, and
the whole app is mounted in jsdom against a stubbed backend to check the
behaviour that actually matters — ingestion gates the app, a loaded dataset
unlocks it, documents expose a backend PDF link, and the bank panel never
claims a freeze it did not send.

## The case tab

Everything an officer does to a case goes through the backend and comes back
cited:

- **diary** — append-only entries; a trace run files its own entry with
  `refs.trace_ids`, nothing is editable after the fact
- **details** — officer, station, FIR and complainant fields the letters need
- **documents** — case diary, freeze requisition, covering letter, victim
  acknowledgement; each generated server-side with a reference number, the
  dataset fingerprint and the list of `source_row_id`s it cites. The account
  picker is prefilled from the last trace's HIGH/CRITICAL accounts and passes
  the `trace_id`, so the requisition quotes **traced credit from this victim**
  rather than every rupee the account ever received
- **bank** — shows `DISCONNECTED` unless `ABHEDYA_BANK_URL` is configured.
  Pressing send with no endpoint returns `409 BANK_NOT_CONNECTED` and says so.
  There is no demo mode that pretends an account was frozen

Theme choice is stored in `localStorage` under `abhedya-demo-theme` and defaults
to the operating system preference.
