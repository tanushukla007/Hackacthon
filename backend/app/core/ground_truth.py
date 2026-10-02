"""
Ground-truth discovery.

The one rule: this module may report that labels exist, or report that they do
not. It may never invent them. Nothing downstream is allowed to publish an
accuracy, a precision, a recall or a confusion matrix unless `available` is
True here, and `available` is True only when a file on disk says so.

Discovery is deliberately literal. It looks for files whose name suggests
labels, reads the header, and requires a column that identifies an account and
a column that carries a label. If it cannot find both, the file is reported as
rejected WITH THE REASON, so a missing label file never looks like an absent
one and vice versa.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import polars as pl

from ..config import ACCOUNT_WIDTH, DATA_DIR

# Where a label file could plausibly live. Searched in this order.
SEARCH_DIRS = (DATA_DIR, DATA_DIR / "raw", DATA_DIR / "labels", DATA_DIR / "ground_truth",
               DATA_DIR / "artifacts", DATA_DIR.parent)

# Filename hints. A file still has to prove itself by its columns.
NAME_HINTS = ("ground_truth", "groundtruth", "ground-truth", "labels", "label",
              "mule", "suspect", "fraud", "flagged", "answer", "key")

# Column name candidates, matched case-insensitively after stripping non-alphanumerics.
ACCOUNT_COLS = ("accountid", "account", "accountno", "accountnumber", "acct",
                "muleaccount", "suspectaccount", "account_no")
LABEL_COLS = ("label", "ismule", "mule", "issuspect", "suspect", "isfraud", "fraud",
              "class", "target", "y", "flag", "redflag", "isredflag")

# Values that mean "this account is a positive". Anything else is a negative,
# except unparseable values, which are reported rather than guessed.
TRUE_VALUES = {"1", "1.0", "true", "yes", "y", "mule", "suspect", "fraud", "positive",
               "red", "redflag", "red_flag", "flagged", "t"}
FALSE_VALUES = {"0", "0.0", "false", "no", "n", "normal", "legit", "legitimate",
                "genuine", "negative", "clean", "f", ""}


def _norm_col(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _norm_account(value: str) -> str:
    """Same normalisation ingest applies, so labels and transactions can join."""
    digits = re.sub(r"\D", "", (value or "").strip())
    return digits.zfill(ACCOUNT_WIDTH) if digits else ""


@dataclass
class GroundTruth:
    available: bool = False
    source: str | None = None
    account_column: str | None = None
    label_column: str | None = None
    labels: dict[str, int] = field(default_factory=dict)
    positive_count: int = 0
    negative_count: int = 0
    unparseable: list[str] = field(default_factory=list)
    searched: list[str] = field(default_factory=list)
    rejected: list[dict] = field(default_factory=list)
    note: str = ""

    def payload(self) -> dict:
        """What the API publishes. Deliberately includes the search trail: an
        investigator should be able to see WHERE we looked before believing
        that nothing was found."""
        return {
            "available": self.available,
            "source": self.source,
            "account_column": self.account_column,
            "label_column": self.label_column,
            "labelled_accounts": len(self.labels),
            "positive_count": self.positive_count,
            "negative_count": self.negative_count,
            "unparseable_label_values": self.unparseable[:10],
            "searched_paths": self.searched,
            "rejected_candidates": self.rejected,
            "note": self.note,
        }


def _candidate_files() -> list[Path]:
    seen, out = set(), []
    for d in SEARCH_DIRS:
        if not d.exists():
            continue
        for p in sorted(d.glob("*")):
            if not p.is_file() or p.suffix.lower() not in (".csv", ".tsv", ".json", ".parquet"):
                continue
            if p.resolve() in seen:
                continue
            seen.add(p.resolve())
            if any(h in p.name.lower() for h in NAME_HINTS):
                out.append(p)
    return out


def _read_head(path: Path) -> pl.DataFrame | None:
    try:
        if path.suffix.lower() == ".parquet":
            return pl.read_parquet(path)
        if path.suffix.lower() == ".json":
            return pl.read_json(path)
        sep = "\t" if path.suffix.lower() == ".tsv" else ","
        return pl.read_csv(path, separator=sep, infer_schema_length=0)
    except Exception:
        return None


def discover() -> GroundTruth:
    """Find a label file, or state plainly that there is not one."""
    gt = GroundTruth()
    gt.searched = [str(d) for d in SEARCH_DIRS if d.exists()]

    for path in _candidate_files():
        df = _read_head(path)
        if df is None:
            gt.rejected.append({"file": path.name, "reason": "could not be parsed"})
            continue
        cols = {_norm_col(c): c for c in df.columns}
        acc_col = next((cols[c] for c in ACCOUNT_COLS if c in cols), None)
        lab_col = next((cols[c] for c in LABEL_COLS if c in cols), None)
        if acc_col is None or lab_col is None:
            gt.rejected.append({
                "file": path.name,
                "reason": "no %s column found" % ("account" if acc_col is None else "label"),
                "columns": df.columns[:12],
            })
            continue

        labels: dict[str, int] = {}
        unparseable: list[str] = []
        for a, lv in zip(df[acc_col].cast(pl.Utf8), df[lab_col].cast(pl.Utf8)):
            acct = _norm_account(a or "")
            if not acct:
                continue
            v = (lv or "").strip().lower()
            if v in TRUE_VALUES:
                labels[acct] = 1
            elif v in FALSE_VALUES:
                labels[acct] = 0
            else:
                if len(unparseable) < 50:
                    unparseable.append(lv)
        if not labels:
            gt.rejected.append({"file": path.name, "reason": "no usable label values"})
            continue

        gt.available = True
        gt.source = str(path)
        gt.account_column, gt.label_column = acc_col, lab_col
        gt.labels = labels
        gt.positive_count = sum(labels.values())
        gt.negative_count = len(labels) - gt.positive_count
        gt.unparseable = unparseable
        gt.note = ("Labels loaded from %s. Counts are read from the file, not assumed."
                   % path.name)
        return gt

    gt.note = (
        "No ground-truth file found. The problem statement's expectation of roughly "
        "1,500 mule accounts is an unverified external claim, not a label set, and is "
        "never treated as one. Accuracy, precision, recall, F1 and the confusion matrix "
        "stay unavailable until a label file exists. Drop a CSV with an account column "
        "and a label column into data/ and it will be picked up automatically."
    )
    return gt
