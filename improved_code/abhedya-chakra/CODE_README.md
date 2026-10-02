# ABHEDYA-CHAKRA — implementation

Local-first cyber-financial investigation console. FastAPI + Polars + DuckDB +
NumPy CSR on the backend; React + Vite + Cytoscape.js on the frontend.

The three specification documents in `docs/` are binding on this code:
`DATA_CONTEXT.md` (what the data is and what may never be done to it),
`BACKEND_API.md` (payload shapes) and `FRONTEND_UI.md` (presentation).

## Run it

```bash
make install        # pinned backend + frontend dependencies
make sample         # synthetic dev CSV — ONLY if you do not have the real file
make api            # :8000  FastAPI, auto-ingests the first CSV in data/raw
make web            # :5173  Vite dev server, proxies /api to :8000
```

Drop the real dataset in `data/raw/` and restart the API, or POST
`/api/ingest {"filename": "..."}` from the System page.

```bash
make check          # 32 data-contract assertions — must stay at 0 failures
make bench          # writes data/artifacts/bench.json; until then the UI shows null
```

## Layout

```
backend/app/
  config.py              every threshold, weight, keyword and window
  errors.py              closed error-code set + the one response envelope
  main.py                app, middleware, lifespan autoload
  api/routes.py          HTTP surface only, no business logic
  core/ingest.py         CSV -> normalized + derived frame, profile, fingerprint
  core/features.py       per-account feature rows (measurements only)
  core/graph.py          CSR build, hub guard, value-weighted traversal
  core/risk.py           MRI: six components, reasons, caps, disclaimer
  core/investigate.py    victim -> trace -> layers -> evidence
  core/evidence.py       EvidenceObject, forbidden-language validation, Decimal totals
  core/cases.py          mutable case state (JSON on disk)
  core/store.py          the dataset singleton
frontend/src/
  services/              the only place that performs HTTP
  hooks/                 useApi, useDataset
  components/            layout, dashboard, investigation, graph, timeline,
                         account, evidence, common
  pages/                 dashboard, investigation, accounts, account, cases, system
tools/
  make_sample_dataset.py synthetic dev fixture (clearly labelled as such)
  contract_check.py      enforces the data contract
  bench.py               measures real performance, writes bench.json
  profile_dataset.py     standalone dataset profiler
  build_docs.py          PDF/DOCX document build
```

## Rules this code enforces

* Account numbers are strings end to end. Never `int()`.
* `Transaction_ID` is not unique and nothing is keyed on it; `source_row_id` is.
* No row is ever dropped, de-duplicated or quarantined.
* Parallel edges between the same pair are separate edges.
* Outflows may only be FIFO-matched to strictly earlier inflows.
* Every displayed number can name its `source_row_ids`.
* Every response carries the dataset fingerprint.
* Layer is per-investigation; no global layer exists on an account.
* OBSERVED / INFERRED / ASSESSED are separated; "criminal", "guilty" and
  "confirmed mule" are blocked by the evidence validator.
* No accuracy figure exists anywhere: the dataset has no labels.

## Dependencies

Backend pins are in `backend/requirements.txt` (`pip check` clean on Python
3.13). The frontend uses React 18, Vite 5, Cytoscape 3 and `cytoscape-dagre`
only — no React wrapper around Cytoscape, so there are no peer-dependency
conflicts, and no CSS framework, so the visual language is entirely our own.
