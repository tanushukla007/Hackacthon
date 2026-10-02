#!/usr/bin/env python3
"""
Stage-level ingestion profile (brief §20).

Loads a CSV through the real pipeline and reports, per stage: duration, share
of total, and what the stage actually does. Also records peak RSS, because an
optimisation that trades memory for time has to be visible as such.

Usage: python3 tools/profile_ingest.py [csv] [--repeat N]
"""
from __future__ import annotations

import os
import resource
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.config import BUDGET_MS, RAW_DIR      # noqa: E402
from app.core.store import STORE               # noqa: E402

WHAT = {
    "fingerprint": "SHA-256 of the whole file, 1 MB at a time",
    "normalize":   "parse CSV, clean accounts/IFSC, parse timestamps, derive flags",
    "encode":      "build the account index and join integer ids onto every row",
    "facts":       "write facts.parquet and register the DuckDB view",
    "graph":       "extract edge arrays and build the CSR adjacency",
    "features":    "per-account aggregates, temporal passes, percentile ranks",
    "profile":     "measure the dataset profile published by /api/ingest/profile",
    "score":       "score every account with the canonical risk engine",
}


def rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    csv = Path(args[0]) if args else sorted(RAW_DIR.glob("*.csv"))[0]
    if not csv.exists():
        print(f"no such file: {csv}")
        return 2

    size_mb = csv.stat().st_size / 1e6
    print(f"file     {csv.name}  ({size_mb:.0f} MB)")
    print(f"budget   {BUDGET_MS['ingest_s']} s\n")

    t0 = time.perf_counter()
    STORE.load(csv)
    total = time.perf_counter() - t0

    rows = STORE.n_rows
    print(f"{'stage':<13} {'seconds':>8} {'% total':>8}   what it does")
    print("-" * 96)
    stages = sorted(STORE.stages, key=lambda s: -s["ms"])
    for s in stages:
        sec = s["ms"] / 1000.0
        print(f"{s['stage']:<13} {sec:>8.2f} {sec / total * 100:>7.1f}%   "
              f"{WHAT.get(s['stage'], '')}")
    print("-" * 96)
    print(f"{'TOTAL':<13} {total:>8.2f} {100.0:>7.1f}%")

    slowest = stages[0]
    print(f"\nrows                 {rows:,}")
    print(f"accounts             {STORE.n_accounts:,}")
    print(f"throughput           {rows / total:,.0f} rows/s")
    print(f"peak RSS             {rss_mb():.0f} MB")
    print(f"slowest stage        {slowest['stage']} "
          f"({slowest['ms'] / 1000:.2f} s, {slowest['ms'] / 10 / total:.1f}%)")
    budget = BUDGET_MS["ingest_s"]
    verdict = "WITHIN" if total <= budget else "OVER"
    print(f"verdict              {verdict} the {budget} s budget "
          f"({total:.2f} s)")
    if total > budget:
        print(f"                     needs {total - budget:.1f} s removed; the "
              f"{slowest['stage']} stage is the place to look")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
