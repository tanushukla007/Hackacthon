"""
Mule Risk Index (DATA_CONTEXT.md §26).

Deterministic, explainable, capped. No randomness, no model, no LLM.
Every component returns a score AND the measurement that produced it, so the
API can ship a reason string instead of a bare number.
"""
from __future__ import annotations

import math

from ..config import (CALIBRATION_REGIME, MRI_BANDS, MRI_DISCLAIMER, MRI_WEIGHTS,
                      PRIMARY_VELOCITY_WINDOW, ROLE_FANIN_PCTL, ROLE_FANOUT_PCTL,
                      ROLE_FORWARD_MIN, ROLE_SPLIT_MIN, ROLE_TERMINAL_FAMILIES,
                      ROLE_TERMINAL_MAX_FORWARD, TERMINAL_SIGNAL_SOLO_CAP)


def _band(score: float) -> str:
    for name, lo, hi in MRI_BANDS:
        if lo <= score < hi:
            return name
    return MRI_BANDS[-1][0]


def _fmt_inr(v: float) -> str:
    """Indian digit grouping, presentation only."""
    neg = v < 0
    s = f"{abs(v):.2f}"
    whole, frac = s.split(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        whole = ",".join(parts + [tail])
    return ("-" if neg else "") + whole + "." + frac


def _dur(seconds: float | None) -> str:
    if seconds is None or (isinstance(seconds, float) and math.isnan(seconds)):
        return "not measurable"
    s = int(seconds)
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m {s % 60}s"
    if s < 86400:
        return f"{s // 3600}h {(s % 3600) // 60}m"
    return f"{s // 86400}d {(s % 86400) // 3600}h"


def score_account(idx: int, F: dict, P: dict, cooccurrence_rate: float) -> dict:
    """Return the full MRI payload for one account index."""
    nan = float("nan")
    hold = float(F["median_hold_seconds"][idx])
    hold_ok = not math.isnan(hold)
    fr = float(F["forward_ratio"][idx])
    in_deg, out_deg = int(F["in_degree"][idx]), int(F["out_degree"][idx])
    in_amt, out_amt = float(F["total_in_amount"][idx]), float(F["total_out_amount"][idx])
    w = PRIMARY_VELOCITY_WINDOW
    peak_in, peak_out = int(F[f"peak_in_count_{w}"][idx]), int(F[f"peak_out_count_{w}"][idx])
    fam = int(F["distinct_signal_families"][idx])

    comps: list[dict] = []

    # ---- 1. pass-through: needs BOTH a high forward ratio AND a short hold ---
    hold_pct = float(P["median_hold_seconds"][idx]) if hold_ok else 100.0
    ratio_s = min(fr / 0.9, 1.0) if in_amt > 0 else 0.0
    hold_s = max(0.0, 1.0 - hold_pct / 100.0) if hold_ok else 0.0
    pt = ratio_s * hold_s
    comps.append({
        "key": "pass_through", "label": "Pass-through behaviour",
        "weight": MRI_WEIGHTS["pass_through"],
        "score": round(pt * MRI_WEIGHTS["pass_through"], 2),
        "measurement": {"forward_ratio": round(fr, 3),
                        "median_hold_seconds": None if not hold_ok else round(hold, 1),
                        "hold_percentile": round(hold_pct, 1)},
        "reason": (
            f"{fr * 100:.0f}% of observed inflow was forwarded, with a median hold of "
            f"{_dur(hold if hold_ok else None)}"
            if in_amt > 0 else "no inflow observed in the dataset window"),
    })

    # ---- 2. velocity --------------------------------------------------------
    v_pct = max(float(P[f"peak_in_count_{w}"][idx]), float(P[f"peak_out_count_{w}"][idx]))
    vel = (v_pct / 100.0) ** 2 if max(peak_in, peak_out) > 2 else 0.0
    comps.append({
        "key": "velocity", "label": "Temporal velocity",
        "weight": MRI_WEIGHTS["velocity"],
        "score": round(vel * MRI_WEIGHTS["velocity"], 2),
        "measurement": {"window_seconds": w, "peak_in": peak_in, "peak_out": peak_out,
                        "percentile": round(v_pct, 1),
                        "peak_in_window_start": int(F["peak_in_window_start"][idx])},
        "reason": (f"peak of {peak_in} inbound and {peak_out} outbound transactions in a "
                   f"rolling {w // 60}-minute window (percentile {v_pct:.1f})"),
    })

    # ---- 3. fan-in ----------------------------------------------------------
    fi_pct = float(P["in_degree"][idx])
    cw = int(F["collection_window_seconds"][idx])
    compress = 1.0
    if in_deg > 3 and cw > 0:
        compress = min(1.0, (in_deg / max(cw / 3600.0, 0.25)) / 20.0)
    fi = (fi_pct / 100.0) * (0.4 + 0.6 * compress) if in_deg > 2 else 0.0
    comps.append({
        "key": "fan_in", "label": "Fan-in (collection)",
        "weight": MRI_WEIGHTS["fan_in"], "score": round(fi * MRI_WEIGHTS["fan_in"], 2),
        "measurement": {"in_degree": in_deg, "percentile": round(fi_pct, 1),
                        "collection_window_seconds": cw},
        "reason": (f"{in_deg} distinct senders (percentile {fi_pct:.1f}) over a collection "
                   f"window of {_dur(cw) if cw else 'a single event'}"),
    })

    # ---- 4. fan-out ---------------------------------------------------------
    fo_pct = float(P["out_degree"][idx])
    split = float(F["split_ratio"][idx])
    fo = (fo_pct / 100.0) * (0.5 + 0.5 * min(split / 3.0, 1.0)) if out_deg > 2 else 0.0
    comps.append({
        "key": "fan_out", "label": "Fan-out (dispersal)",
        "weight": MRI_WEIGHTS["fan_out"], "score": round(fo * MRI_WEIGHTS["fan_out"], 2),
        "measurement": {"out_degree": out_deg, "percentile": round(fo_pct, 1),
                        "split_ratio": round(split, 2)},
        "reason": (f"{out_deg} distinct receivers (percentile {fo_pct:.1f}), "
                   f"{F['out_txn_count'][idx]} outgoing transactions"),
    })

    # ---- 5. terminal signals, with the §9.2 co-occurrence discount ----------
    raw_fam = fam / 3.0
    discount = 1.0 - 0.6 * max(0.0, min(cooccurrence_rate, 1.0))
    term = raw_fam * (1.0 if fam <= 1 else discount + (1 - discount) / fam)
    comps.append({
        "key": "terminal_signals", "label": "Terminal / exit signals",
        "weight": MRI_WEIGHTS["terminal_signals"],
        "score": round(term * MRI_WEIGHTS["terminal_signals"], 2),
        "measurement": {
            "distinct_families": fam,
            "foreign_ip_txns": int(F["is_foreign_ip_txns"][idx]),
            "automation_txns": int(F["is_automation_device_txns"][idx]),
            "crypto_txns": int(F["narr_crypto_txns"][idx]),
            "wallet_txns": int(F["narr_wallet_txns"][idx]),
            "cashout_txns": int(F["narr_cashout_txns"][idx]),
            "cooccurrence_discount_applied": round(discount, 3),
        },
        "reason": (f"{fam} of 3 signal families present"
                   + (f"; discounted because measured co-occurrence is "
                      f"{cooccurrence_rate:.2f}" if fam > 1 else "")
                   if fam else "no terminal signals on any transaction"),
    })

    # ---- 6. behavioural anomaly --------------------------------------------
    cv = float(F["out_amount_cv"][idx])
    structured = 0.0
    if int(F["out_txn_count"][idx]) >= 8 and not math.isnan(cv):
        structured = max(0.0, 1.0 - min(cv / 0.35, 1.0))
    rnd = float(F["round_amount_share"][idx])
    anom = min(1.0, structured * 0.8 + rnd * 0.2)
    comps.append({
        "key": "behavioral_anomaly", "label": "Behavioural anomaly",
        "weight": MRI_WEIGHTS["behavioral_anomaly"],
        "score": round(anom * MRI_WEIGHTS["behavioral_anomaly"], 2),
        "measurement": {"out_amount_cv": None if math.isnan(cv) else round(cv, 3),
                        "round_amount_share": round(rnd, 3),
                        "out_txn_count": int(F["out_txn_count"][idx])},
        "reason": (f"outgoing amounts cluster tightly (CV {cv:.2f}) across "
                   f"{int(F['out_txn_count'][idx])} transfers"
                   if structured > 0 else "no amount-clustering pattern measured"),
    })

    total = sum(c["score"] for c in comps)
    capped = False
    non_terminal = sum(c["score"] for c in comps if c["key"] != "terminal_signals")
    if non_terminal < 15 and total > TERMINAL_SIGNAL_SOLO_CAP:
        total, capped = TERMINAL_SIGNAL_SOLO_CAP, True

    top = sorted([c for c in comps if c["score"] > 0.5], key=lambda c: -c["score"])[:3]
    return {
        "mri": round(total, 1),
        "band": _band(total),
        "components": comps,
        "reason": "; ".join(c["reason"] for c in top) or
                  "no behavioural signal measured above threshold",
        "solo_cap_applied": capped,
        "calibration_regime": CALIBRATION_REGIME,
        "disclaimer": MRI_DISCLAIMER,
        "totals": {"total_in": _fmt_inr(in_amt), "total_out": _fmt_inr(out_amt),
                   "net_balance": _fmt_inr(in_amt - out_amt)},
    }


def role_assessment(idx: int, F: dict, P: dict) -> dict:
    """
    Behaviour-shape descriptor. NEVER from a single degree being zero
    (DATA_CONTEXT.md §15, §16) and never a global layer (§18).
    """
    in_deg, out_deg = int(F["in_degree"][idx]), int(F["out_degree"][idx])
    fr = float(F["forward_ratio"][idx])
    hold = float(F["median_hold_seconds"][idx])
    hold_ok = not math.isnan(hold)
    split = float(F["split_ratio"][idx])
    fi_pct, fo_pct = float(P["in_degree"][idx]), float(P["out_degree"][idx])
    fam = int(F["distinct_signal_families"][idx])

    in_txn, out_txn = int(F["in_txn_count"][idx]), int(F["out_txn_count"][idx])
    consolidated = in_txn > 0 and out_txn >= in_txn * ROLE_SPLIT_MIN

    role, why = "PARTICIPANT", []
    if fi_pct >= ROLE_FANIN_PCTL and fr >= ROLE_FORWARD_MIN and out_deg >= 1:
        role = "COLLECTOR"
        why.append(f"high fan-in ({in_deg} senders, percentile {fi_pct:.1f}) with "
                   f"{fr * 100:.0f}% of inflow forwarded onward")
    if fo_pct >= ROLE_FANOUT_PCTL and in_deg >= 1 and split >= ROLE_SPLIT_MIN and consolidated:
        role = "DISTRIBUTOR" if role == "PARTICIPANT" else "COLLECTOR_DISTRIBUTOR"
        why.append(f"receives consolidated inflow then splits to {out_deg} receivers "
                   f"(percentile {fo_pct:.1f}, split ratio {split:.1f})")
    if fam >= ROLE_TERMINAL_FAMILIES and fr < ROLE_TERMINAL_MAX_FORWARD:
        role = "TERMINAL" if role == "PARTICIPANT" else role
        why.append(f"{fam} terminal signal families present with only "
                   f"{fr * 100:.0f}% of inflow leaving the account")
    if fi_pct >= ROLE_FANIN_PCTL and out_deg == 0:
        role = "HOLDER"
        why = [f"high fan-in ({in_deg} senders) with no observed outflow - "
               f"a holder, which is a different finding from a collector"]
    return {
        "role": role,
        "confidence": "ASSESSED",
        "reasons": why or ["no distinctive flow shape measured"],
        "note": "Role descriptors describe the shape of flow through the account. "
                "Both collectors and distributors send and receive.",
        "hold": None if not hold_ok else hold,
    }
