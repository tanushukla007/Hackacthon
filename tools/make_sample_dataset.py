#!/usr/bin/env python3
"""
Generate a SYNTHETIC development dataset with the same schema and shape as
VoidHacks8_MuleAccount_2M_Transactions.csv.

!! THIS IS NOT THE COMPETITION DATASET AND IS NOT EVIDENCE. !!
It exists so the pipeline can be built and tested before the real file is
dropped into data/raw/. Every figure the UI shows from it is synthetic.

Usage:  python3 tools/make_sample_dataset.py [rows] [out.csv]
"""
import sys
from pathlib import Path

import numpy as np
import polars as pl

ROOT = Path(__file__).resolve().parent.parent
N = int(sys.argv[1]) if len(sys.argv) > 1 else 250_000
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "data/raw/SYNTHETIC_DEV_250k.csv"
rng = np.random.default_rng(20261002)

T0 = np.datetime64("2026-09-15T00:00:00")
SPAN = 15 * 86400
BANKS = ["HDFC", "SBIN", "ICIC", "UTIB", "PUNB", "KKBK", "BARB", "CNRB", "IDIB", "YESB"]
MODES = np.array(["UPI", "IMPS", "NEFT", "RTGS"])
MODE_P = np.array([0.650, 0.221, 0.100, 0.029])
DEVS = np.array(["Windows_Browser", "iOS", "Android"])
NARR = np.array(["SALARY", "RENT", "UPI_PAYMENT", "BILL_PAY", "MERCHANT", "P2P_TRANSFER",
                 "EMI", "FEES", "REFUND", "GROCERY", "FUEL", "INSURANCE"])

# ---------------------------------------------------------------- accounts
N_NORMAL, N_L1, N_L2, N_L3 = 6000, 40, 50, 30
total_acc = N_NORMAL + N_L1 + N_L2 + N_L3
acc_nums = np.unique(rng.integers(10**11, 10**12 - 1, size=total_acc * 2))[:total_acc]
rng.shuffle(acc_nums)
accounts = np.array([str(a).zfill(12) for a in acc_nums])
accounts[0] = "000011223344"                      # leading-zero account: identity test
normal = accounts[:N_NORMAL]
l1 = accounts[N_NORMAL:N_NORMAL + N_L1]
l2 = accounts[N_NORMAL + N_L1:N_NORMAL + N_L1 + N_L2]
l3 = accounts[N_NORMAL + N_L1 + N_L2:]
ifsc_of = {a: f"{BANKS[i % len(BANKS)]}0{rng.integers(100000, 999999)}"
           for i, a in enumerate(accounts)}


def res_ip(n):
    return np.char.add(np.char.add(rng.choice(["49", "103", "117", "157", "42"], n), "."),
                       np.array([f"{a}.{b}.{c}" for a, b, c in
                                 rng.integers(0, 255, (n, 3))]))


rows = {k: [] for k in ("tid", "sa", "ra", "si", "ri", "amt", "ts", "mode", "narr", "ip", "dev")}


def emit(sa, ra, amt, ts, mode=None, narr=None, ip=None, dev=None):
    rows["sa"].append(sa); rows["ra"].append(ra)
    rows["si"].append(ifsc_of[sa]); rows["ri"].append(ifsc_of[ra])
    rows["amt"].append(round(float(amt), 2)); rows["ts"].append(int(ts))
    rows["mode"].append(mode or str(rng.choice(MODES, p=MODE_P)))
    rows["narr"].append(narr or str(rng.choice(NARR)))
    rows["ip"].append(ip); rows["dev"].append(dev)


# ------------------------------------------------------------ mule networks
N_CASES = 22
case_log = []
for c in range(N_CASES):
    collector = l1[c % N_L1]
    distributor = l2[rng.integers(0, N_L2)]
    start = int(rng.integers(0, SPAN - 40000))
    victims = rng.choice(normal, size=int(rng.integers(28, 60)), replace=False)
    total_in = 0.0
    for v in victims:                                    # fan-in, compressed window
        a = float(rng.uniform(15000, 260000))
        total_in += a
        emit(v, collector, a, start + rng.integers(0, 8600),
             mode=str(rng.choice(["IMPS", "UPI", "NEFT"], p=[.5, .35, .15])),
             narr="P2P_TRANSFER")
    fwd = total_in * rng.uniform(0.95, 0.995)            # pass-through, fast
    for k in range(int(rng.integers(2, 5))):
        emit(collector, distributor, fwd / 4 if k < 3 else fwd / 4,
             start + 9000 + rng.integers(0, 3000), mode="IMPS", narr="FUND_TRANSFER")
    n_split = int(rng.integers(18, 30))                  # fan-out, structured
    per = fwd / n_split
    sinks = list(rng.choice(l3, size=min(6, N_L3), replace=False)) + \
            list(rng.choice(normal, size=n_split - 6, replace=False))
    for j, s in enumerate(sinks[:n_split]):
        emit(distributor, s, per * rng.uniform(0.97, 1.03),
             start + 13000 + j * rng.integers(40, 180), mode="IMPS", narr="SETTLEMENT")
    for s in sinks[:6]:                                  # terminal / exit behaviour
        for _ in range(int(rng.integers(2, 5))):
            emit(s, str(rng.choice(normal)), per * rng.uniform(0.2, 0.5),
                 start + 20000 + rng.integers(0, 9000),
                 mode="UPI",
                 narr=str(rng.choice(["P2P_CRYPTO", "WALLET_TOPUP", "CASHOUT"])),
                 ip=f"{rng.choice([185, 194])}.{rng.integers(0,255)}."
                    f"{rng.integers(0,255)}.{rng.integers(0,255)}",
                 dev=str(rng.choice(["Web_Emulator", "Linux_Script"])))
    case_log.append({"victim": str(victims[0]), "collector": str(collector),
                     "distributor": str(distributor)})

# ------------------------------------------------------------- background
n_bg = max(N - len(rows["sa"]), 0)
amt = np.clip(rng.lognormal(np.log(899.35), 1.15, n_bg), 50, 499823.99)
sa = rng.choice(normal, n_bg)
ra = rng.choice(normal, n_bg)
ra = np.where(sa == ra, rng.choice(normal, n_bg), ra)
ts = rng.integers(0, SPAN, n_bg)
for i in range(n_bg):
    emit(sa[i], ra[i], amt[i], ts[i])

n = len(rows["sa"])
mode = np.array(rows["mode"])
dev = np.array([d if d else "" for d in rows["dev"]], dtype=object)
blank = dev == ""
dev[blank] = rng.choice(DEVS, blank.sum())
ip = np.array([p if p else "" for p in rows["ip"]], dtype=object)
blank_ip = ip == ""
ip[blank_ip] = res_ip(blank_ip.sum())

tids = np.array([f"TXN{i:010d}" for i in rng.permutation(n)])
dupe_idx = rng.choice(n, size=max(int(n * 0.0011), 1), replace=False)   # DC §4
tids[dupe_idx] = tids[rng.choice(n, size=len(dupe_idx))]

ts_arr = T0 + np.array(rows["ts"], dtype="timedelta64[s]")
df = pl.DataFrame({
    "Transaction_ID": tids,
    "Sender_Account": rows["sa"],
    "Receiver_Account": rows["ra"],
    "Sender_IFSC": rows["si"],
    "Receiver_IFSC": rows["ri"],
    "Amount": rows["amt"],
    "Timestamp": [str(x).replace("T", " ") for x in ts_arr],
    "Payment_Mode": mode,
    "Narration": rows["narr"],
    "IP_Address": ip.astype(str),
    "Device_Type": dev.astype(str),
}).sample(fraction=1.0, shuffle=True, seed=7)

OUT.parent.mkdir(parents=True, exist_ok=True)
df.write_csv(OUT)
print(f"wrote {OUT}  rows={df.height:,}  accounts={total_acc:,}  "
      f"median={df['Amount'].median():.2f}  size={OUT.stat().st_size/1e6:.1f} MB")
print("SYNTHETIC - not the competition dataset, not evidence.")
print("example case:", case_log[0])
