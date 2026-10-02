"""
Investigation service: victim -> trace -> layered network -> evidence.

Layer is assigned RELATIVE TO THE SEED VICTIM and never stored on an account
(DATA_CONTEXT.md §18). Role and MRI come from the risk module only.
"""
from __future__ import annotations

import math, time
from collections import OrderedDict

import numpy as np

from ..config import MAX_EDGES, MAX_NODES
from . import graph as gr
from . import risk
from .evidence import exact_total, make_evidence, ulid
from .store import STORE

TRACES: "OrderedDict[str, dict]" = OrderedDict()
TRACE_LIMIT = 24


def _layer_for(hop: int, idx: int, F, P) -> tuple[str, str]:
    """
    Layer from hop distance AND behaviour (never hop depth alone - §17 rule 1).
    """
    fr = float(F["forward_ratio"][idx])
    fam = int(F["distinct_signal_families"][idx])
    in_deg, out_deg = int(F["in_degree"][idx]), int(F["out_degree"][idx])
    split = float(F["split_ratio"][idx])
    if hop == 0:
        return "VICTIM", "seed account of this trace"
    if fam >= 2 and fr < 0.6:
        return "L3", (f"{fam} terminal signal families with only {fr * 100:.0f}% of inflow "
                      f"observed leaving - flow stops being observable here")
    if hop == 1 and in_deg >= 3 and fr >= 0.5:
        return "L1", (f"1 hop from the victim; receives from {in_deg} distinct senders and "
                      f"forwards {fr * 100:.0f}% of inflow onward")
    if hop >= 2 and split >= 1.5 and out_deg >= 3:
        return "L2", (f"{hop} hops from the victim; receives consolidated value and splits "
                      f"to {out_deg} receivers (split ratio {split:.1f})")
    if hop == 1:
        return "L1", f"1 hop from the victim ({in_deg} senders in, {out_deg} receivers out)"
    return f"H{hop}", (f"{hop} hops from the victim; no distinctive collection or dispersal "
                       f"shape measured")


def run_trace(victim: str, amount: float | None, start_ts: int | None,
              end_ts: int | None, max_hops: int) -> dict:
    t0 = time.perf_counter()
    F, P = STORE.F, STORE.P
    vi = STORE.idx(victim)
    v_out_nbr, v_out_eids = STORE.fw.neighbours(vi)

    seed_ts = start_ts if start_ts is not None else (
        int(STORE.ts[v_out_eids].min()) - 1 if v_out_eids.size else 0)
    # default seed = the victim's single largest outgoing transfer (the likely
    # fraudulent debit); an officer normally supplies the reported amount instead.
    seed_amount = amount if amount is not None else (
        float(STORE.amount[v_out_eids].max()) if v_out_eids.size else 0.0)
    if amount is None and v_out_eids.size:
        seed_ts = int(STORE.ts[v_out_eids[int(np.argmax(STORE.amount[v_out_eids]))]]) - 1

    res = gr.trace_forward(STORE, vi, seed_ts, seed_amount, max_hops, window_end=end_ts)
    hop_of, value, arrival = res["nodes"], res["value"], res["arrival"]

    nodes = []
    for idx, hop in hop_of.items():
        s = risk.score_account(idx, F, P, STORE.cooccurrence_rate)
        role = risk.role_assessment(idx, F, P)
        layer, layer_reason = _layer_for(hop, idx, F, P)
        nodes.append({
            "account_id": STORE.aid(idx),
            "hop_distance": hop,
            "layer": layer,
            "relative_to_victim": victim,
            "layer_reason": layer_reason,
            "attributed_value": round(float(value.get(idx, 0.0)), 2),
            "arrival_ts": int(arrival.get(idx, 0)),
            "mri": s["mri"], "band": s["band"],
            "role": role["role"], "role_reasons": role["reasons"],
            "is_hub": bool(STORE.is_hub[idx]),
            "in_degree": int(F["in_degree"][idx]), "out_degree": int(F["out_degree"][idx]),
            "total_in": round(float(F["total_in_amount"][idx]), 2),
            "total_out": round(float(F["total_out_amount"][idx]), 2),
            "signal_families": int(F["distinct_signal_families"][idx]),
        })
    nodes.sort(key=lambda n: (n["hop_distance"], -n["mri"]))

    edges = []
    for e in res["edges"]:
        eid = e["eid"]
        edges.append({
            "edge_id": int(eid),
            "source_row_id": int(STORE.row_id[eid]),
            "from": STORE.aid(e["src"]), "to": STORE.aid(e["dst"]),
            "amount": round(float(STORE.amount[eid]), 2),
            "ts_epoch": int(STORE.ts[eid]),
            "hop": e["hop"],
            "attributed_value": round(float(e["attributed"]), 2),
        })
    edges.sort(key=lambda e: e["ts_epoch"])

    trace_id = ulid("trc")
    payload = {
        "trace_id": trace_id,
        "victim_account": victim,
        "seed_amount": round(seed_amount, 2),
        "seed_basis": "reported_amount" if amount is not None else "largest_outgoing_transfer",
        "seed_ts": seed_ts,
        "max_hops": max_hops,
        "node_count": len(nodes), "edge_count": len(edges),
        "truncated": res["truncation"] is not None,
        "truncation_reason": res["truncation"],
        "caps": {"max_nodes": MAX_NODES, "max_edges": MAX_EDGES},
        "hub_threshold_degree": STORE.hub_cut,
        "nodes": nodes, "edges": edges,
        "dataset_fingerprint": STORE.fingerprint,
        "processing_ms": round((time.perf_counter() - t0) * 1000, 2),
    }
    payload["summary"] = _summary(payload)
    payload["evidence"] = _evidence(payload)
    TRACES[trace_id] = payload
    while len(TRACES) > TRACE_LIMIT:
        TRACES.popitem(last=False)
    return payload


def _summary(p: dict) -> dict:
    by_layer: dict[str, int] = {}
    for n in p["nodes"]:
        by_layer[n["layer"]] = by_layer.get(n["layer"], 0) + 1
    flagged = [n for n in p["nodes"] if n["band"] in ("HIGH", "CRITICAL")]
    span = [e["ts_epoch"] for e in p["edges"]]
    return {
        "accounts_reached": p["node_count"],
        "transactions_traced": p["edge_count"],
        "value_traced": round(sum(e["amount"] for e in p["edges"]), 2),
        "layers": by_layer,
        "high_risk_accounts": len(flagged),
        "terminal_accounts": sum(1 for n in p["nodes"] if n["layer"] == "L3"),
        "hubs_encountered": sum(1 for n in p["nodes"] if n["is_hub"]),
        "time_span": {"from": min(span) if span else None, "to": max(span) if span else None},
        "statement": (
            f"{p['node_count']} accounts and {p['edge_count']} transactions were reached "
            f"within {p['max_hops']} hops of {p['victim_account']}. "
            f"{len(flagged)} accounts show HIGH or CRITICAL behavioural risk. "
            "These are observations and assessments, not findings of fact."),
    }


def _evidence(p: dict) -> list[dict]:
    """Claims built only from measured values, each citing its source rows."""
    out = []
    fp = STORE.fingerprint
    for n in p["nodes"]:
        if n["band"] not in ("HIGH", "CRITICAL") or n["hop_distance"] == 0:
            continue
        rows = [e["source_row_id"] for e in p["edges"] if e["to"] == n["account_id"]]
        if not rows:
            continue
        txns = STORE.rows_for(rows[:200])
        out.append(make_evidence(
            claim=(f"{len(rows)} traced transactions totalling Rs {exact_total(txns)} "
                   f"were received by {n['account_id']} within this trace"),
            claim_type="OBSERVED",
            measurement={"transactions": len(rows), "total_decimal": exact_total(txns),
                         "hop_distance": n["hop_distance"]},
            source_row_ids=rows[:200], fingerprint=fp, account_id=n["account_id"]))
        out.append(make_evidence(
            claim=(f"{n['account_id']} is assessed at MRI {n['mri']} ({n['band']}) from its "
                   f"observed behaviour: {'; '.join(n['role_reasons'])}"),
            claim_type="ASSESSED",
            measurement={"mri": n["mri"], "band": n["band"], "layer": n["layer"],
                         "relative_to_victim": n["relative_to_victim"]},
            source_row_ids=rows[:200], fingerprint=fp, account_id=n["account_id"]))
    return out[:60]


def timeline(p: dict, buckets: int = 180) -> dict:
    if not p["edges"]:
        return {"buckets": [], "from": None, "to": None}
    ts = np.array([e["ts_epoch"] for e in p["edges"]])
    amt = np.array([e["amount"] for e in p["edges"]])
    lo, hi = int(ts.min()), int(ts.max())
    width = max((hi - lo) // buckets, 60)
    keys = (ts - lo) // width
    out = []
    for k in np.unique(keys):
        m = keys == k
        out.append({"ts": int(lo + int(k) * width), "count": int(m.sum()),
                    "amount": round(float(amt[m].sum()), 2)})
    return {"buckets": out, "from": lo, "to": hi, "bucket_seconds": int(width)}
