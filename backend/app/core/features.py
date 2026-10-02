"""
Per-account feature rows (DATA_CONTEXT.md §19).

MEASUREMENTS ONLY. No score, no role, no layer, no verdict lives here.
Every field must be reproducible by a SQL query over the fact table.
"""
from __future__ import annotations

import numpy as np
import polars as pl

from ..config import FORWARD_RATIO_CLIP, PRIMARY_VELOCITY_WINDOW, VELOCITY_WINDOWS


def _peak_window(ts_sorted: np.ndarray, window: int) -> tuple[int, int]:
    """Max events inside any rolling `window`, and the start ts of that window."""
    if ts_sorted.size == 0:
        return 0, 0
    j = np.searchsorted(ts_sorted, ts_sorted + window, side="right")
    counts = j - np.arange(ts_sorted.size)
    k = int(np.argmax(counts))
    return int(counts[k]), int(ts_sorted[k])


def _fifo_hold(in_ts: np.ndarray, in_amt: np.ndarray,
               out_ts: np.ndarray, out_amt: np.ndarray) -> tuple[float | None, float | None, float]:
    """
    FIFO attribution respecting temporal causality: an outflow may only consume
    inflows that are STRICTLY EARLIER. Returns (median_hold, min_hold, unattributed_out).
    Hold is None - never 0 - when nothing could be matched.
    """
    holds: list[float] = []
    weights: list[float] = []
    i, n_in = 0, in_ts.size
    pending_amt = in_amt.copy()
    unattributed = 0.0
    for o in range(out_ts.size):
        need = float(out_amt[o])
        t_out = out_ts[o]
        while need > 1e-9:
            while i < n_in and (pending_amt[i] <= 1e-9 or in_ts[i] >= t_out):
                if in_ts[i] >= t_out:
                    break
                i += 1
            if i >= n_in or in_ts[i] >= t_out:
                unattributed += need
                break
            take = min(need, float(pending_amt[i]))
            pending_amt[i] -= take
            need -= take
            holds.append(float(t_out - in_ts[i]))
            weights.append(take)
    if not holds:
        return None, None, unattributed
    h = np.array(holds)
    return float(np.median(h)), float(h.min()), unattributed


def build_features(df: pl.DataFrame, n_accounts: int) -> dict[str, np.ndarray]:
    """Vectorised aggregates + per-account temporal passes."""
    src = df["src_idx"].to_numpy()
    dst = df["dst_idx"].to_numpy()
    amt = df["amount_f"].to_numpy()
    ts = df["ts_epoch"].to_numpy()

    f: dict[str, np.ndarray] = {}
    z = lambda dt=np.float64: np.zeros(n_accounts, dtype=dt)   # noqa: E731

    f["out_txn_count"] = np.bincount(src, minlength=n_accounts).astype(np.int32)
    f["in_txn_count"] = np.bincount(dst, minlength=n_accounts).astype(np.int32)
    f["total_out_amount"] = np.bincount(src, weights=amt, minlength=n_accounts)
    f["total_in_amount"] = np.bincount(dst, weights=amt, minlength=n_accounts)
    f["net_balance"] = f["total_in_amount"] - f["total_out_amount"]

    deg = (df.lazy().group_by("src_idx").agg(pl.col("dst_idx").n_unique().alias("d"))
             .collect())
    f["out_degree"] = z(np.int32)
    f["out_degree"][deg["src_idx"].to_numpy()] = deg["d"].to_numpy()
    deg = (df.lazy().group_by("dst_idx").agg(pl.col("src_idx").n_unique().alias("d"))
             .collect())
    f["in_degree"] = z(np.int32)
    f["in_degree"][deg["dst_idx"].to_numpy()] = deg["d"].to_numpy()

    for name, keycol in (("sender_bank", "src_idx"), ("receiver_bank", "dst_idx")):
        b = (df.lazy().group_by(keycol).agg(pl.col(name).n_unique().alias("b")).collect())
        arr = z(np.int32)
        arr[b[keycol].to_numpy()] = b["b"].to_numpy()
        f["unique_" + name + "s"] = arr

    for sig in ("is_foreign_ip", "is_automation_device", "narr_crypto",
                "narr_wallet", "narr_cashout"):
        v = df[sig].to_numpy().astype(np.float64)
        f[sig + "_txns"] = (np.bincount(src, weights=v, minlength=n_accounts)
                            + np.bincount(dst, weights=v, minlength=n_accounts)).astype(np.int32)
    fam_net = (f["is_foreign_ip_txns"] > 0).astype(np.int8)
    fam_dev = (f["is_automation_device_txns"] > 0).astype(np.int8)
    fam_nar = ((f["narr_crypto_txns"] + f["narr_wallet_txns"] + f["narr_cashout_txns"]) > 0).astype(np.int8)
    f["distinct_signal_families"] = (fam_net + fam_dev + fam_nar).astype(np.int8)
    f["signal_txns"] = (f["is_foreign_ip_txns"] + f["is_automation_device_txns"]
                        + f["narr_crypto_txns"] + f["narr_wallet_txns"]
                        + f["narr_cashout_txns"]).astype(np.int32)

    # ---- temporal passes, grouped by account ---------------------------------
    out_order = np.argsort(src, kind="stable")
    in_order = np.argsort(dst, kind="stable")
    out_ptr = np.zeros(n_accounts + 1, dtype=np.int64)
    np.cumsum(np.bincount(src, minlength=n_accounts), out=out_ptr[1:])
    in_ptr = np.zeros(n_accounts + 1, dtype=np.int64)
    np.cumsum(np.bincount(dst, minlength=n_accounts), out=in_ptr[1:])

    for w in VELOCITY_WINDOWS:
        f[f"peak_in_count_{w}"] = z(np.int32)
        f[f"peak_out_count_{w}"] = z(np.int32)
    f["peak_in_window_start"] = z(np.int64)
    f["collection_window_seconds"] = z(np.int64)
    f["first_seen_ts"] = np.full(n_accounts, 0, dtype=np.int64)
    f["last_seen_ts"] = z(np.int64)
    f["median_hold_seconds"] = np.full(n_accounts, np.nan)
    f["min_hold_seconds"] = np.full(n_accounts, np.nan)
    f["unattributed_out_amount"] = z()
    f["out_amount_cv"] = np.full(n_accounts, np.nan)
    f["round_amount_share"] = z()
    f["active_days"] = z(np.int32)

    is_round = (np.mod(amt, 1000.0) == 0)

    for a in range(n_accounts):
        oi = out_order[out_ptr[a]:out_ptr[a + 1]]
        ii = in_order[in_ptr[a]:in_ptr[a + 1]]
        o_ts, o_amt = np.sort(ts[oi]), amt[oi]
        i_ts_order = np.argsort(ts[ii], kind="stable")
        i_ts, i_amt = ts[ii][i_ts_order], amt[ii][i_ts_order]
        o_sorted = np.argsort(ts[oi], kind="stable")
        o_ts, o_amt = ts[oi][o_sorted], amt[oi][o_sorted]

        if i_ts.size == 0 and o_ts.size == 0:
            continue
        all_ts = np.concatenate([i_ts, o_ts]) if (i_ts.size and o_ts.size) else (i_ts if i_ts.size else o_ts)
        f["first_seen_ts"][a] = int(all_ts.min())
        f["last_seen_ts"][a] = int(all_ts.max())
        f["active_days"][a] = int(np.unique(all_ts // 86400).size)

        for w in VELOCITY_WINDOWS:
            ci, start = _peak_window(i_ts, w)
            co, _ = _peak_window(o_ts, w)
            f[f"peak_in_count_{w}"][a] = ci
            f[f"peak_out_count_{w}"][a] = co
            if w == PRIMARY_VELOCITY_WINDOW:
                f["peak_in_window_start"][a] = start
        if i_ts.size > 1:
            f["collection_window_seconds"][a] = int(i_ts[-1] - i_ts[0])
        if o_amt.size > 1 and o_amt.mean() > 0:
            f["out_amount_cv"][a] = float(o_amt.std() / o_amt.mean())
        if o_amt.size:
            f["round_amount_share"][a] = float(is_round[oi].mean())
        med, mn, un = _fifo_hold(i_ts, i_amt, o_ts, o_amt)
        if med is not None:
            f["median_hold_seconds"][a] = med
            f["min_hold_seconds"][a] = mn
        f["unattributed_out_amount"][a] = un

    with np.errstate(divide="ignore", invalid="ignore"):
        fr = np.where(f["total_in_amount"] > 0,
                      f["total_out_amount"] / np.maximum(f["total_in_amount"], 1e-9), 0.0)
    f["forward_ratio"] = np.clip(fr, 0.0, FORWARD_RATIO_CLIP)
    f["split_ratio"] = np.where(f["in_txn_count"] > 0,
                                f["out_txn_count"] / np.maximum(f["in_txn_count"], 1), 0.0)
    return f


def percentile_ranks(values: np.ndarray) -> np.ndarray:
    """Percentile rank of each value within the measured distribution (0-100)."""
    v = np.nan_to_num(values.astype(np.float64), nan=0.0)
    order = v.argsort(kind="stable")
    ranks = np.empty_like(order, dtype=np.float64)
    ranks[order] = np.arange(v.size, dtype=np.float64)
    return ranks / max(v.size - 1, 1) * 100.0
