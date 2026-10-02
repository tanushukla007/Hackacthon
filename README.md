# ⬢ ABHEDYA-CHAKRA

**A local-first cyber-financial investigation and digital-forensics platform.**
Type a victim's account number → get the money trail, the mule hierarchy, the risk scores, the graph, and a printable Section 94 BNSS freeze notice. In under two seconds. Entirely offline.

> Built for **Void Hacks() 8.0** · Track *Abhedya — Cyber Security & Digital Forensics* · in association with the **Indore Police Commissionerate**.

---

## The problem

A victim loses ₹2,50,000 to a digital-arrest scam. The bank sends the investigating officer a CSV with **two million rows**. The money has already been layered through a collector account, split across five distributors, and cashed out through eleven terminal accounts — in forty-five minutes.

Spreadsheets die at this scale. Four-way SQL self-joins are too slow to investigate interactively. And the freeze notice that could save the money has to be drafted by hand, correctly, right now.

## What this does

```text
      Victim account ID
              │   ≤ 2 seconds, offline
              ▼
   ┌──────────────────────────────────────────────────────────────┐
   │  4-hop money trail · value-attributed, temporally ordered     │
   │  L1 collectors → L2 distributors → L3 terminal cash-out       │
   │  Mule Risk Index 0–100 per account, with reasons              │
   │  Interactive graph · 15-day timeline · subgraph export        │
   │  Case diary + per-bank S.94 BNSS freeze requisition (PDF)     │
   └──────────────────────────────────────────────────────────────┘
```

---

## Quick start

```bash
make setup                               # python venv + node deps
make ingest FILE=data/raw/transactions.csv   # 2M rows, ~40 s, one time
make run                                 # API :8000 + UI :5173
```

Open <http://localhost:5173>, type a victim account ID, press Enter.

Requires Python 3.11+, Node 18+, 16 GB RAM. **No internet connection is needed at any point.**

---

## Benchmarks

Measured with `make bench` on `<hardware>`, dataset = 2,000,000 rows / ≈24,873 accounts / 15 days (2026-09-15 → 2026-09-29).

**Blank means unmeasured. No number appears here until `make bench` produces it.**

_Measured on a **2-core / ~2 GB sandbox** against `STANDIN_2M.csv`, a locally generated synthetic stand-in at competition scale. The real 2M competition CSV has not been seen by this system. Full detail and regime notes: `docs/PERFORMANCE.md`._

| Benchmark | Target | Actual | Status |
|---|---|---|:--:|
| Ingest 2,080,000 rows | ≤ 60 s | **17.6 s** | PASS |
| Peak RSS during ingest | ≤ 6 GB | **1.22 GB** | PASS |
| 4-hop trace (p95) | ≤ 2 s | **755 ms** | PASS |
| Account search (p95) | ≤ 1 s | **1.43 ms** | PASS |
| Graph render, 500 nodes / 1,500 edges | interactive | `__ fps` | `__` |
| Case diary generation | ≤ 10 s | `__ s` | `__` |
| Detection F1 *(state the evaluation regime)* | ≥ 0.85 | `__` | `__` |

*(Fill these in from the real run before submission — `make bench` writes `docs/benchmarks.json`.)*

---

## How it works

```text
 2M CSV ─▶ Polars/DuckDB ingest ─┬─▶ FACT STORE    (DuckDB)   = evidence
                                 ├─▶ GRAPH STORE   (NumPy CSR)= traversal
                                 └─▶ FEATURE STORE (25k × 40) = detection
                                              │
                   ┌──────────────────────────┴──────────────────┐
                   ▼                                             ▼
        value-attributed 4-hop trace                   Mule Risk Index 0–100
                   │                                             │
                   └──────────────┬──────────────────────────────┘
                                  ▼
                        validated Evidence Object
                                  ▼
                 case diary  +  S.94 BNSS freeze requisition
```

**The key sizing insight:** the dataset has ~25,000 accounts and 2,000,000 transactions. The *graph* is tiny; the *log* is big. So we keep a big immutable columnar fact table for evidence and a small integer-encoded CSR adjacency in RAM for traversal. Four-hop traversal becomes array arithmetic, not SQL joins.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full engineering account.

## Anti-hallucination

The LLM **never** produces a fact. Facts come from the database via a typed, provenance-carrying `EvidenceObject`; the model writes only two narrative paragraphs and is forbidden to emit digits. An output validator then re-checks every account number, amount, IFSC, transaction ID and timestamp in the generated document against the evidence, and falls back to a pure template on any violation.

Every document carries: `✔ 47/47 facts verified against source dataset · 0 unverified entities · sha256:7f3a…`

Run `make test-hallucination` to see the validator reject a deliberately lying model stub.

---

## Documentation

| Document | Contents |
|---|---|
| [`ABHEDYA_CHAKRA_PRD.md`](ABHEDYA_CHAKRA_PRD.md) | Full product requirements — 31 sections, every requirement traced to the problem statement |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Module boundaries, CSR internals, memory budget, algorithms, ADRs |
| [`docs/EVALUATION.md`](docs/EVALUATION.md) | Detection metrics, threshold calibration, synthetic ground truth, benchmark methodology |
| [`docs/DEMO.md`](docs/DEMO.md) | Five-minute demo script, pre-flight checklist, failure recovery, judge Q&A |

## Repository layout

```text
backend/abhedya/   ingest/ graph/ detect/ evidence/ docs/ api/ bench/
frontend/src/      components/ hooks/ api/
data/artifacts/    abhedya.duckdb · graph.npz · features.parquet · manifest.json
tests/             unit · golden-file · performance smoke
docs/              PRD · architecture · evaluation · demo · slides
```

All thresholds live in exactly one file: `backend/abhedya/config.py`.

## Make targets

| Target | Does |
|---|---|
| `make setup` | Create venv, install Python + Node dependencies |
| `make ingest FILE=…` | Ingest a CSV, build artifacts, print the timing table |
| `make run` | Start API + UI |
| `make bench` | Ingest + trace + render benchmarks → `docs/benchmarks.json` |
| `make profile` | Profile the CSV before anything else → `data/artifacts/profile.json` |
| `make profile-check` | Assert the profile against PRD §7.2; non-zero exit on mismatch |
| `make eval` | Precision / recall / F1 / confusion matrix → `docs/EVALUATION.md` |
| `make test` | Unit + golden-file + performance smoke tests |
| `make demo` | Pre-warm state, open the console on the demo account |

## Scope

**In:** ingestion, detection, risk scoring, tracing, visualisation, timeline, subgraph export, document generation — all local.
**Out:** banking-system integration, real account freezing, live ingestion, police-database integration, automated legal filing. The output is a **draft for an Investigating Officer to verify and sign**, not a legal instrument.

## Team

| Member | Owns |
|---|---|
| M1 — Technical Lead | Architecture, ingestion, graph engine, traversal, performance, API |
| M2 — Frontend | Dashboard, graph canvas, timeline, inspector, evidence basket |
| M3 — Detection / Data | Features, rule cards, thresholds, MRI calibration, evaluation |
| M4 — Forensics / Docs / QA | Evidence Object, validator, templates, PDF/DOCX, QA, demo |

## Legal note

Documents generated by this tool cite **Section 94 of the Bharatiya Nagarik Suraksha Sanhita, 2023** (corresponding to the erstwhile Section 91 CrPC, 1973), read with Section 106 BNSS. They are **computer-generated drafts** produced from the supplied dataset and must be verified and signed by the Investigating Officer before service. This is a hackathon prototype operating on synthetic data.

---

<p align="center"><b>अभेद्य चक्र</b> — <i>the wheel that cannot be broken.</i><br/>
Every rupee leaves a trace. Our job is to make it readable in two seconds.</p>
