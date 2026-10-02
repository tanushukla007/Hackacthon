#!/usr/bin/env python3
"""
Why does the score distribution have no high tail?

Measures, for every account in the loaded dataset: the final MRI, and the
score each component actually contributed. Prints the distribution of each so
the ceiling can be seen rather than guessed at.

This is a diagnosis tool. It changes nothing.

Usage: python3 tools/diagnose_risk.py [csv]
"""
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.config import MRI_BANDS, MRI_WEIGHTS, RAW_DIR   # noqa: E402
from app.core import risk                                # noqa: E402
from app.core.store import STORE                         # noqa: E402

csv = Path(sys.argv[1]) if len(sys.argv) > 1 else sorted(RAW_DIR.glob("*.csv"))[0]
STORE.load(csv)
F, P = STORE.F, STORE.P
n = len(F["in_degree"])
print(f"dataset: {csv.name} · {n:,} accounts\n")

keys = list(MRI_WEIGHTS)
comp = {k: np.zeros(n) for k in keys}
mri = np.zeros(n)
capped = 0

for i in range(n):
    s = risk.score_account(i, F, STORE.P, STORE.cooccurrence_rate)
    mri[i] = s["mri"]
    for c in s["components"]:
        comp[c["key"]][i] = c["score"]
    if s.get("cap_applied"):
        capped += 1

print("MRI distribution")
for q in (50, 75, 90, 95, 99, 99.9):
    print(f"  p{q:<5} {np.percentile(mri, q):6.2f}")
print(f"  max   {mri.max():6.2f}")
print(f"  mean  {mri.mean():6.2f}")

print("\nbands")
for name, lo, hi in MRI_BANDS:
    c = int(((mri >= lo) & (mri < hi)).sum())
    print(f"  {name:<9} {c:>7,}  {c / n * 100:5.2f}%")

print("\ncomponent contribution (score out of its weight)")
print(f"  {'component':<20} {'weight':>6} {'max':>7} {'p99':>7} {'p90':>7} {'p50':>7} "
      f"{'% zero':>7} {'% of weight at max':>19}")
for k in keys:
    v = comp[k]
    w = MRI_WEIGHTS[k]
    print(f"  {k:<20} {w:>6} {v.max():>7.2f} {np.percentile(v, 99):>7.2f} "
          f"{np.percentile(v, 90):>7.2f} {np.percentile(v, 50):>7.2f} "
          f"{(v == 0).mean() * 100:>6.1f}% {v.max() / w * 100:>18.1f}%")

print(f"\ntheoretical maximum if every component saturated: {sum(MRI_WEIGHTS.values())}")
print(f"highest MRI actually observed:                    {mri.max():.2f}")
print(f"accounts hitting the terminal-solo cap:           {capped:,}")

top = np.argsort(-mri)[:5]
print("\ntop 5 accounts, component by component")
for i in top:
    s = risk.score_account(int(i), F, STORE.P, STORE.cooccurrence_rate)
    parts = " ".join(f"{c['key']}={c['score']:.1f}/{c['weight']}" for c in s["components"])
    print(f"  {STORE.aid(int(i))} MRI {s['mri']:5.1f} {s['band']:<8} {parts}")

# How many accounts have several independent signals at once? That is the
# question the brief is really asking: is the score able to express "many
# different things are wrong here at the same time"?
strong = {k: (comp[k] >= MRI_WEIGHTS[k] * 0.6) for k in keys}
stack = np.sum([strong[k].astype(int) for k in keys], axis=0)
print("\nhow many components are strong (>=60% of weight) per account")
for c in range(0, len(keys) + 1):
    cnt = int((stack == c).sum())
    if cnt:
        print(f"  {c} strong component(s): {cnt:>7,} accounts   max MRI in group "
              f"{mri[stack == c].max():6.2f}")
