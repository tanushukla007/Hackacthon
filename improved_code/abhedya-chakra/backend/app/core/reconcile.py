"""
Account reconciliation: why does the file contain N accounts and not the N we
were told to expect?

The brief's question is 24,873 observed against an expected ~25,000. This
module does not answer it with a theory. It measures every mechanism that
could produce a difference and reports each one with a number:

  - accounts that only ever send
  - accounts that only ever receive
  - accounts on both sides
  - accounts whose identity CHANGED under normalisation (collisions)
  - accounts present in a label file but never seen in a transaction
  - accounts seen in transactions but absent from a label file

If the counts reconcile, the report says so. If they do not, the residual is
printed as a residual rather than explained away.
"""
from __future__ import annotations

import re
from pathlib import Path

import polars as pl

from ..config import ACCOUNT_WIDTH
from . import ground_truth as gt_mod

_NON_DIGIT = re.compile(r"\D")


def _norm_expr(col: str) -> pl.Expr:
    """Exactly the normalisation ingest performs (ingest.py: acct())."""
    return (pl.col(col).str.strip_chars().str.replace_all(r"\D", "")
            .str.pad_start(ACCOUNT_WIDTH, "0"))


def build(src: Path, expected_total: int | None = None) -> dict:
    """Scan the two account columns of the source CSV and reconcile.

    Reads only the columns it needs, so this stays cheap even at 2M rows.
    """
    lf = pl.scan_csv(src, infer_schema_length=0, low_memory=True).select(
        pl.col("Sender_Account").alias("raw_s"),
        pl.col("Receiver_Account").alias("raw_r"),
    ).with_columns(
        _norm_expr("raw_s").alias("norm_s"),
        _norm_expr("raw_r").alias("norm_r"),
    )
    df = lf.collect(engine="streaming")

    senders = df["norm_s"].unique()
    receivers = df["norm_r"].unique()
    s_set, r_set = set(senders.to_list()), set(receivers.to_list())
    observed = s_set | r_set

    # --- normalisation collisions ------------------------------------------
    # Two different raw strings that become the same account after stripping
    # non-digits and zero-padding. These REDUCE the unique-account count, so
    # they are a candidate explanation for an observed count below expectation.
    pairs = pl.concat([
        df.select(pl.col("raw_s").alias("raw"), pl.col("norm_s").alias("norm")),
        df.select(pl.col("raw_r").alias("raw"), pl.col("norm_r").alias("norm")),
    ]).unique()
    collided = (pairs.group_by("norm").agg(pl.col("raw").n_unique().alias("raw_forms"))
                .filter(pl.col("raw_forms") > 1).sort("raw_forms", descending=True))
    examples = []
    for row in collided.head(10).iter_rows(named=True):
        forms = (pairs.filter(pl.col("norm") == row["norm"])["raw"].unique()
                 .to_list()[:4])
        examples.append({"normalised": row["norm"], "raw_forms": forms})

    # Raw identities that were distinct before normalisation.
    raw_identities = int(pairs["raw"].n_unique())
    collapsed = raw_identities - len(observed)

    # --- shape of the account universe -------------------------------------
    sender_only = s_set - r_set
    receiver_only = r_set - s_set
    both = s_set & r_set

    # --- malformed account numbers -----------------------------------------
    # Not an error on its own: it is a fact about the file that changes how the
    # count should be read.
    all_raw = pairs["raw"].to_list()
    non_12_digit, non_numeric = 0, 0
    for raw in all_raw:
        digits = _NON_DIGIT.sub("", (raw or "").strip())
        if not digits:
            non_numeric += 1
        elif len(digits) != ACCOUNT_WIDTH:
            non_12_digit += 1

    # --- ground truth -------------------------------------------------------
    gt = gt_mod.discover()
    gt_accounts = set(gt.labels) if gt.available else set()
    in_gt_only = gt_accounts - observed
    in_txn_only = observed - gt_accounts if gt.available else set()

    report = {
        "observed_accounts": len(observed),
        "sender_accounts": len(s_set),
        "receiver_accounts": len(r_set),
        "sender_only": len(sender_only),
        "receiver_only": len(receiver_only),
        "both_sides": len(both),

        "raw_identities_before_normalisation": raw_identities,
        "normalization_collisions": int(collided.height),
        "accounts_lost_to_normalisation": int(collapsed),
        "collision_examples": examples,
        "malformed_account_numbers": {
            "not_12_digits_after_stripping": non_12_digit,
            "no_digits_at_all": non_numeric,
            "note": ("Counted on raw values. Ingest zero-pads to %d characters and never "
                     "drops a row, so these still appear as accounts." % ACCOUNT_WIDTH),
        },

        "ground_truth_available": gt.available,
        "ground_truth_accounts": len(gt_accounts) if gt.available else None,
        "accounts_in_ground_truth_only": len(in_gt_only) if gt.available else None,
        "accounts_in_transactions_only": len(in_txn_only) if gt.available else None,
        "missing_from_transactions": sorted(in_gt_only)[:25] if gt.available else [],
    }

    # --- reconciliation against a claimed universe --------------------------
    if expected_total:
        residual = expected_total - len(observed)
        report["expected_accounts"] = expected_total
        report["difference"] = residual
        report["expected_source"] = "caller-supplied"
        explained = {
            "accounts_lost_to_normalisation": int(collapsed),
            "accounts_in_ground_truth_only": len(in_gt_only) if gt.available else 0,
        }
        report["explained_by"] = explained
        report["unexplained_residual"] = residual - sum(explained.values())
        report["verdict"] = (
            "reconciled" if report["unexplained_residual"] == 0
            else "partially explained; residual stated rather than attributed")
    else:
        report["expected_accounts"] = None
        report["difference"] = None
        report["verdict"] = (
            "No verified account universe exists in the workspace, so there is nothing "
            "to reconcile against. %d is the number of distinct accounts that appear in "
            "a transaction; it is reported as exactly that and is not an error. A "
            "problem statement saying 'approximately 25,000 accounts' is an expectation, "
            "not a reference file." % len(observed)
        )
    return report
