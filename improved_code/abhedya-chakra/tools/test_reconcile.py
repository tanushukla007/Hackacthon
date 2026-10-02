#!/usr/bin/env python3
"""
Does the reconciliation report actually detect the mechanisms it names?

Builds a tiny CSV in which every mechanism is present by construction, with a
known count, then asserts the report recovers each one. Without this, a report
of "0 normalization_collisions" is indistinguishable from a detector that
cannot find collisions at all.

Usage: python3 tools/test_reconcile.py
"""
import csv
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

WORK = ROOT / "data" / "_recon_test"
PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))


COLS = ["Transaction_ID", "Sender_Account", "Receiver_Account", "Sender_IFSC",
        "Receiver_IFSC", "Amount", "Timestamp", "Payment_Mode", "Narration",
        "IP_Address", "Device_Type"]


def row(i, s, r):
    return [f"TXN{i:05d}", s, r, "HDFC0000111", "ICIC0000222", "1000.00",
            "2026-09-15 10:%02d:00" % (i % 60), "UPI", "payment", "10.0.0.1", "iOS"]


def main():
    if WORK.exists():
        shutil.rmtree(WORK)
    WORK.mkdir(parents=True)
    csv_path = WORK / "mini.csv"

    rows = []
    # 3 accounts that both send and receive
    core = ["100000000001", "100000000002", "100000000003"]
    rows += [row(1, core[0], core[1]), row(2, core[1], core[2]), row(3, core[2], core[0])]
    # 1 sender-only, 1 receiver-only
    rows.append(row(4, "200000000001", core[0]))          # sender only
    rows.append(row(5, core[0], "300000000001"))          # receiver only
    # a normalisation collision: two raw forms of the SAME account
    rows.append(row(6, "400-0000-00001", core[1]))
    rows.append(row(7, "4000 0000 0001", core[1]))
    # a short account that zero-pads up to 12 digits
    rows.append(row(8, "55501", core[2]))

    with open(csv_path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(COLS)
        w.writerows(rows)

    # a label file that includes one account which never transacts
    gt_path = WORK / "ground_truth_labels.csv"
    with open(gt_path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["account_id", "is_mule"])
        w.writerow([core[0], 1])
        w.writerow(["999000000001", 1])        # never appears in a transaction
        w.writerow([core[1], 0])

    # Point discovery at the test directory.
    from app.core import ground_truth as gtm
    from app.core import reconcile
    gtm.SEARCH_DIRS = (WORK,)

    print("ground truth discovery")
    gt = gtm.discover()
    check("a labelled file is discovered", gt.available, gt.note[:60])
    check("the account column is identified", gt.account_column == "account_id")
    check("the label column is identified", gt.label_column == "is_mule")
    check("positives are counted from the file, not assumed",
          gt.positive_count == 2, f"got {gt.positive_count}")
    check("negatives are counted", gt.negative_count == 1, f"got {gt.negative_count}")

    print("\nreconciliation")
    rep = reconcile.build(csv_path, expected_total=9)
    # Observed distinct accounts: core(3) + sender-only + receiver-only
    #                             + collided(1) + padded short(1) = 7
    check("observed accounts counted", rep["observed_accounts"] == 7,
          f"got {rep['observed_accounts']}")
    # Three: 200000000001, the collided 400000000001, and the zero-padded 000000055501.
    check("sender-only accounts found", rep["sender_only"] == 3,
          f"got {rep['sender_only']}")
    check("receiver-only accounts found", rep["receiver_only"] == 1,
          f"got {rep['receiver_only']}")
    check("both-sided accounts found", rep["both_sides"] == 3,
          f"got {rep['both_sides']}")
    check("a normalisation collision is detected",
          rep["normalization_collisions"] == 1, f"got {rep['normalization_collisions']}")
    check("the collision is quantified as lost identities",
          rep["accounts_lost_to_normalisation"] == 1,
          f"got {rep['accounts_lost_to_normalisation']}")
    check("the colliding raw forms are shown",
          any(len(e["raw_forms"]) >= 2 for e in rep["collision_examples"]))
    check("short account numbers are reported, not hidden",
          rep["malformed_account_numbers"]["not_12_digits_after_stripping"] >= 1)
    check("a labelled account that never transacts is found",
          rep["accounts_in_ground_truth_only"] == 1,
          f"got {rep['accounts_in_ground_truth_only']}")
    check("the residual is arithmetic, not narrative",
          rep["difference"] == 2 and
          rep["unexplained_residual"] == 2 - rep["explained_by"]["accounts_lost_to_normalisation"]
          - rep["explained_by"]["accounts_in_ground_truth_only"],
          f"difference={rep['difference']} explained={rep['explained_by']} "
          f"residual={rep['unexplained_residual']}")

    print("\nno-ground-truth behaviour")
    gt_path.unlink()
    gtm.SEARCH_DIRS = (WORK,)
    gt2 = gtm.discover()
    check("absence of labels is reported as absence", not gt2.available)
    check("the absence note refuses to treat ~1,500 as a label set",
          "unverified" in gt2.note)
    rep2 = reconcile.build(csv_path)
    check("with no reference universe, nothing is called an error",
          rep2["expected_accounts"] is None and "not an error" in rep2["verdict"])

    shutil.rmtree(WORK)
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
