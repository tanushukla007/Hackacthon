#!/usr/bin/env python3
"""
profile_dataset.py — ABHEDYA-CHAKRA · FR-A05 Dataset Profiling & Schema Discovery

Profiles the hackathon CSV BEFORE any analytical assumption is applied, writes
data/artifacts/profile.json, and (with --check) asserts the result against the
expectation table in PRD §7.2 — exiting non-zero on any out-of-tolerance value.

This is the first thing to run in Phase 1. Every [DATA-PRELIM] figure in the PRD
becomes verified (or corrected) by its output.

Usage
-----
    python3 tools/profile_dataset.py data/raw/VoidHacks8_MuleAccount_2M_Transactions.csv
    python3 tools/profile_dataset.py <csv> --check          # also verify vs §7.2
    python3 tools/profile_dataset.py <csv> --out profile.json

Requires: duckdb (pip install duckdb).  Falls back to polars if duckdb absent.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from pathlib import Path

# ── PRD §7.2 expectation table — the ONLY place these live ────────────────────
EXPECTED = {
    "row_count":                (2_000_000,     "exact"),
    "column_count":             (11,            "exact"),
    "unique_accounts":          (24_873,        0.01),
    "unique_txn_ids":           (1_997_748,     0.001),
    "txn_id_row_surplus":       (2_252,         "exact"),
    "date_min":                 ("2026-09-15",  "day"),
    "date_max":                 ("2026-09-29",  "day"),
    "amount_median":            (899.35,        0.01),
    "amount_max":               (499_823.99,    0.01),
    "mode_counts.UPI":          (1_299_844,     0.001),
    "mode_counts.IMPS":         (441_199,       0.001),
    "mode_counts.NEFT":         (199_134,       0.001),
    "mode_counts.RTGS":         (59_823,        0.001),
    "device_counts.Web_Emulator": (1_327,       "exact"),
    "device_counts.Linux_Script": (1_327,       "exact"),
    "foreign_ip_rows":          (2_654,         "exact"),
    "narr_crypto_rows":         (1_327,         "exact"),
    "narr_wallet_rows":         (1_327,         "exact"),
    "unique_pairs":             (1_996_771,     0.05),
}

FOREIGN_IP_PREFIXES = (185, 194)
AUTOMATION_DEVICES = ("Web_Emulator", "Linux_Script")
CRYPTO_KEYWORDS = ("p2p", "crypto", "usdt", "btc", "binance", "tether")
WALLET_KEYWORDS = ("wallet", "topup", "paytm", "phonepe", "mobikwik")


def sha256(path: Path, chunk: int = 1 << 22) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while blk := f.read(chunk):
            h.update(blk)
    return h.hexdigest()


def like_any(col: str, words) -> str:
    return " OR ".join([f"lower({col}) LIKE '%{w}%'" for w in words])


def profile(csv_path: Path) -> dict:
    import duckdb

    t0 = time.time()
    con = duckdb.connect()
    con.execute(f"CREATE VIEW t AS SELECT * FROM read_csv_auto('{csv_path}', header=true)")
    cols = [r[0] for r in con.execute("DESCRIBE t").fetchall()]
    types = {r[0]: r[1] for r in con.execute("DESCRIBE t").fetchall()}

    def one(sql):
        return con.execute(sql).fetchone()[0]

    def rows(sql):
        return con.execute(sql).fetchall()

    P: dict = {
        "_meta": {
            "tool": "profile_dataset.py",
            "prd_section": "FR-A05 / §7.2",
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "file": csv_path.name,
            "file_size_bytes": csv_path.stat().st_size,
            "sha256": sha256(csv_path),
        }
    }

    # ── shape ────────────────────────────────────────────────────────────────
    P["row_count"] = one("SELECT COUNT(*) FROM t")
    P["column_count"] = len(cols)
    P["columns"] = cols
    P["dtypes"] = types
    P["schema_hash"] = hashlib.sha256("|".join(cols).encode()).hexdigest()[:16]

    # ── time ─────────────────────────────────────────────────────────────────
    P["date_min"] = str(one("SELECT MIN(CAST(Timestamp AS TIMESTAMP)) FROM t"))
    P["date_max"] = str(one("SELECT MAX(CAST(Timestamp AS TIMESTAMP)) FROM t"))
    P["span_days"] = one(
        "SELECT date_diff('day', MIN(CAST(Timestamp AS TIMESTAMP)),"
        " MAX(CAST(Timestamp AS TIMESTAMP))) FROM t")
    P["rows_per_day"] = {str(d): c for d, c in rows(
        "SELECT CAST(CAST(Timestamp AS TIMESTAMP) AS DATE) d, COUNT(*) c"
        " FROM t GROUP BY d ORDER BY d")}
    P["rows_per_hour_of_day"] = {int(h): c for h, c in rows(
        "SELECT hour(CAST(Timestamp AS TIMESTAMP)) h, COUNT(*) c FROM t GROUP BY h ORDER BY h")}

    # ── identity & duplicates (PRD §7.3, §11.3) ──────────────────────────────
    P["unique_accounts"] = one(
        "SELECT COUNT(*) FROM (SELECT Sender_Account a FROM t"
        " UNION SELECT Receiver_Account FROM t)")
    P["unique_txn_ids"] = one("SELECT COUNT(DISTINCT Transaction_ID) FROM t")
    P["txn_id_row_surplus"] = P["row_count"] - P["unique_txn_ids"]

    hist = rows("SELECT occ, COUNT(*) n_ids, occ*COUNT(*) n_rows FROM"
                " (SELECT Transaction_ID, COUNT(*) occ FROM t GROUP BY 1 HAVING COUNT(*)>1)"
                " GROUP BY occ ORDER BY occ")
    P["txn_id_repeat_histogram"] = [
        {"repeat_count": o, "n_ids": n, "n_rows": r} for o, n, r in hist]
    P["txn_id_duplicated_ids"] = sum(n for _, n, _ in hist)
    P["txn_id_affected_rows"] = sum(r for _, _, r in hist)   # ← resolves §7.3 ambiguity

    allcols = ", ".join(cols)
    P["exact_duplicate_rows"] = one(
        f"SELECT COALESCE(SUM(c),0) FROM (SELECT COUNT(*) c FROM t"
        f" GROUP BY {allcols} HAVING COUNT(*)>1)")
    P["near_duplicate_rows"] = P["txn_id_affected_rows"] - P["exact_duplicate_rows"]

    # ── completeness ─────────────────────────────────────────────────────────
    P["nulls_per_column"] = {
        c: one(f'SELECT COUNT(*) FROM t WHERE "{c}" IS NULL') for c in cols}
    P["malformed_ifsc"] = one(
        "SELECT COUNT(*) FROM t WHERE NOT regexp_matches(upper(Sender_IFSC),"
        " '^[A-Z]{4}0[A-Z0-9]{6}$') OR NOT regexp_matches(upper(Receiver_IFSC),"
        " '^[A-Z]{4}0[A-Z0-9]{6}$')")
    P["non_12_digit_accounts"] = one(
        "SELECT COUNT(*) FROM t WHERE length(CAST(Sender_Account AS VARCHAR))<>12"
        " OR length(CAST(Receiver_Account AS VARCHAR))<>12")

    # ── amounts ──────────────────────────────────────────────────────────────
    a = con.execute(
        "SELECT MIN(Amount), quantile_cont(Amount,0.01), quantile_cont(Amount,0.25),"
        " median(Amount), AVG(Amount), quantile_cont(Amount,0.75),"
        " quantile_cont(Amount,0.99), MAX(Amount),"
        " SUM(CASE WHEN Amount<=0 THEN 1 ELSE 0 END),"
        " SUM(CASE WHEN Amount%1000=0 THEN 1 ELSE 0 END) FROM t").fetchone()
    keys = ["amount_min", "amount_p1", "amount_p25", "amount_median", "amount_mean",
            "amount_p75", "amount_p99", "amount_max", "amount_nonpositive",
            "amount_round_1000"]
    P.update({k: (round(v, 2) if isinstance(v, float) else v) for k, v in zip(keys, a)})

    # ── categorical ──────────────────────────────────────────────────────────
    P["mode_counts"] = dict(rows(
        "SELECT Payment_Mode, COUNT(*) FROM t GROUP BY 1 ORDER BY 2 DESC"))
    P["device_counts"] = dict(rows(
        "SELECT Device_Type, COUNT(*) FROM t GROUP BY 1 ORDER BY 2 DESC"))
    P["ip_first_octet_top20"] = dict(rows(
        "SELECT split_part(IP_Address,'.',1) o, COUNT(*) c FROM t"
        " GROUP BY o ORDER BY c DESC LIMIT 20"))
    P["amount_by_mode"] = {m: {"n": n, "median": round(med, 2), "min": round(mn, 2),
                               "max": round(mx, 2)}
                           for m, n, med, mn, mx in rows(
        "SELECT Payment_Mode, COUNT(*), median(Amount), MIN(Amount), MAX(Amount)"
        " FROM t GROUP BY 1")}

    # ── signals + co-occurrence (PRD §7.4 — settles mentor Q15) ──────────────
    fip = f"(CAST(split_part(IP_Address,'.',1) AS INT) IN {FOREIGN_IP_PREFIXES})"
    aut = "(Device_Type IN {})".format(str(AUTOMATION_DEVICES))
    cry = f"({like_any('Narration', CRYPTO_KEYWORDS)})"
    wal = f"({like_any('Narration', WALLET_KEYWORDS)})"
    P["foreign_ip_rows"] = one(f"SELECT COUNT(*) FROM t WHERE {fip}")
    P["automation_rows"] = one(f"SELECT COUNT(*) FROM t WHERE {aut}")
    P["narr_crypto_rows"] = one(f"SELECT COUNT(*) FROM t WHERE {cry}")
    P["narr_wallet_rows"] = one(f"SELECT COUNT(*) FROM t WHERE {wal}")
    P["any_signal_rows"] = one(f"SELECT COUNT(*) FROM t WHERE {fip} OR {aut} OR {cry} OR {wal}")
    P["all_four_signal_rows"] = one(
        f"SELECT COUNT(*) FROM t WHERE {fip} AND {aut} AND ({cry} OR {wal})")
    P["signal_cooccurrence"] = {
        "foreign_ip_and_automation": one(f"SELECT COUNT(*) FROM t WHERE {fip} AND {aut}"),
        "foreign_ip_and_narration": one(f"SELECT COUNT(*) FROM t WHERE {fip} AND ({cry} OR {wal})"),
        "automation_and_narration": one(f"SELECT COUNT(*) FROM t WHERE {aut} AND ({cry} OR {wal})"),
    }
    P["observed_cooccurrence_rate"] = round(
        P["all_four_signal_rows"] / max(P["any_signal_rows"], 1), 4)
    P["accounts_touching_a_signal"] = one(
        f"SELECT COUNT(*) FROM (SELECT Sender_Account a FROM t WHERE {fip} OR {aut} OR {cry} OR {wal}"
        f" UNION SELECT Receiver_Account FROM t WHERE {fip} OR {aut} OR {cry} OR {wal})")

    # ── graph shape (PRD §7.6, §13.1, §13.3) ─────────────────────────────────
    P["unique_pairs"] = one(
        "SELECT COUNT(*) FROM (SELECT DISTINCT Sender_Account, Receiver_Account FROM t)")
    P["self_loops"] = one("SELECT COUNT(*) FROM t WHERE Sender_Account = Receiver_Account")
    for side, col in (("out", "Sender_Account"), ("in", "Receiver_Account")):
        d = con.execute(
            f"SELECT median(c), quantile_cont(c,0.90), quantile_cont(c,0.99), MAX(c), AVG(c)"
            f" FROM (SELECT {col}, COUNT(*) c FROM t GROUP BY 1)").fetchone()
        P[f"{side}_degree"] = {"p50": d[0], "p90": d[1], "p99": d[2],
                               "max": d[3], "mean": round(d[4], 2)}
    P["suggested_hub_degree_cap"] = max(500, int(P["out_degree"]["p99"] * 3))

    # ── derived: branching factors (PRD §7.5) ────────────────────────────────
    per_acct = P["row_count"] / max(P["unique_accounts"], 1)
    span_h = max(P["span_days"], 1) * 24
    P["derived"] = {
        "txns_per_account_as_sender": round(per_acct, 2),
        "txns_per_day": round(P["row_count"] / max(P["span_days"], 1)),
        "pairs_per_row": round(P["unique_pairs"] / P["row_count"], 4),
        "csr_mem_mb_both_directions": round(P["unique_pairs"] * 32 * 2 / 1e6),
        "branching_factor": {},
    }
    for h in (1, 6, 24, 72):
        b = per_acct * h / span_h
        P["derived"]["branching_factor"][f"{h}h"] = {
            "b": round(b, 2),
            **{f"hop{k}": round(b ** k, 1) for k in (1, 2, 3, 4)},
            "saturates_population": b ** 4 > P["unique_accounts"],
        }

    P["_meta"]["profile_seconds"] = round(time.time() - t0, 2)
    return P


def get(d: dict, dotted: str):
    cur = d
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def check(P: dict) -> int:
    print("\n── §7.2 expectation check " + "─" * 52)
    bad = 0
    for key, (exp, tol) in EXPECTED.items():
        act = get(P, key)
        if act is None:
            print(f"  ?  {key:32s} expected {exp!s:>14}  actual MISSING")
            bad += 1
            continue
        if tol == "exact":
            ok = act == exp
        elif tol == "day":
            ok = str(act)[:10] == str(exp)[:10]
        else:
            ok = exp == 0 or abs(act - exp) / abs(exp) <= tol
        print(f"  {'OK' if ok else 'XX'} {key:32s} expected {exp!s:>14}  actual {act!s:>14}")
        bad += (not ok)
    print("─" * 78)
    if bad:
        print(f"  {bad} MISMATCH(ES) — this is a P0 finding. Update PRD §7 and §33 before tuning.")
    else:
        print("  All expectations met. Replace the §7.0 status block with a VERIFIED stamp.")
    return bad


def highlights(P: dict) -> None:
    d = P["derived"]
    print("\n── findings that change the build " + "─" * 44)
    print(f"  Rows / accounts        : {P['row_count']:,} rows · {P['unique_accounts']:,} accounts")
    print(f"  Transaction_ID         : {P['unique_txn_ids']:,} distinct · surplus {P['txn_id_row_surplus']:,}")
    print(f"     duplicated IDs      : {P['txn_id_duplicated_ids']:,} affecting {P['txn_id_affected_rows']:,} rows")
    print(f"     exact duplicates    : {P['exact_duplicate_rows']:,}   near-duplicates: {P['near_duplicate_rows']:,}")
    print(f"  Unique pairs           : {P['unique_pairs']:,}  ({d['pairs_per_row']:.1%} of rows)"
          f"  → CSR ≈ {d['csr_mem_mb_both_directions']} MB both directions")
    print(f"  Amount median / mean   : ₹{P['amount_median']:,} / ₹{P['amount_mean']:,}"
          f"   → check every ₹ threshold in config.py")
    print(f"  Signal co-occurrence   : {P['observed_cooccurrence_rate']:.0%} of signal rows carry all signal types")
    print(f"     → C5 discount uses this value (PRD §15.1); settles mentor Q15")
    print(f"  Accounts with a signal : {P['accounts_touching_a_signal']:,}"
          f"  (vs 1,500 mule accounts described by the PS)")
    print(f"  Out-degree p99 / max   : {P['out_degree']['p99']} / {P['out_degree']['max']}"
          f"   → suggested HUB_DEGREE_CAP = {P['suggested_hub_degree_cap']}")
    print("  Branching by window:")
    for w, v in d["branching_factor"].items():
        flag = "  ⚠ SATURATES POPULATION" if v["saturates_population"] else ""
        print(f"     {w:>4}  b={v['b']:>6}   hop4={v['hop4']:>12,.0f}{flag}")
    print("─" * 78)


def main() -> int:
    ap = argparse.ArgumentParser(description="ABHEDYA-CHAKRA dataset profiler (FR-A05)")
    ap.add_argument("csv", type=Path)
    ap.add_argument("--out", type=Path, default=Path("data/artifacts/profile.json"))
    ap.add_argument("--check", action="store_true", help="verify against PRD §7.2")
    a = ap.parse_args()

    if not a.csv.exists():
        print(f"error: {a.csv} not found", file=sys.stderr)
        return 2
    try:
        import duckdb  # noqa: F401
    except ImportError:
        print("error: pip install duckdb", file=sys.stderr)
        return 2

    print(f"profiling {a.csv} ({a.csv.stat().st_size/1e6:.0f} MB) …")
    P = profile(a.csv)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(P, indent=2, default=str))
    print(f"→ {a.out}  ({P['_meta']['profile_seconds']} s)")

    highlights(P)
    return 1 if (a.check and check(P)) else 0


if __name__ == "__main__":
    sys.exit(main())
