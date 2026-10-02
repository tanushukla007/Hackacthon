#!/usr/bin/env python3
"""
Measure what the system actually does on THIS machine and write the result to
data/artifacts/bench.json. Until this runs, the API reports benchmarks as null.
Nothing here is ever estimated: every number is timed.

Usage: python3 tools/bench.py [csv] [--traces 25]
"""
import json, statistics, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.config import ARTIFACT_DIR, RAW_DIR          # noqa: E402
from app.core.store import STORE                      # noqa: E402
from app.core import investigate                      # noqa: E402

csv = Path(sys.argv[1]) if len(sys.argv) > 1 and not sys.argv[1].startswith("-") \
    else sorted(RAW_DIR.glob("*.csv"))[0]
n_traces = 25
if "--traces" in sys.argv:
    n_traces = int(sys.argv[sys.argv.index("--traces") + 1])

t0 = time.perf_counter()
STORE.load(csv)
ingest_s = time.perf_counter() - t0

import numpy as np                                     # noqa: E402
seeds = np.argsort(-STORE.F["out_txn_count"])[:n_traces]

trace_ms, graph_nodes = [], []
for s in seeds:
    a = STORE.aid(int(s))
    t = time.perf_counter()
    p = investigate.run_trace(a, None, None, None, 4)
    trace_ms.append((time.perf_counter() - t) * 1000)
    graph_nodes.append(p["node_count"])

acct_ms = []
for s in seeds:
    t = time.perf_counter()
    from app.core import risk
    risk.score_account(int(s), STORE.F, STORE.P, STORE.cooccurrence_rate)
    acct_ms.append((time.perf_counter() - t) * 1000)

p95 = lambda xs: round(sorted(xs)[max(0, int(len(xs) * 0.95) - 1)], 2)   # noqa: E731
out = {
    "measured_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "source_file": csv.name,
    "dataset_fingerprint": STORE.fingerprint,
    "rows": STORE.n_rows,
    "accounts": STORE.n_accounts,
    "ingest_seconds": round(ingest_s, 2),
    "ingest_stage_ms": STORE.timings,
    "trace_samples": len(trace_ms),
    "trace_ms": {"p50": round(statistics.median(trace_ms), 2), "p95": p95(trace_ms),
                 "max": round(max(trace_ms), 2)},
    "trace_nodes": {"median": int(statistics.median(graph_nodes)), "max": int(max(graph_nodes))},
    "score_account_ms": {"p50": round(statistics.median(acct_ms), 3), "p95": p95(acct_ms)},
}
(ARTIFACT_DIR / "bench.json").write_text(json.dumps(out, indent=2))
print(json.dumps(out, indent=2))
print("\nwritten to", ARTIFACT_DIR / "bench.json")
