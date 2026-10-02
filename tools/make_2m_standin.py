#!/usr/bin/env python3
"""
Generate a 2,000,000-row STAND-IN for the competition dataset.

!! THIS IS NOT THE COMPETITION DATASET. IT IS NOT EVIDENCE. !!

It exists for one honest purpose: to measure ingestion and query performance at
the real row count, because the real file is not in this workspace. Detection
quality measured on it describes this generator, not reality.

Two outputs:
  out/STANDIN_2M.csv                  same schema as the real file
                                      (out/ is snapshot-excluded; this file is
                                      regenerable and must never be committed)
  data/synthetic_eval/planted_labels.csv
      the accounts this generator deliberately gave mule-like behaviour

The label file is written OUTSIDE every directory that ground_truth.discover()
searches, so it can never be mistaken by the running system for real ground
truth. Point the evaluator at it explicitly to exercise the metric path.

Memory: written in chunks, vectorised with NumPy, so peak stays well under the
sandbox ceiling.

Usage: python3 tools/make_2m_standin.py [rows] [accounts]
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import polars as pl

ROOT = Path(__file__).resolve().parent.parent
N_ROWS = int(sys.argv[1]) if len(sys.argv) > 1 else 2_000_000
N_ACCOUNTS = int(sys.argv[2]) if len(sys.argv) > 2 else 25_000
# Written to out/, NOT data/raw/, for two reasons:
#   1. out/ is excluded from workspace snapshots, so a quarter-gigabyte of
#      regenerable synthetic data never counts against the storage budget.
#   2. data/raw/ is what the server autoloads from; a 2M synthetic stand-in
#      sitting there is a trap waiting to run the demo on the wrong dataset.
# Override with: python3 tools/make_2m_standin.py <rows> <accounts> <path>
OUT = Path(sys.argv[3]) if len(sys.argv) > 3 else ROOT / "out" / "STANDIN_2M.csv"
LABELS = ROOT / "data" / "synthetic_eval" / "planted_labels.csv"
CHUNK = 250_000

rng = np.random.default_rng(20261002)

T0 = 1789430400                     # 2026-09-15 00:00:00 UTC
SPAN = 15 * 86400                   # 15 days, matching the stated window
BANKS = np.array(["HDFC", "SBIN", "ICIC", "UTIB", "PUNB", "KKBK", "BARB", "CNRB",
                  "IDIB", "YESB"])
MODES = np.array(["UPI", "IMPS", "NEFT", "RTGS"])
MODE_P = np.array([0.650, 0.221, 0.100, 0.029])
DEVS = np.array(["Windows_Browser", "iOS", "Android"])
SUSPECT_DEVS = np.array(["Web_Emulator", "Linux_Script"])
NARR = np.array(["SALARY", "RENT", "UPI_PAYMENT", "BILL_PAY", "MERCHANT",
                 "P2P_TRANSFER", "EMI", "FEES", "REFUND", "GROCERY", "FUEL"])
SUSPECT_NARR = np.array(["P2P_CRYPTO", "WALLET_LOAD", "WALLET_TOPUP", "CASHOUT"])

# ---------------------------------------------------------------- accounts
nums = np.unique(rng.integers(10 ** 11, 10 ** 12 - 1, size=int(N_ACCOUNTS * 1.3)))
rng.shuffle(nums)
nums = nums[:N_ACCOUNTS]
ACC = np.array([str(a).zfill(12) for a in nums])
IFSC = np.array([BANKS[i] + "0" + str(rng.integers(100000, 999999))
                 for i in rng.integers(0, len(BANKS), size=N_ACCOUNTS)])

# Role allocation. Roughly 6% of the universe is given mule-like behaviour,
# which is the proportion the problem statement implies (~1,500 of ~25,000).
n_mule = max(1, int(round(N_ACCOUNTS * 0.06)))
idx = np.arange(N_ACCOUNTS)
rng.shuffle(idx)
collectors = idx[:n_mule // 3]
distributors = idx[n_mule // 3: 2 * (n_mule // 3)]
passthru = idx[2 * (n_mule // 3): n_mule]
mules = np.concatenate([collectors, distributors, passthru])
normals = idx[n_mule:]
# A legitimate high-degree hub population: high volume, slow, NOT mules. They
# exist so the hub guard has something to be wrong about.
hubs = normals[:max(1, N_ACCOUNTS // 500)]

print(f"accounts {N_ACCOUNTS:,} · collectors {len(collectors):,} "
      f"distributors {len(distributors):,} pass-through {len(passthru):,} "
      f"legit hubs {len(hubs):,}")


def _ips(n: int, suspicious: np.ndarray) -> np.ndarray:
    a = np.where(suspicious,
                 rng.choice(np.array([185, 194]), size=n),
                 rng.integers(1, 180, size=n))
    return np.char.add(np.char.add(a.astype(str), "."),
                       np.char.add(np.char.add(rng.integers(0, 256, n).astype(str), "."),
                                   np.char.add(rng.integers(0, 256, n).astype(str) + ".",
                                               rng.integers(1, 255, n).astype(str))))


def chunk_rows(k: int, start_row: int) -> pl.DataFrame:
    """One chunk of transactions: background flow plus planted structure."""
    lo = T0 + int(SPAN * k / (N_ROWS / CHUNK))
    hi = T0 + int(SPAN * (k + 1) / (N_ROWS / CHUNK))

    n_struct = int(CHUNK * 0.12)
    n_back = CHUNK - n_struct

    # ---- background: ordinary accounts paying ordinary accounts ----------
    s_b = rng.choice(normals, size=n_back)
    r_b = rng.choice(normals, size=n_back)
    # a slice of background routed through legitimate hubs (high degree, slow)
    hub_n = n_back // 12
    s_b[:hub_n] = rng.choice(hubs, size=hub_n)
    r_b[hub_n:2 * hub_n] = rng.choice(hubs, size=hub_n)
    t_b = rng.integers(lo, hi, size=n_back)
    a_b = np.round(rng.lognormal(6.6, 1.05, size=n_back), 2)

    # ---- structured: collection, dispersal, fast pass-through ------------
    third = n_struct // 3
    # collectors: many distinct senders -> one collector, tight window
    c_dst = rng.choice(collectors, size=third)
    c_src = rng.choice(normals, size=third)
    c_t = rng.integers(lo, hi, size=third)
    c_a = np.round(rng.lognormal(10.1, 0.5, size=third), 2)
    # distributors: one distributor -> many receivers, minutes later
    d_src = rng.choice(distributors, size=third)
    d_dst = rng.choice(normals, size=third)
    d_t = rng.integers(lo, hi, size=third)
    d_a = np.round(rng.lognormal(9.4, 0.45, size=third), 2)
    # pass-through: in then out within minutes, nearly the same value
    p_n = n_struct - 2 * third
    p_mid = rng.choice(passthru, size=p_n)
    p_in_src = rng.choice(normals, size=p_n)
    p_out_dst = rng.choice(np.concatenate([distributors, normals[:500]]), size=p_n)
    p_t = rng.integers(lo, max(lo + 1, hi - 900), size=p_n)
    p_a = np.round(rng.lognormal(10.0, 0.4, size=p_n), 2)

    src = np.concatenate([s_b, c_src, d_src, p_in_src, p_mid])
    dst = np.concatenate([r_b, c_dst, d_dst, p_mid, p_out_dst])
    ts = np.concatenate([t_b, c_t, d_t, p_t, p_t + rng.integers(40, 850, size=p_n)])
    amt = np.concatenate([a_b, c_a, d_a, p_a, np.round(p_a * rng.uniform(0.9, 0.99, p_n), 2)])

    n = len(src)
    # terminal indicators: concentrated on the dispersal side, never universal
    susp = np.zeros(n, dtype=bool)
    tail = np.isin(src, distributors) | np.isin(src, passthru)
    susp[tail] = rng.random(int(tail.sum())) < 0.22

    dev = np.where(susp & (rng.random(n) < 0.6),
                   rng.choice(SUSPECT_DEVS, size=n), rng.choice(DEVS, size=n))
    narr = np.where(susp & (rng.random(n) < 0.7),
                    rng.choice(SUSPECT_NARR, size=n), rng.choice(NARR, size=n))
    mode = rng.choice(MODES, size=n, p=MODE_P)

    tid = np.char.add("TXN", (np.arange(start_row, start_row + n)).astype(str))
    # duplicate Transaction_IDs: a fixed small number per chunk, never removed
    dups = max(1, int(2250 / (N_ROWS / CHUNK)))
    dpos = rng.choice(n, size=dups * 2, replace=False)
    tid[dpos[dups:]] = tid[dpos[:dups]]

    ts_str = (np.datetime64("1970-01-01T00:00:00") +
              ts.astype("timedelta64[s]")).astype("datetime64[s]").astype(str)
    ts_str = np.char.replace(ts_str, "T", " ")

    return pl.DataFrame({
        "Transaction_ID": tid,
        "Sender_Account": ACC[src],
        "Receiver_Account": ACC[dst],
        "Sender_IFSC": IFSC[src],
        "Receiver_IFSC": IFSC[dst],
        "Amount": amt,
        "Timestamp": ts_str,
        "Payment_Mode": mode,
        "Narration": narr,
        "IP_Address": _ips(n, susp),
        "Device_Type": dev,
    })


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    LABELS.parent.mkdir(parents=True, exist_ok=True)
    if OUT.exists():
        OUT.unlink()

    written = 0
    n_chunks = int(np.ceil(N_ROWS / CHUNK))
    for k in range(n_chunks):
        df = chunk_rows(k, written)
        with open(OUT, "ab" if k else "wb") as fh:
            df.write_csv(fh, include_header=(k == 0))
        written += df.height
        print(f"  chunk {k + 1}/{n_chunks}  rows {written:,}", flush=True)

    # The planted positives, written where discovery will NOT find them.
    lab = pl.DataFrame({
        "account_id": ACC[np.concatenate([mules, normals])],
        "is_mule": np.concatenate([np.ones(len(mules), dtype=np.int8),
                                   np.zeros(len(normals), dtype=np.int8)]),
    })
    lab.write_csv(LABELS)

    size_mb = OUT.stat().st_size / 1e6
    print(f"\n{OUT}  {written:,} rows  {size_mb:.0f} MB")
    print(f"{LABELS}  {len(mules):,} planted positives / {len(normals):,} negatives")
    print("\nTHIS IS SYNTHETIC. Performance measured on it is real; detection "
          "quality measured on it describes the generator, not the world.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
