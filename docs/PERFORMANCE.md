# Abhedya Chakra — Measured Performance

_Generated 2026-10-02 01:21 by `tools/make_performance_doc.py` from benchmark artifacts._

**Every figure below was measured on this machine.** Any row still showing `____` was never measured and is deliberately left blank. No target is reported as if it were a result.

## 1. What the measurements run on

| Property | Value |
|---|---|
| CPU cores available | 2 |
| Total RAM | ~1,984 MB |
| Python | 3.13.14 |
| Platform | Linux x86_64 |

> This is a **2-core, ~2 GB sandbox** — far smaller than the 16 GB target machine the budgets in the PRD assume. Timings here are therefore a **pessimistic** bound: the same code on the stated target hardware has more cores and roughly eight times the memory headroom.

## 2. Datasets measured, and what each one is honestly worth

| Dataset | Rows | Accounts | What it is | What a number from it means |
|---|---:|---:|---|---|
| `SYNTHETIC_DEV_250k.csv` | 250,000 | 6,069 | The synthetic development fixture | Correctness and regression baseline |
| `STANDIN_2M.csv` | 2,080,000 | 25,000 | A **synthetic stand-in** generated locally to match the stated scale of the competition file | **Performance only.** Throughput and memory are real engineering facts; detection quality measured on it would describe the generator, not the world |

**The real 2M competition CSV has not been seen by this system.** No accuracy, precision, recall or F1 figure appears in this document, because no ground-truth label file exists. See `docs/EVALUATION.md`.

## 3. Ingestion

| Dataset | Rows | Wall clock | Budget | Verdict | Throughput |
|---|---:|---:|---:|---|---:|
| `SYNTHETIC_DEV_250k.csv` | 250,000 | 2.47 s | 60 s | **PASS** (24.3x inside budget) | 101,215 rows/s |
| `STANDIN_2M.csv` | 2,080,000 | 17.62 s | 60 s | **PASS** (3.4x inside budget) | 118,048 rows/s |

### 3.1 Stage breakdown — 2,080,000 rows

| Stage | ms | % of ingest | What it does |
|---|---:|---:|---|
| `features` | 8,284.3 | 47.0% | per-account aggregates, temporal passes, percentile ranks |
| `normalize` | 5,044.3 | 28.6% | parse CSV, clean accounts/IFSC, parse timestamps, derive flags, stream to parquet |
| `profile` | 1,762.9 | 10.0% | measure the dataset profile published by /api/ingest/profile |
| `score` | 1,162.7 | 6.6% | score every account with the canonical risk engine |
| `encode` | 560.5 | 3.2% | build the account index and join integer ids onto every row |
| `graph` | 488.5 | 2.8% | extract edge arrays and build the CSR adjacency |
| `fingerprint` | 301.7 | 1.7% | SHA-256 of the source file, 1 MB at a time |
| `facts` | 17.3 | 0.1% | register the DuckDB view over facts.parquet |
| **total** | **17,622.2** | 100% | |

### 3.2 Stage breakdown — 250,000 rows

| Stage | ms | % of ingest | What it does |
|---|---:|---:|---|
| `features` | 1,206.2 | 48.8% | per-account aggregates, temporal passes, percentile ranks |
| `normalize` | 639.8 | 25.9% | parse CSV, clean accounts/IFSC, parse timestamps, derive flags, stream to parquet |
| `profile` | 220.5 | 8.9% | measure the dataset profile published by /api/ingest/profile |
| `score` | 209.9 | 8.5% | score every account with the canonical risk engine |
| `encode` | 85.8 | 3.5% | build the account index and join integer ids onto every row |
| `graph` | 49.1 | 2.0% | extract edge arrays and build the CSR adjacency |
| `fingerprint` | 47.9 | 1.9% | SHA-256 of the source file, 1 MB at a time |
| `facts` | 11.5 | 0.5% | register the DuckDB view over facts.parquet |
| **total** | **2,470.7** | 100% | |

### 3.3 Memory, and why it was the real constraint

Time was never the problem; **memory was**. The original ingest built one fully materialised frame and made roughly twenty-five eager passes over it. Peak RSS grew at about 600 MB per million rows, so the 2M-row file was **OOM-killed (exit 137) after four seconds** on a 2 GB machine — it could not be ingested at all.

| Rows | Peak RSS, eager path | Peak RSS, streaming path |
|---:|---:|---:|
| 250,000 | 403 MB | 362 MB |
| 1,000,000 | 993 MB | 896 MB |
| 2,080,000 | **OOM, killed** | **1,217 MB** |

The fix was structural, not a tuning knob:

1. `sink_facts()` streams CSV straight to parquet with `sink_parquet`, so the derived frame is never held in memory in full.
2. `build_profile_lazy()` replaces ~25 eager passes with one streaming scan.
3. Account **and bank** identities are resolved to integer codes by DuckDB over the parquet, so two 2M-row string columns never enter RAM. Results are fetched as NumPy arrays, which also removes any `pyarrow` dependency.
4. The feature pass was profiled and rewritten — one global `lexsort` instead of 25k per-account argsorts, a dead accumulator list deleted, `np.median` dispatch removed, and all velocity windows batched into one `searchsorted`. Output stayed **bit-identical** across all 36 feature arrays.

## 4. Query latency

### 4.1 Four-hop trace

| Dataset | p50 | p95 | max | Budget (p95) | Verdict | Samples |
|---|---:|---:|---:|---:|---|---:|
| `SYNTHETIC_DEV_250k.csv` | 40.68 ms | 61.32 ms | 242.77 ms | 2000 ms | **PASS** (32.6x inside budget) | 25 |
| `STANDIN_2M.csv` | 455.71 ms | 755.18 ms | 906.12 ms | 2000 ms | **PASS** (2.6x inside budget) | 25 |

Traces are capped at 800 nodes by `max_nodes`, and the median trace in both runs hit that cap — so these are **worst-case full-size traces**, not easy ones.

### 4.2 Live HTTP endpoints (fixture dataset, measured at the client)

| Endpoint | p50 | p95 | Samples |
|---|---:|---:|---:|
| account search | 1.24 ms | 1.43 ms | 100 |
| account details | 13.56 ms | 15.54 ms | 100 |
| counterparties | 11.45 ms | 14.07 ms | 100 |
| transactions | 40.92 ms | 46.38 ms | 100 |

Account search is **PASS** (699.3x inside budget) against its 1,000 ms budget. It is a binary search over a sorted account array, not a DuckDB `LIKE` scan, which is why it is sub-millisecond.

Scoring a single account: p50 0.03 ms, p95 0.05 ms — the MRI is cheap enough to recompute on demand.

## 5. Still unmeasured

| Figure | Why it is blank |
|---|---|
| Graph render frame rate at 500 nodes / 1,500 edges | Needs a real browser profile; headless browsers are unavailable in this environment |
| Detection F1 / precision / recall | **No ground-truth label file exists.** Publishing one would be fabrication |
| Ingest time on the real competition CSV | That file has not been provided |
| Cold start, artifacts to serving | Not yet instrumented |

---

Regenerate with `python3 tools/make_performance_doc.py` after any `make bench` run. Source artifacts: `data/artifacts/bench.json`, `bench_2m.json`, `bench_api.json`.
