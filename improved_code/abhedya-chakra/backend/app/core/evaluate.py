"""
Detection evaluation.

Every function here needs two things: a score for each account, and a label
for each account. If labels do not exist, the module returns an explicit
"unavailable" result. It never substitutes a default, never scores against
itself, and never reports a metric it could not compute.

Metrics are implemented in NumPy rather than pulled from scikit-learn so the
backend keeps a small dependency set and so the exact tie-handling is visible
in the repository rather than assumed. The implementations are checked against
scikit-learn in tools/test_evaluate.py when it is installed, and against
hand-computed fixtures when it is not.

Terminology, because the brief is right that these get confused:
  Precision@K = of the top K we ranked, how many are truly positive.
  Recall@K    = of ALL true positives, how many appear in the top K.
"""
from __future__ import annotations

import numpy as np

DEFAULT_KS = (100, 250, 500, 1000, 1500, 2000)


# --------------------------------------------------------------------------
# curves and aggregate scores
# --------------------------------------------------------------------------
def _rank_desc(scores: np.ndarray) -> np.ndarray:
    """Indices sorted by score descending. Ties broken by index so the order is
    deterministic across runs - an unstable sort would make Precision@K jitter."""
    return np.lexsort((np.arange(len(scores)), -scores))


def roc_curve(y: np.ndarray, s: np.ndarray) -> dict:
    order = _rank_desc(s)
    y_sorted = y[order]
    P, N = int(y.sum()), int((1 - y).sum())
    if P == 0 or N == 0:
        return {"fpr": [], "tpr": [], "thresholds": [], "auc": None,
                "note": "ROC is undefined when one class is empty."}
    tp = np.cumsum(y_sorted)
    fp = np.cumsum(1 - y_sorted)
    tpr = np.concatenate([[0.0], tp / P])
    fpr = np.concatenate([[0.0], fp / N])
    thr = np.concatenate([[np.inf], s[order]])
    auc = float(np.trapezoid(tpr, fpr)) if hasattr(np, "trapezoid") else float(np.trapz(tpr, fpr))
    return {"fpr": _thin(fpr), "tpr": _thin(tpr), "thresholds": _thin(thr), "auc": auc}


def pr_curve(y: np.ndarray, s: np.ndarray) -> dict:
    """Precision-recall curve plus average precision.

    Average precision is the step-wise sum used by scikit-learn
    (sum over thresholds of (R_n - R_{n-1}) * P_n), NOT the trapezoid, because
    trapezoidal interpolation of a PR curve is optimistically biased.
    """
    order = _rank_desc(s)
    y_sorted = y[order]
    P = int(y.sum())
    if P == 0:
        return {"precision": [], "recall": [], "average_precision": None,
                "note": "PR is undefined with no positives."}
    tp = np.cumsum(y_sorted)
    k = np.arange(1, len(y_sorted) + 1)
    precision = tp / k
    recall = tp / P
    ap = float(np.sum((recall - np.concatenate([[0.0], recall[:-1]])) * precision))
    return {"precision": _thin(precision), "recall": _thin(recall),
            "average_precision": ap, "baseline": float(P / len(y))}


def _thin(a: np.ndarray, n: int = 300) -> list[float]:
    """Downsample a curve for transport. The endpoints are always kept."""
    a = np.asarray(a, dtype=float)
    if len(a) <= n:
        return [round(float(x), 6) for x in a]
    idx = np.unique(np.concatenate([
        np.linspace(0, len(a) - 1, n).astype(int), [0, len(a) - 1]]))
    return [round(float(a[i]), 6) for i in idx]


# --------------------------------------------------------------------------
# confusion matrix at a threshold
# --------------------------------------------------------------------------
def confusion_at(y: np.ndarray, s: np.ndarray, threshold: float) -> dict:
    pred = (s >= threshold).astype(np.int8)
    tp = int(((pred == 1) & (y == 1)).sum())
    fp = int(((pred == 1) & (y == 0)).sum())
    tn = int(((pred == 0) & (y == 0)).sum())
    fn = int(((pred == 0) & (y == 1)).sum())
    return {"threshold": float(threshold), **_from_counts(tp, fp, tn, fn)}


def _from_counts(tp: int, fp: int, tn: int, fn: int) -> dict:
    prec = tp / (tp + fp) if (tp + fp) else None
    rec = tp / (tp + fn) if (tp + fn) else None
    spec = tn / (tn + fp) if (tn + fp) else None
    f1 = (2 * prec * rec / (prec + rec)) if (prec and rec) else (0.0 if (prec is not None and rec is not None) else None)
    bal = ((rec + spec) / 2) if (rec is not None and spec is not None) else None
    denom = float((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn))
    mcc = ((tp * tn - fp * fn) / np.sqrt(denom)) if denom > 0 else None
    return {
        "true_positive": tp, "false_positive": fp,
        "true_negative": tn, "false_negative": fn,
        "predicted_positive": tp + fp, "predicted_negative": tn + fn,
        "actual_positive": tp + fn, "actual_negative": tn + fp,
        "precision": _r(prec), "recall": _r(rec), "specificity": _r(spec),
        "f1": _r(f1), "balanced_accuracy": _r(bal), "mcc": _r(mcc),
        "accuracy": _r((tp + tn) / (tp + tn + fp + fn)) if (tp + tn + fp + fn) else None,
        "accuracy_note": ("Accuracy is reported for completeness only. With a small "
                          "positive class it is dominated by true negatives and is not a "
                          "meaningful measure of detection quality."),
    }


def _r(v, nd: int = 6):
    return None if v is None else round(float(v), nd)


# --------------------------------------------------------------------------
# ranking metrics
# --------------------------------------------------------------------------
def precision_recall_at_k(y: np.ndarray, s: np.ndarray, ks=DEFAULT_KS) -> list[dict]:
    order = _rank_desc(s)
    y_sorted = y[order]
    P = int(y.sum())
    out = []
    for k in ks:
        kk = min(int(k), len(y_sorted))
        hits = int(y_sorted[:kk].sum())
        out.append({
            "k": int(k),
            "evaluated_k": kk,
            "recovered": hits,
            "precision_at_k": _r(hits / kk) if kk else None,
            "recall_at_k": _r(hits / P) if P else None,
            "total_positives": P,
            "statement": (f"Of the top {kk} ranked accounts, {hits} are labelled positive; "
                          f"that is {hits}/{P} of all labelled positives."
                          if P else "No positives in the label set."),
        })
    return out


def threshold_sweep(y: np.ndarray, s: np.ndarray, steps: int = 40) -> list[dict]:
    """Sweep thresholds across the observed score range.

    This exists to CHOOSE an operating point on validation data, not to report
    the best number found. The caller is responsible for not tuning on test.
    """
    lo, hi = float(np.min(s)), float(np.max(s))
    if hi <= lo:
        return []
    rows = []
    for t in np.linspace(lo, hi, steps):
        c = confusion_at(y, s, t)
        rows.append({k: c[k] for k in
                     ("threshold", "true_positive", "false_positive", "true_negative",
                      "false_negative", "precision", "recall", "f1")})
    return rows


# --------------------------------------------------------------------------
# error analysis
# --------------------------------------------------------------------------
def error_analysis(account_ids, y: np.ndarray, s: np.ndarray, threshold: float,
                   limit: int = 10) -> dict:
    """The accounts the detector got most wrong, worst first.

    False positives are ordered by score (confidently wrong), false negatives
    by score ascending (missed by the widest margin).
    """
    pred = (s >= threshold).astype(np.int8)
    fp_idx = np.where((pred == 1) & (y == 0))[0]
    fn_idx = np.where((pred == 0) & (y == 1))[0]
    fp_idx = fp_idx[np.argsort(-s[fp_idx])][:limit]
    fn_idx = fn_idx[np.argsort(s[fn_idx])][:limit]
    rank = {int(i): r + 1 for r, i in enumerate(_rank_desc(s))}
    fmt = lambda i: {"account_id": account_ids[int(i)], "score": _r(float(s[i]), 2),  # noqa: E731
                     "rank": rank[int(i)]}
    return {"top_false_positives": [fmt(i) for i in fp_idx],
            "top_false_negatives": [fmt(i) for i in fn_idx],
            "threshold": float(threshold)}


# --------------------------------------------------------------------------
# the one entry point the API uses
# --------------------------------------------------------------------------
def evaluate(account_ids: list[str], scores: np.ndarray, labels: dict[str, int],
             threshold: float, ks=DEFAULT_KS) -> dict:
    """Full evaluation over the accounts that carry a label.

    Accounts without a label are EXCLUDED and counted, rather than assumed
    negative: assuming unlabelled means negative would silently invent
    thousands of true negatives and inflate every metric that uses them.
    """
    mask = np.array([a in labels for a in account_ids], dtype=bool)
    n_labelled = int(mask.sum())
    if n_labelled == 0:
        return {"available": False,
                "reason": "No account in this dataset appears in the label file."}
    y = np.array([labels[a] for a, m in zip(account_ids, mask) if m], dtype=np.int8)
    s = scores[mask]
    ids = [a for a, m in zip(account_ids, mask) if m]

    conf = confusion_at(y, s, threshold)
    roc = roc_curve(y, s)
    pr = pr_curve(y, s)
    return {
        "available": True,
        "evaluated_accounts": n_labelled,
        "unlabelled_accounts_excluded": int((~mask).sum()),
        "exclusion_note": ("Accounts with no label are excluded from every metric. "
                           "They are not assumed to be negative."),
        "actual_positive": int(y.sum()),
        "actual_negative": int((1 - y).sum()),
        "operating_threshold": float(threshold),
        "confusion": conf,
        "roc_auc": _r(roc.get("auc")),
        "pr_auc": _r(pr.get("average_precision")),
        "pr_baseline": _r(pr.get("baseline")),
        "curves": {"roc": roc, "pr": pr},
        "ranking": precision_recall_at_k(y, s, ks),
        "threshold_sweep": threshold_sweep(y, s),
        "errors": error_analysis(ids, y, s, threshold),
        "priority_note": ("With a small positive class, PR-AUC, Recall@K and Precision@K "
                          "describe detection quality better than accuracy or ROC-AUC."),
    }


def unavailable(reason: str, searched: list[str] | None = None) -> dict:
    """The honest answer when there is nothing to evaluate against."""
    return {
        "available": False,
        "ground_truth_available": False,
        "reason": reason,
        "searched_paths": searched or [],
        "metrics": None,
        "what_is_published_instead": [
            "a ranked candidate list, with the evidence behind every rank",
            "deterministic typology tests over constructed cases",
            "measured ingestion and query benchmarks",
        ],
        "never": ("No accuracy, precision, recall, F1, confusion matrix or AUC is "
                  "produced without labels. An unlabelled dataset cannot score itself."),
    }
