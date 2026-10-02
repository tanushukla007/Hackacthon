#!/usr/bin/env python3
"""
Are the evaluation metrics correct?

Two kinds of check:
  1. hand-computed fixtures, so the arithmetic is pinned in the repository;
  2. agreement with scikit-learn, when it happens to be installed.

A metrics module that nobody checks is how fabricated accuracy gets shipped by
accident rather than on purpose.

Usage: python3 tools/test_evaluate.py
"""
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.core import evaluate as ev   # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))


def close(a, b, tol=1e-9):
    return a is not None and b is not None and abs(a - b) <= tol


print("hand-computed confusion matrix")
# 10 accounts: 4 positive. Threshold 0.5.
y = np.array([1, 1, 1, 1, 0, 0, 0, 0, 0, 0], dtype=np.int8)
s = np.array([.9, .8, .4, .3, .7, .6, .2, .1, .05, .01])
c = ev.confusion_at(y, s, 0.5)
check("TP", c["true_positive"] == 2, str(c["true_positive"]))
check("FP", c["false_positive"] == 2, str(c["false_positive"]))
check("FN", c["false_negative"] == 2, str(c["false_negative"]))
check("TN", c["true_negative"] == 4, str(c["true_negative"]))
check("precision = 2/4", close(c["precision"], 0.5))
check("recall = 2/4", close(c["recall"], 0.5))
check("specificity = 4/6", close(c["specificity"], 4 / 6, 1e-6))
check("f1 = 0.5", close(c["f1"], 0.5))
check("balanced accuracy = (0.5+0.667)/2", close(c["balanced_accuracy"], (0.5 + 4 / 6) / 2, 1e-6))
mcc_expected = (2 * 4 - 2 * 2) / np.sqrt(4 * 4 * 6 * 6)
check("mcc matches the formula", close(c["mcc"], float(mcc_expected), 1e-6))
check("accuracy is accompanied by a caveat", "not a meaningful" in c["accuracy_note"])

print("\nprecision@k and recall@k are not the same thing")
# 20 accounts, 5 positives, all ranked in the top 10.
y2 = np.zeros(20, dtype=np.int8)
y2[[0, 1, 2, 3, 4]] = 1
s2 = np.linspace(1.0, 0.0, 20)
rows = {r["k"]: r for r in ev.precision_recall_at_k(y2, s2, ks=(5, 10, 20))}
check("P@5 = 5/5", close(rows[5]["precision_at_k"], 1.0))
check("R@5 = 5/5", close(rows[5]["recall_at_k"], 1.0))
check("P@10 = 5/10 (precision falls as K grows)", close(rows[10]["precision_at_k"], 0.5))
check("R@10 = 5/5 (recall does not)", close(rows[10]["recall_at_k"], 1.0))
check("recovered count is stated explicitly", rows[10]["recovered"] == 5)
check("K larger than the population is clamped and reported",
      rows[20]["evaluated_k"] == 20)

print("\nranking is deterministic under ties")
y3 = np.array([1, 0, 1, 0], dtype=np.int8)
s3 = np.array([0.5, 0.5, 0.5, 0.5])
a = ev.precision_recall_at_k(y3, s3, ks=(2,))[0]["recovered"]
b = ev.precision_recall_at_k(y3, s3, ks=(2,))[0]["recovered"]
check("identical input gives identical top-K", a == b)

print("\ndegenerate cases refuse rather than guess")
y4 = np.zeros(10, dtype=np.int8)
s4 = np.random.RandomState(0).rand(10)
check("ROC with no positives returns no AUC", ev.roc_curve(y4, s4)["auc"] is None)
check("PR with no positives returns no AP",
      ev.pr_curve(y4, s4)["average_precision"] is None)
out = ev.evaluate(["a", "b"], np.array([1.0, 2.0]), {}, threshold=1.0)
check("evaluating with no labels is unavailable, not zero", out["available"] is False)

print("\nunlabelled accounts are excluded, never assumed negative")
ids = ["a", "b", "c", "d"]
sc = np.array([9.0, 8.0, 7.0, 6.0])
res = ev.evaluate(ids, sc, {"a": 1, "b": 0}, threshold=7.5)
check("only labelled accounts are evaluated", res["evaluated_accounts"] == 2)
check("the excluded count is published", res["unlabelled_accounts_excluded"] == 2)
check("no phantom true negatives appear",
      res["confusion"]["true_negative"] + res["confusion"]["false_positive"] == 1)

print("\nagreement with scikit-learn")
try:
    from sklearn.metrics import (average_precision_score, confusion_matrix,
                                 matthews_corrcoef, roc_auc_score)
    rng = np.random.RandomState(42)
    yy = (rng.rand(5000) < 0.06).astype(np.int8)          # ~6% positive, like the brief
    ss = rng.rand(5000) + yy * 0.45                       # a signal, not a perfect one
    check("ROC-AUC matches sklearn",
          close(ev.roc_curve(yy, ss)["auc"], float(roc_auc_score(yy, ss)), 1e-6))
    check("PR-AUC matches sklearn average_precision",
          close(ev.pr_curve(yy, ss)["average_precision"],
                float(average_precision_score(yy, ss)), 1e-6))
    cc = ev.confusion_at(yy, ss, 0.9)
    tn, fp, fn, tp = confusion_matrix(yy, (ss >= 0.9).astype(int)).ravel()
    check("confusion matrix matches sklearn",
          (cc["true_positive"], cc["false_positive"], cc["true_negative"],
           cc["false_negative"]) == (int(tp), int(fp), int(tn), int(fn)))
    check("MCC matches sklearn",
          close(cc["mcc"], float(matthews_corrcoef(yy, (ss >= 0.9).astype(int))), 1e-6))
except ImportError:
    print("  SKIP  scikit-learn is not installed; fixtures above still pin the arithmetic")

print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
sys.exit(1 if FAIL else 0)
