# Architecture — Abhedya-Chakra

**Companion to the PRD.** The PRD says *what* and *why*; this document says *how*, at the level of detail a teammate needs to open an editor and start typing. Section numbers in `[§n]` refer to the PRD.

---

## 1. The sizing insight that drives everything

```text
  TRANSACTION ROWS : 2,000,000     ← big as rows (the fact table)
  UNIQUE ACCOUNTS  :    24,873     ← small as nodes (the graph)   [DATA-PRELIM]
  UNIQUE PAIRS     : ≈1,996,771    ← ≈99.8% of rows are their own pair
  AVG DEGREE       :   ~80 out / ~80 in  (every account does both)
  OBSERVED WINDOW  : 2026-09-15 → 2026-09-29  (≈15 days)
```

> **Verification status:** these figures are preliminary profiling output. `make profile-check`
> (PRD FR-A05) asserts them against the CSV in Phase 1; nothing is tuned before it passes.

Three consequences, and every other decision follows from them:

1. **Separate the log from the graph.** The transaction log is an immutable columnar fact table (DuckDB) used *only* for evidence retrieval. The graph is a small integer-encoded CSR structure held in RAM and used *only* for traversal. They are joined by a dense `int32` account index.
2. **Everything per-account is precomputable.** ≈24,873 rows of features is nothing, and they are computed **on both the incoming and the outgoing side** — "collector" and "distributor" are role descriptors, not exclusive capabilities (PRD §2.4). The entire detection pass is one `GROUP BY` plus vectorised arithmetic, done at ingest time, inside the 60-second budget.
3. **The 2-second query budget is not spent on traversal.** A pruned 4-hop BFS over ≈24.9k nodes takes tens of milliseconds — *provided the window is pruned*: at a 72-hour window the branching factor is ≈16 and hop 4 reaches ≈66,885 nodes, i.e. the whole population. The default window is therefore **6 hours** (PRD §7.5). It is spent on evidence row retrieval and JSON serialisation. Optimise *those*.

> **The rule:** if a request-time code path touches 2,000,000 rows, it is wrong. Pre-aggregate it at ingest.

---

## 2. Component map

```text
┌────────────────────────────────────────────────────────────────────────────┐
│  backend/abhedya/                                                          │
│                                                                            │
│  ingest/        loader.py    CSV → typed Polars/DuckDB frame               │
│                 normalize.py casts, enums, IFSC/IP validation, flags       │
│                 encode.py    account dictionary, dense int32 indices       │
│                 manifest.py  SHA-256 fingerprint, counts, timings          │
│                                                                            │
│  graph/         csr.py       build + load CSR arrays (fwd and reverse)     │
│                 traverse.py  value-attributed temporal BFS  [§17]          │
│                 subgraph.py  ego networks, caps, leaf collapsing           │
│                                                                            │
│  detect/        features.py  ~40 per-account features        [§14.1]       │
│                 rules.py     rule cards R1–R10 + suppressors [§14.2–14.3]  │
│                 scoring.py   Mule Risk Index                 [§15]         │
│                 layers.py    L1/L2/L3 assignment             [§16]         │
│                 rings.py     weak components, cycles ≤ 4                   │
│                                                                            │
│  evidence/      schema.py    pydantic EvidenceObject         [§20.2]       │
│                 builder.py   trace result → EvidenceObject                 │
│                 validator.py V1–V10 output checks            [§20.3]       │
│                                                                            │
│  docs/          diary.py     case diary assembly             [§21.2]       │
│                 requisition.py per-bank freeze notices       [§21.3]       │
│                 pdf.py       Jinja2 → HTML → WeasyPrint / python-docx      │
│                 templates/   *.html.j2 + print.css                         │
│                                                                            │
│  api/routers/   search · investigate · graph · timeline · documents · eval │
│  bench/         bench_ingest.py · bench_trace.py · bench_eval.py           │
│  config.py      EVERY threshold, one file, env-overridable                 │
│  state.py       AppState singleton, loaded once at startup                 │
└────────────────────────────────────────────────────────────────────────────┘
```

### Dependency direction (enforce this in review)

```text
api ──▶ evidence ──▶ detect ──▶ graph ──▶ ingest ──▶ config
 │                      │          │
 └──────────▶ docs ─────┘          └── nothing imports api; nothing imports upward
```

Nothing below `api` may import FastAPI. Nothing below `evidence` may import Jinja. This keeps the engine testable without a server and lets M3 run detection in a notebook.

---

## 3. Data flow, end to end

```text
 CSV (2M rows)
   │  [1] duckdb.read_csv / pl.scan_csv        ~8–15 s
   ▼
 raw frame
   │  [2] normalize: casts, enums, regex flags  ~5–8 s
   │  [3] encode:    accounts → int32 dense     ~3–5 s
   │  [4] derive:    day_index, minute_bucket, terminal flags  ~4–7 s
   ▼
 transactions table ───────────────────────────▶ DuckDB  (FACT STORE, evidence)
   │  [6] GROUP BY src_idx / dst_idx            ~3–5 s
   ▼
 features (25k rows) ──────────────────────────▶ Parquet (FEATURE STORE)
   │  [7] sort by (src, ts) → indptr/indices    ~4–6 s
   ▼
 CSR arrays ───────────────────────────────────▶ graph.npz (GRAPH STORE)
   │  [8] rules → MRI → rings → cycles          ~1–2 s
   ▼
 manifest.json   (fingerprint + timings + config snapshot)

                                        TOTAL ≈ 35–55 s    target ≤ 60 s
```

**Runtime (per request):**

```text
 GET /api/investigate?account=…
   → AppState.index_of(account)                       O(1) dict
   → traverse.trace(idx, depth=4, …)                  CSR, NumPy          ~60 ms
   → detect.layers.assign(trace)                      vectorised           ~40 ms
   → DuckDB: SELECT … WHERE txn_id IN (…)             indexed, ~2k rows   ~250 ms
   → response assembly + orjson                                           ~120 ms
                                                              total ≈ 485 ms
```

---

## 4. Storage layer

### 4.1 Fact store (DuckDB)

One table, append-only, never mutated after ingest:

```sql
CREATE TABLE transactions (
  row_id        INTEGER,      -- provenance anchor for evidence
  txn_id        VARCHAR,
  src_idx       INTEGER,      -- dense account index
  dst_idx       INTEGER,
  sender_acct   VARCHAR(12),  -- kept for evidence rendering, never for joins
  receiver_acct VARCHAR(12),
  sender_ifsc   VARCHAR(11),
  receiver_ifsc VARCHAR(11),
  amount        DOUBLE,
  ts            TIMESTAMP,
  ts_epoch      BIGINT,
  minute_bucket INTEGER,
  day_index     UTINYINT,
  mode_code     UTINYINT,
  narration     VARCHAR,
  ip            VARCHAR,
  ip_octet1     UTINYINT,
  device        VARCHAR,
  is_foreign_ip BOOLEAN,
  is_automation BOOLEAN,
  narr_crypto   BOOLEAN,
  narr_wallet   BOOLEAN,
  amount_round  BOOLEAN
);
CREATE INDEX idx_src ON transactions(src_idx, ts_epoch);
CREATE INDEX idx_dst ON transactions(dst_idx, ts_epoch);
CREATE INDEX idx_txn ON transactions(txn_id);
```

Account numbers are stored as **strings** everywhere (leading zeros are real) and never used as join keys — `src_idx`/`dst_idx` are.

### 4.2 Graph store (NumPy CSR)

```python
# forward, sorted by (src, dst); aggregated per unique pair
out_indptr   : int32[N+1]
out_indices  : int32[E]      # destination
out_weight   : float64[E]    # total ₹ on the pair
out_count    : int32[E]      # transactions on the pair
out_first_ts : int64[E]
out_last_ts  : int64[E]
# in_* mirror for reverse ("who funded this account")
```

Neighbours of `u` = `out_indices[out_indptr[u]:out_indptr[u+1]]`. Pure slicing — no hashing, cache-friendly, releases the GIL inside NumPy.

**Why not NetworkX:** a Python object graph of ≈24.9k nodes / ≈2.0 M edges costs several hundred MB and is 50–100× slower to traverse. NetworkX is permitted **only** in offline notebooks to cross-check centrality results.

### 4.3 Memory budget (steady state)

| Structure | Size |
|---|---:|
| CSR forward (6 arrays × ≈2.0 M) | ~64 MB |
| CSR reverse | ~64 MB |
| Features DataFrame (≈24.9k × ~45 float64) | ~9 MB |
| Account dictionary (two-way maps) | ~6 MB |
| DuckDB page cache (configurable) | ~512 MB |
| Python + FastAPI + interpreter | ~250 MB |
| **Steady-state total** | **≈ 1.0 GB** |
| Ingest peak (transient frames) | ≤ 6 GB |

### 4.4 Artifacts and caching

`data/artifacts/` holds `abhedya.duckdb`, `graph.npz`, `features.parquet`, `manifest.json`. Re-ingesting a file whose SHA-256 matches the manifest **skips straight to artifact load** — cold start ≤ 3 s. This is demo-day insurance: you never re-ingest in front of a judge.

---

## 5. Process model and concurrency

Single `uvicorn` process, `--workers 1`. The graph lives in RAM; additional workers would duplicate it.

```python
@asynccontextmanager
async def lifespan(app):
    state.load()                 # DuckDB connect + npz mmap + parquet → ~3 s
    yield
    state.close()
```

- Endpoints are `async def`; CPU-bound traversal is dispatched to a small `ThreadPoolExecutor` (NumPy releases the GIL, so this genuinely parallelises).
- DuckDB connections are per-request cursors off one shared read-only connection.
- An LRU cache (`maxsize=128`) memoises trace results keyed by `(account, depth, min_value, window)`. **Pre-warm it for the demo accounts.**
- There is no write path at request time. The system is read-only after ingest, which eliminates an entire class of concurrency bugs.

---

## 6. Traversal algorithm (the 40%-weighted path)

Plain BFS is wrong here for two reasons: it follows edges that happened *before* the money arrived, and it fans out through high-degree aggregator accounts until the whole graph is in the result. We use **temporally-ordered, value-attributed BFS**:

```python
def trace(victim, t0, depth=4, min_value=1000, window=72*3600, topk=25):
    frontier = [(victim, INF, t0, 0)]
    traced_in = defaultdict(float)
    edges = []
    while frontier:
        u, value_at_u, t_in, hop = frontier.pop()
        if hop >= depth: continue
        cands = txns_from(u, after=t_in, before=t_in + window)   # causality
        if not cands: continue
        total_out = sum(c.amount for c in cands)
        for c in top_by_amount(cands, topk):
            share  = c.amount / max(total_out, c.amount)
            traced = min(value_at_u * share, c.amount)           # attribution
            if traced < min_value: continue                      # pruning
            if is_hub(c.dst) and traced < HUB_PASSTHROUGH_MIN: continue
            edges.append(Edge(u, c.dst, c.txn_id, c.amount, traced, c.ts, hop+1))
            traced_in[c.dst] += traced
            if c.dst not in seen_at_shallower_hop:
                frontier.append((c.dst, traced, c.ts, hop+1))
            else:
                mark_cycle(u, c.dst)
```

| Property | Why it matters |
|---|---|
| **Temporal causality** | An outbound transfer can only carry stolen funds if it post-dates the inbound credit. Eliminates most spurious paths for free. |
| **Proportional attribution** | ₹1,00,000 split five ways attributes ₹20,000 per child — so "funds currently held" is arithmetically correct and survives cross-examination. |
| **Value pruning** | Floor is `max(₹100, 0.2% × initial_amount)` — **not** a flat ₹1,000, which sat above the ₹899.35 median transaction and would have truncated genuine trails at hop 1–2. |
| **Hub guard** | Threshold is distribution-relative: `max(500, p99_out_degree × 3)` read from `profile.json`, not a hard-coded 2,000. Hubs are entered but not expanded unless traced value is material, then only the top-15 edges. Marked `AGGREGATOR`, excluded from freeze lists. |
| **Determinism** | Same input → byte-identical output. Required for golden-file tests and a reproducible demo. |

**Reverse mode** (`direction=up`) answers "who funded this account?" and is the fallback when a blind-test ID turns out to be a mule rather than a victim — see PRD §17.5. Do not skip this; it protects the highest-weighted criterion.

---

## 7. Detection pipeline

```text
transactions ─GROUP BY─▶ raw aggregates ─▶ derived features ─▶ rule cards
                                                 │                 │
                                                 ▼                 ▼
                                          component scores    reason strings
                                                 │                 │
                                                 └────▶ MRI 0–100 ◀┘
                                                          │
                                        suppressors ──────┤
                                        ring multiplier ──┤
                                        victim proximity ─┘
```

Rule cards are pure functions over a feature row returning `(fired: bool, contribution: float, reason: str)`. This shape is what makes the system explainable: **a score with no reasons is a bug**, and the reason strings flow straight into the case diary.

Thresholds live only in `config.py`. Member 3 owns that file; nobody inlines a magic number anywhere else.

---

## 8. API layer

- FastAPI with pydantic response models → OpenAPI docs are generated free at `/docs` (show this to judges).
- `orjson` response class; account numbers always strings; amounts always numbers in rupees.
- Every response carries `query_ms` and `dataset_fingerprint`. The visible `query_ms` is a **demo asset**, not decoration.
- Uniform error envelope with a stable `code`, a human message, and suggestions where useful (fuzzy account match on `ACCOUNT_NOT_FOUND`).
- A `MOCK=1` environment flag makes every endpoint return realistic fixtures. **This ships in the first 90 minutes** so the frontend and document work are never blocked on the engine.

---

## 9. Frontend architecture

```text
App
├── SystemBar          dataset fingerprint, row count, READY state, query_ms
├── SearchBar          account input, validation, fuzzy suggest
├── KpiStrip           siphoned · mule nodes · layers · top risk · still held
├── GraphCanvas        Cytoscape: dagre (layered) ⇄ fcose (force)
│   └── LayerLegend
├── NodeInspector      MRI breakdown, reasons, counterparties, txn table
├── TimelineSlider     15-day range + play, histogram, minute granularity
├── EvidenceBasket     pinned accounts/transactions → feeds documents
└── DocumentModal      case diary / requisition preview + PDF-DOCX download
```

**Rendering rules that keep it at 30 fps:**
- Layout runs **once per trace result**, never per filter. Timeline filtering toggles `display:none` on existing elements inside a single `cy.batch()`.
- `hideEdgesOnViewport: true`, `textureOnViewport: true`, `motionBlur: false`.
- Hard caps: 800 nodes / 2,500 edges, with low-value leaves collapsed into an expandable `+N accounts (₹X)` node.
- The stylesheet is memoised; node data carries precomputed `size`/`colour` so style functions stay O(1).

---

## 10. Document pipeline

```text
TraceResult ─▶ EvidenceBuilder ─▶ EvidenceObject (pydantic, validated)
                                        │
                        ┌───────────────┴───────────────┐
                        ▼                               ▼
              Jinja2 template                    LLM (prose only,
              (ALL facts live here)               zero digits allowed)
                        └───────────────┬───────────────┘
                                        ▼
                              OutputValidator V1–V10
                                        ▼
                         HTML ─▶ WeasyPrint ─▶ PDF
                              ─▶ python-docx ─▶ DOCX
```

The inversion that makes this safe: **the template owns the facts, the model owns the grammar.** A model that cannot emit a digit cannot invent an account number. The validator is the second line of defence, not the first.

---

## 11. Architecture Decision Records

| # | Decision | Alternatives rejected | Rationale |
|---|---|---|---|
| **ADR-1** | NumPy CSR for the graph | NetworkX, Neo4j, igraph | 25k nodes fit trivially; CSR traversal is ~100× faster than NetworkX and needs no server. Neo4j violates "local, simple deployment". |
| **ADR-2** | DuckDB as fact store | SQLite, Parquet-only, pandas | Vectorised CSV reader hits the 60 s target alone; SQL for evidence pulls; single-file artifact; zero config. |
| **ADR-3** | Polars for ingest transforms | pandas | 5–20× faster on 2M rows, strict schema catches dirty data at the boundary, Arrow-native handoff to DuckDB. |
| **ADR-4** | Single process, state in RAM | Multi-worker + shared store | Avoids duplicating the graph per worker; read-only after ingest so there is no coherency problem. |
| **ADR-5** | Template-first documents, LLM for prose only | LLM generates the document | The PS demands programmatic prevention of hallucinated facts. A prompt is not a guarantee; a template plus a validator is. |
| **ADR-6** | Cytoscape.js | D3 force, vis.js, react-force-graph | Best directed/compound support, `dagre` gives the layered Victim→L1→L2→L3 read that matches the PS diagram exactly. |
| **ADR-7** | Layers are relative to a victim | Global per-account layer label | An account can be L2 in one case and L1 in another. We also store a global modal role to cover the other evaluation interpretation. |
| **ADR-8** | Value-attributed temporal BFS | Plain k-hop BFS | Plain BFS follows pre-dated edges and explodes through hubs; attribution is also what makes "currently held" defensible. |
| **ADR-9** | Local Ollama, optional | Cloud LLM API | PS requires local core execution. The no-LLM path is complete, so the demo never depends on a model being warm. |
| **ADR-10** | All thresholds in `config.py` | Constants near usage | One owner, one diff to retune, and the config snapshot goes into every generated document for reproducibility. |

---

## 12. Failure modes and defences

| Failure | Defence |
|---|---|
| Ingest exceeds 60 s | Streaming mode (`STREAMING=1`), Parquet pre-conversion, chunked CSR build |
| OOM on a bigger file | int32/uint8 encoding, aggregated edges, Polars streaming collect |
| Trace explodes through a hub | Hub guard + value pruning + top-K expansion |
| Trace exceeds 2 s | LRU cache, reduce `topk`, pre-warm demo accounts |
| Blind ID has no downstream flow | Auto-detect and offer the upstream trace; never show an empty canvas |
| Browser freeze | Node/edge caps, leaf collapsing, `[Simplify view]` escape hatch |
| LLM unavailable or slow | `use_llm=false` produces a complete, correct document |
| Validator rejects output | Regenerate twice, then fall back to pure template; never ship an unvalidated document |
| Schema differs from spec | Column alias map in `ingest/loader.py`; a five-minute fix, not a rewrite |
| Backend dies mid-demo | UI reconnect card with the restart command; tagged `v1.0-freeze` build on disk |

---

## 13. Testing strategy

| Layer | What it covers |
|---|---|
| Unit | Normalization edge cases (leading zeros, bad IFSC/IP), **row conservation and duplicate-`Transaction_ID` handling (no row is ever dropped — every row keeps an immutable `source_row_id`)**, CSR vs a NetworkX reference on a 1,000-node fixture, each rule card, MRI monotonicity and single-feature dominance caps, validator **V1–V12** |
| Golden file | Fixed trace input → expected JSON; fixed EvidenceObject → expected document text |
| Integration | Ingest a 50k fixture → investigate an injected victim → L1/L2/L3 sets must match the injection exactly |
| Performance smoke | Fails CI if ingest > 75 s or p95 trace > 2.5 s (buffer under the real targets) |
| Adversarial | Non-existent account, incoming-only account, 5,000-counterparty hub, single-transaction account, malformed input, backend restart, LLM down, Wi-Fi off |

---

## 14. Extension points (post-hackathon)

Swap `detect/scoring.py` for a learned model behind the same `(features) → (score, reasons)` interface · add bank-side entity resolution in `ingest/encode.py` · add new document types by dropping a template into `docs/templates/` and a builder into `docs/` · add a second dataset by making `AppState` a registry keyed by case ID.
