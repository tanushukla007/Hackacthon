"""
HTTP surface. Every response uses the single envelope; every error code comes
from the closed set. No business logic lives here.
"""
from __future__ import annotations

import re, threading, time
from pathlib import Path

from fastapi import APIRouter, Query, Request
from starlette.responses import Response

from ..config import (ACCOUNT_PATTERN, API_VERSION, BUDGET_MS, LEGAL_PRODUCTION,
                      LEGAL_SEIZURE, MAX_EDGES, MAX_HOPS_LIMIT, MAX_NODES,
                      MRI_BANDS, MRI_WEIGHTS, RAW_DIR, VELOCITY_WINDOWS)
from ..errors import ApiError, ok
from ..core import bank_gateway, cases as case_store, documents
from ..core import investigate, risk
from ..core.evidence import exact_total, make_evidence
from ..core.store import STORE

router = APIRouter(prefix="/api")
ACCT_RE = re.compile(ACCOUNT_PATTERN)


def _need_dataset():
    if not STORE.ready:
        raise ApiError("DATASET_NOT_LOADED",
                       "No dataset is loaded. Ingest a CSV first.",
                       detail={"state": STORE.state},
                       hint="POST /api/ingest with {\"filename\": \"<file in data/raw>\"}")


def _bench():
    """Measured benchmark file, or None. Never an estimate."""
    import json
    from ..config import ARTIFACT_DIR
    f = ARTIFACT_DIR / "bench.json"
    if not f.exists():
        return None
    try:
        b = json.loads(f.read_text())
    except Exception:                                    # noqa: BLE001
        return None
    if b.get("dataset_fingerprint") != STORE.fingerprint:
        return {"stale": True, "measured_for": b.get("dataset_fingerprint"),
                "note": "These benchmarks were measured on a different dataset."}
    return b


def _acct(a: str) -> int:
    if not ACCT_RE.match(a):
        raise ApiError("INVALID_ACCOUNT_FORMAT",
                       "Account numbers are 12-digit strings.",
                       detail={"received": a, "pattern": ACCOUNT_PATTERN})
    i = STORE.idx(a)
    if i is None:
        raise ApiError("ACCOUNT_NOT_FOUND", f"Account {a} does not appear in this dataset.",
                       detail={"account_id": a})
    return i


# --------------------------------------------------------------- system
@router.get("/system/health")
def health(request: Request):
    """Liveness. Answers before the dataset is loaded, and says so."""
    t = time.perf_counter()
    return ok(request, t, {"status": "ok", "api_version": API_VERSION,
                           "dataset_state": STORE.state})


@router.get("/system/status")
def status(request: Request):
    """One call the whole UI can boot from: dataset, documents, bank, budgets."""
    t = time.perf_counter()
    return ok(request, t, {
        "dataset": {
            "state": STORE.state,
            "source_file": STORE.source_path.name if STORE.source_path else None,
            "fingerprint": STORE.fingerprint,
            "rows": STORE.n_rows, "accounts": STORE.n_accounts,
            "loaded_at": STORE.loaded_at, "ingest_seconds": STORE.ingest_seconds,
            "stage_timings_ms": STORE.timings,
        },
        "config": {
            "mri_weights": MRI_WEIGHTS,
            "mri_bands": [{"band": b, "from": lo, "to": hi} for b, lo, hi in MRI_BANDS],
            "velocity_windows": list(VELOCITY_WINDOWS),
            "caps": {"max_nodes": MAX_NODES, "max_edges": MAX_EDGES,
                     "max_hops": MAX_HOPS_LIMIT},
            "hub_threshold_degree": STORE.hub_cut,
        },
        "budgets_ms": BUDGET_MS,
        "benchmarks": _bench(),      # null until tools/bench.py is run - never invented
        "legal_basis": {"production": LEGAL_PRODUCTION, "seizure": LEGAL_SEIZURE},
        "ground_truth": {"labels_available": False,
                         "accuracy_metrics": None,
                         "note": "No labels exist for this dataset. Precision, recall and "
                                 "F1 cannot be computed and are never displayed."},
        "documents": {"pdf_available": documents.PDF_AVAILABLE,
                      "engine": documents.PDF_ENGINE,
                      "types": list(documents.DOC_TYPES)},
        "bank_gateway": bank_gateway.status(),
    })


# --------------------------------------------------------------- ingest
@router.get("/ingest/status")
def ingest_status(request: Request):
    """Honest ingestion state: stage list with measured milliseconds, never a percentage."""
    t = time.perf_counter()
    return ok(request, t, {"job_id": STORE.job_id,
                           "state": STORE.state, "current_stage": STORE.stage,
                           "stages": STORE.stages, "error": STORE.error,
                           "source_file": STORE.source_path.name if STORE.source_path else None,
                           "available_files": sorted(p.name for p in RAW_DIR.glob("*.csv"))})


@router.post("/ingest")
async def ingest(request: Request):
    """Start loading a CSV from data/raw. Returns 202 and a job id; poll for the rest."""
    t = time.perf_counter()
    body = await request.json() if await request.body() else {}
    name = body.get("filename")
    files = sorted(RAW_DIR.glob("*.csv"))
    if not files:
        raise ApiError("FILE_NOT_FOUND", "No CSV found in data/raw.",
                       hint="Drop the dataset CSV into data/raw/ and retry.")
    src = RAW_DIR / name if name else files[0]
    if not src.exists():
        raise ApiError("FILE_NOT_FOUND", f"{src.name} is not in data/raw.",
                       detail={"available": [p.name for p in files]})
    if STORE.state == "LOADING":
        raise ApiError("INGEST_IN_PROGRESS", "An ingest is already running.",
                       detail={"current_stage": STORE.stage})
    threading.Thread(target=STORE.load, args=(src,), daemon=True).start()
    return ok(request, t, {"accepted": True, "source_file": src.name,
                           "job_id": STORE.job_id,
                           "poll": "/api/ingest/status"}, status=202)


@router.get("/ingest/profile")
def profile(request: Request):
    """The profile measured during ingestion of the loaded file."""
    t = time.perf_counter()
    _need_dataset()
    return ok(request, t, STORE.profile)


# -------------------------------------------------------------- dataset
@router.get("/dataset/summary")
def dataset_summary(request: Request):
    """What this dataset is: rows, accounts, window, amounts, modes, duplicates."""
    t = time.perf_counter()
    _need_dataset()
    p = STORE.profile
    return ok(request, t, {
        "source_file": p["source_file"], "fingerprint": p["dataset_fingerprint"],
        "rows": p["rows"], "accounts": p["accounts"],
        "time_window": p["time_window"], "amount": p["amount"],
        "payment_modes": p["payment_modes"], "devices": p["devices"],
        "signals": p["signals"], "signal_cooccurrence": p["signal_cooccurrence"],
        "duplicates": {
            "unique_transaction_ids": p["unique_transaction_ids"],
            "duplicate_transaction_ids": p["duplicate_transaction_ids"],
            "rows_with_duplicate_id": p["rows_with_duplicate_id"],
            "surplus": p["duplicate_id_surplus"],
            "exact_duplicate_rows": p["exact_duplicate_rows"],
            "policy": "Every source row is preserved. source_row_id is the key.",
        },
        "ingest_seconds": p["ingest_seconds"],
        "hub_accounts": p.get("hub_accounts"),
        "hub_threshold_degree": p.get("hub_threshold_degree"),
    })


@router.get("/accounts/top")
def top_accounts(request: Request, limit: int = Query(25, ge=1, le=200)):
    """Accounts ranked by the index, each with the reason it ranked."""
    t = time.perf_counter()
    _need_dataset()
    import numpy as np
    F, P = STORE.F, STORE.P
    order = np.argsort(-STORE.mri)[:limit]
    out = []
    for i in order:
        i = int(i)
        s = risk.score_account(i, F, P, STORE.cooccurrence_rate)
        out.append({"account_id": STORE.aid(i), "mri": s["mri"], "band": s["band"],
                    "role": STORE.role[i], "reason": s["reason"],
                    "in_degree": int(F["in_degree"][i]), "out_degree": int(F["out_degree"][i]),
                    "total_in": round(float(F["total_in_amount"][i]), 2),
                    "forward_ratio": round(float(F["forward_ratio"][i]), 3),
                    "signal_families": int(F["distinct_signal_families"][i]),
                    "is_hub": bool(STORE.is_hub[i])})
    from ..config import CALIBRATION_REGIME, MRI_DISCLAIMER
    return ok(request, t, {"accounts": out, "ranked_from": STORE.n_accounts,
                           "calibration_regime": CALIBRATION_REGIME,
                           "disclaimer": MRI_DISCLAIMER})


@router.get("/accounts/risk-distribution")
def risk_distribution(request: Request):
    """Band counts, MRI histogram and role counts across the dataset."""
    t = time.perf_counter()
    _need_dataset()
    import numpy as np
    counts: dict[str, int] = {}
    for b in STORE.band:
        counts[b] = counts.get(b, 0) + 1
    hist, edges = np.histogram(STORE.mri, bins=20, range=(0, 100))
    return ok(request, t, {
        "bands": counts,
        "histogram": [{"from": float(edges[i]), "to": float(edges[i + 1]),
                       "count": int(hist[i])} for i in range(len(hist))],
        "accounts": STORE.n_accounts,
        "roles": {r: STORE.role.count(r) for r in sorted(set(STORE.role))},
    })


@router.get("/accounts/stats")
def account_stats(request: Request, expected: int | None = None):
    """Account reconciliation: what the file contains and why that number.

    `expected` is optional and is echoed back as a CALLER-SUPPLIED claim. It is
    never treated as truth, because this workspace holds no verified account
    universe to check it against.
    """
    t = time.perf_counter()
    _need_dataset()
    from ..core import reconcile
    key = ("recon", str(STORE.source_path), expected)
    cached = getattr(STORE, "_recon_cache", {}).get(key)
    if cached is None:
        cached = reconcile.build(STORE.source_path, expected_total=expected)
        if not hasattr(STORE, "_recon_cache"):
            STORE._recon_cache = {}
        STORE._recon_cache[key] = cached
    out = dict(cached)
    out["accounts_in_index"] = STORE.n_accounts
    out["index_matches_scan"] = (STORE.n_accounts == cached["observed_accounts"])
    out["display"] = ("%s observed transaction accounts" %
                      format(cached["observed_accounts"], ","))
    return ok(request, t, out)


@router.get("/accounts/ranking")
def account_ranking(request: Request, limit: int = 100, offset: int = 0,
                    band: str | None = None):
    """The canonical ranked candidate list.

    One scorer, one ranking. Every other endpoint that shows a risk number
    reads the same cached array, so no two screens can disagree.
    """
    t = time.perf_counter()
    _need_dataset()
    from ..config import CALIBRATION_REGIME, MRI_DISCLAIMER
    limit = max(1, min(int(limit), 2000))
    order = STORE.ranking_order()
    rows = []
    for rank0, i in enumerate(order):
        if band and STORE.band[i] != band.upper():
            continue
        if len(rows) >= limit + offset:
            break
        rows.append({
            "rank": rank0 + 1,
            "account_id": STORE.aid(int(i)),
            "risk_score": round(float(STORE.mri[i]), 2),
            "risk_band": STORE.band[i],
            "role_global": STORE.role[i],
            "reason": STORE.reason[i],
            "in_degree": int(STORE.F["in_degree"][i]),
            "out_degree": int(STORE.F["out_degree"][i]),
            "total_in": float(STORE.F["total_in_amount"][i]),
            "total_out": float(STORE.F["total_out_amount"][i]),
        })
    return ok(request, t, {
        "ranked_accounts": STORE.n_accounts,
        "returned": len(rows[offset:offset + limit]),
        "accounts": rows[offset:offset + limit],
        "scoring": {"engine": "core/risk.py", "regime": CALIBRATION_REGIME},
        "disclaimer": MRI_DISCLAIMER,
    })


@router.get("/accounts/search")
def search(request: Request, q: str = Query(..., min_length=2), limit: int = 20):
    """Prefix search over account numbers present in the dataset."""
    t = time.perf_counter()
    _need_dataset()
    hits = [a for a in STORE.idx_to_id if q in a][:limit]
    return ok(request, t, {"query": q, "matches": hits, "count": len(hits)})


def _account_payload(account_id: str, i: int) -> dict:
    """Everything observed about one account. Shared by the API and the PDF report."""
    F, P = STORE.F, STORE.P
    s = risk.score_account(i, F, P, STORE.cooccurrence_rate)
    r = risk.role_assessment(i, F, P)
    w = 3600
    banks = STORE.db.execute(
        "SELECT DISTINCT sender_bank FROM txn WHERE Sender_Account = ? "
        "UNION SELECT DISTINCT receiver_bank FROM txn WHERE Receiver_Account = ?",
        [account_id, account_id]).fetchall()
    modes = STORE.db.execute(
        "SELECT payment_mode, COUNT(*) FROM txn WHERE Sender_Account = ? OR "
        "Receiver_Account = ? GROUP BY 1 ORDER BY 2 DESC", [account_id, account_id]).fetchall()
    devs = STORE.db.execute(
        "SELECT device_type, COUNT(*) FROM txn WHERE Sender_Account = ? GROUP BY 1 "
        "ORDER BY 2 DESC", [account_id]).fetchall()
    hold = float(F["median_hold_seconds"][i])
    import math
    return {
        "account_id": account_id,
        "identity": {"banks_used": sorted({b[0] for b in banks if b[0]}),
                     "first_seen_ts": int(F["first_seen_ts"][i]),
                     "last_seen_ts": int(F["last_seen_ts"][i]),
                     "active_days": int(F["active_days"][i])},
        "topology": {
            "in_degree": int(F["in_degree"][i]), "out_degree": int(F["out_degree"][i]),
            "in_txn_count": int(F["in_txn_count"][i]),
            "out_txn_count": int(F["out_txn_count"][i]),
            "in_degree_percentile": round(float(P["in_degree"][i]), 1),
            "out_degree_percentile": round(float(P["out_degree"][i]), 1),
            "is_hub": bool(STORE.is_hub[i]),
        },
        "value": {
            "total_in": round(float(F["total_in_amount"][i]), 2),
            "total_out": round(float(F["total_out_amount"][i]), 2),
            "net_balance": round(float(F["net_balance"][i]), 2),
            "net_balance_note": "Observed flow residual within the dataset window. "
                                "This is NOT the account's bank balance.",
        },
        "temporal": {
            "median_hold_seconds": None if math.isnan(hold) else round(hold, 1),
            "collection_window_seconds": int(F["collection_window_seconds"][i]),
            "peak_in_count_3600": int(F[f"peak_in_count_{w}"][i]),
            "peak_out_count_3600": int(F[f"peak_out_count_{w}"][i]),
            "peak_in_window_start": int(F["peak_in_window_start"][i]),
        },
        "flow": {"forward_ratio": round(float(F["forward_ratio"][i]), 3),
                 "split_ratio": round(float(F["split_ratio"][i]), 2),
                 "unattributed_out_amount": round(float(F["unattributed_out_amount"][i]), 2)},
        "signals": {
            "foreign_ip_txns": int(F["is_foreign_ip_txns"][i]),
            "automation_txns": int(F["is_automation_device_txns"][i]),
            "crypto_txns": int(F["narr_crypto_txns"][i]),
            "wallet_txns": int(F["narr_wallet_txns"][i]),
            "cashout_txns": int(F["narr_cashout_txns"][i]),
            "distinct_families": int(F["distinct_signal_families"][i]),
            "verdict": None,
            "possible_readings": [
                "transfers consistent with exit or conversion behaviour",
                "a VPN, hosting provider or integration used by an ordinary customer",
                "test or batch traffic",
            ] if int(F["distinct_signal_families"][i]) else [],
        },
        "context": {"payment_modes": {m[0]: int(m[1]) for m in modes},
                    "devices": {d[0]: int(d[1]) for d in devs}},
        "risk": s, "role": r,
        "layer_note": "No global layer is stored. Layer is assigned per investigation, "
                      "relative to that investigation's victim.",
    }


@router.get("/accounts/{account_id}")
def account(request: Request, account_id: str):
    """Everything observed about one account, with risk and role attached."""
    t = time.perf_counter()
    _need_dataset()
    return ok(request, t, _account_payload(account_id, _acct(account_id)))


@router.get("/accounts/{account_id}/transactions")
def account_txns(request: Request, account_id: str,
                 direction: str = Query("all", pattern="^(all|in|out)$"),
                 limit: int = Query(100, ge=1, le=1000), offset: int = 0):
    """Paged transactions for an account, each carrying its source_row_id."""
    t = time.perf_counter()
    _need_dataset()
    _acct(account_id)
    where = {"all": "(Sender_Account = ? OR Receiver_Account = ?)",
             "in": "Receiver_Account = ?", "out": "Sender_Account = ?"}[direction]
    params = [account_id, account_id] if direction == "all" else [account_id]
    total = STORE.db.execute(f"SELECT COUNT(*) FROM txn WHERE {where}", params).fetchone()[0]
    rows = STORE.db.execute(
        "SELECT Transaction_ID, Sender_Account, Receiver_Account, Sender_IFSC, Receiver_IFSC, "
        "amount_f, timestamp, payment_mode, Narration, IP_Address, device_type, source_row_id, "
        f"dup_txn_id, is_foreign_ip, is_automation_device, narr_crypto, narr_wallet, "
        f"narr_cashout FROM txn WHERE {where} ORDER BY timestamp LIMIT ? OFFSET ?",
        params + [limit, offset]).fetchall()
    from ..core.store import _txn_payload
    return ok(request, t, {"account_id": account_id, "direction": direction,
                           "total": int(total), "limit": limit, "offset": offset,
                           "transactions": [_txn_payload(r) for r in rows]})


@router.get("/accounts/{account_id}/counterparties")
def counterparties(request: Request, account_id: str, limit: int = 25):
    """Who paid this account and who it paid, by value."""
    t = time.perf_counter()
    _need_dataset()
    _acct(account_id)
    inb = STORE.db.execute(
        "SELECT Sender_Account, COUNT(*), SUM(amount_f) FROM txn WHERE Receiver_Account = ? "
        "GROUP BY 1 ORDER BY 3 DESC LIMIT ?", [account_id, limit]).fetchall()
    outb = STORE.db.execute(
        "SELECT Receiver_Account, COUNT(*), SUM(amount_f) FROM txn WHERE Sender_Account = ? "
        "GROUP BY 1 ORDER BY 3 DESC LIMIT ?", [account_id, limit]).fetchall()
    f = lambda rs: [{"account_id": r[0], "transactions": int(r[1]),   # noqa: E731
                     "amount": round(float(r[2]), 2)} for r in rs]
    return ok(request, t, {"inbound": f(inb), "outbound": f(outb)})


# --------------------------------------------------------- transactions
@router.get("/transactions/{transaction_id}")
def transaction(request: Request, transaction_id: str):
    """Look up by Transaction_ID; 409 when the id matches several rows."""
    t = time.perf_counter()
    _need_dataset()
    rows = STORE.db.execute(
        "SELECT Transaction_ID, Sender_Account, Receiver_Account, Sender_IFSC, Receiver_IFSC, "
        "amount_f, timestamp, payment_mode, Narration, IP_Address, device_type, source_row_id, "
        "dup_txn_id, is_foreign_ip, is_automation_device, narr_crypto, narr_wallet, narr_cashout "
        "FROM txn WHERE Transaction_ID = ? ORDER BY source_row_id",
        [transaction_id]).fetchall()
    if not rows:
        raise ApiError("TRANSACTION_NOT_FOUND", f"No row carries Transaction_ID "
                                                f"{transaction_id}.")
    from ..core.store import _txn_payload
    matches = [_txn_payload(r) for r in rows]
    warn = None
    if len(matches) > 1:
        warn = [f"Transaction_ID {transaction_id} appears on {len(matches)} source rows. "
                f"Use source_row_id to address one row."]
    return ok(request, t, {"transaction_id": transaction_id, "match_count": len(matches),
                           "ambiguous": len(matches) > 1, "matches": matches}, warnings=warn)


@router.get("/rows/{source_row_id}")
def row(request: Request, source_row_id: int):
    """The provenance endpoint: one immutable source row, exactly as ingested."""
    t = time.perf_counter()
    _need_dataset()
    rows = STORE.rows_for([source_row_id])
    if not rows:
        raise ApiError("ROW_NOT_FOUND", f"source_row_id {source_row_id} is not in this dataset.",
                       detail={"rows_in_dataset": STORE.n_rows})
    return ok(request, t, {"row": rows[0], "provenance": {
        "source_file": STORE.source_path.name, "dataset_fingerprint": STORE.fingerprint,
        "note": "source_row_id is the 0-based ordinal of this row in the source file."}})


# --------------------------------------------------------------- traces
@router.post("/trace")
async def create_trace(request: Request):
    """Follow this victim's money. Bounded, value-weighted, truncation always reported."""
    t = time.perf_counter()
    _need_dataset()
    body = await request.json()
    victim = str(body.get("victim_account", ""))
    _acct(victim)
    hops = int(body.get("max_hops", 4))
    if not 1 <= hops <= MAX_HOPS_LIMIT:
        raise ApiError("INVALID_HOPS", f"max_hops must be between 1 and {MAX_HOPS_LIMIT}.",
                       detail={"received": hops})
    amount = body.get("amount")
    if amount is not None and float(amount) <= 0:
        raise ApiError("INVALID_AMOUNT", "amount must be positive.")
    start_ts, end_ts = body.get("start_ts"), body.get("end_ts")
    if start_ts and end_ts and int(end_ts) <= int(start_ts):
        raise ApiError("INVALID_TIME_WINDOW", "end_ts must be after start_ts.")
    p = investigate.run_trace(victim, float(amount) if amount else None,
                              int(start_ts) if start_ts else None,
                              int(end_ts) if end_ts else None, hops)
    warn = ([f"Result truncated: {p['truncation_reason']}"] if p["truncated"] else None)

    # Optional: file this investigation against a case, so the case keeps a
    # receipt of what was run and the diary says so without anyone typing it.
    case_id = body.get("case_id")
    if case_id:
        c = _case(case_id)
        case_store.add_trace(c, p)
        case_store.add_diary(
            c,
            "Trace run from victim " + p["victim_account"] + ": " +
            str(p["node_count"]) + " accounts, " + str(p["edge_count"]) +
            " transfers, " + str(p["max_hops"]) + " hops." +
            (" Result truncated (" + str(p["truncation_reason"]) + ")."
             if p["truncated"] else ""),
            c.get("officer") or "SYSTEM", kind="ACTION",
            refs={"trace_ids": [p["trace_id"]], "accounts": [p["victim_account"]]})
    return ok(request, t, p, warnings=warn)


@router.get("/trace/{trace_id}")
def get_trace(request: Request, trace_id: str):
    """Re-read a trace held in memory. Expired traces 404 rather than re-running."""
    t = time.perf_counter()
    p = investigate.TRACES.get(trace_id)
    if not p:
        raise ApiError("TRACE_NOT_FOUND", "That trace is no longer in memory.",
                       hint="Re-run the trace from the investigation page.")
    return ok(request, t, p)


@router.get("/trace/{trace_id}/timeline")
def get_timeline(request: Request, trace_id: str, buckets: int = 180):
    """Bucketed activity for a trace, for the playback control."""
    t = time.perf_counter()
    p = investigate.TRACES.get(trace_id)
    if not p:
        raise ApiError("TRACE_NOT_FOUND", "That trace is no longer in memory.")
    return ok(request, t, investigate.timeline(p, buckets))


@router.get("/trace/{trace_id}/evidence")
def get_evidence(request: Request, trace_id: str):
    """The evidence objects a trace produced, each citing its rows."""
    t = time.perf_counter()
    p = investigate.TRACES.get(trace_id)
    if not p:
        raise ApiError("TRACE_NOT_FOUND", "That trace is no longer in memory.")
    return ok(request, t, {"trace_id": trace_id, "evidence": p["evidence"],
                           "count": len(p["evidence"])})


# ---------------------------------------------------------------- cases
@router.get("/cases")
def list_cases(request: Request):
    """All cases on disk, newest first."""
    t = time.perf_counter()
    return ok(request, t, {"cases": case_store.listing()})


@router.post("/cases")
async def create_case(request: Request):
    """Open a case file around a victim account."""
    t = time.perf_counter()
    body = await request.json()
    c = case_store.create(body.get("title", "Untitled investigation"),
                          str(body.get("victim_account", "")),
                          body.get("officer", "Investigating Officer"),
                          body.get("reported_amount"), STORE.fingerprint)
    return ok(request, t, c, status=201)


@router.get("/cases/{case_id}")
def get_case(request: Request, case_id: str):
    """One case: details, basket, diary, traces run and documents issued."""
    t = time.perf_counter()
    c = case_store.load(case_id)
    if not c:
        raise ApiError("CASE_NOT_FOUND", f"{case_id} does not exist.")
    return ok(request, t, c)


@router.post("/cases/{case_id}/evidence")
async def add_case_evidence(request: Request, case_id: str):
    """Pin evidence into the basket; refuses evidence from another dataset."""
    t = time.perf_counter()
    c = case_store.load(case_id)
    if not c:
        raise ApiError("CASE_NOT_FOUND", f"{case_id} does not exist.")
    body = await request.json()
    items = body.get("items") or ([body] if body.get("claim") else [])
    if not items:
        raise ApiError("VALIDATION_FAILED", "No evidence items supplied.")
    try:
        c = case_store.add_evidence(c, items, STORE.fingerprint)
    except ValueError:
        raise ApiError("FINGERPRINT_MISMATCH",
                       "That evidence was produced from a different dataset.",
                       detail={"current": STORE.fingerprint})
    return ok(request, t, {"case_id": case_id, "basket_size": len(c["basket"])}, status=201)


@router.post("/cases/{case_id}/diary")
async def add_case_diary(request: Request, case_id: str):
    """Append one diary entry. Entries are never edited or deleted."""
    t = time.perf_counter()
    c = case_store.load(case_id)
    if not c:
        raise ApiError("CASE_NOT_FOUND", f"{case_id} does not exist.")
    body = await request.json()
    text = (body.get("text") or "").strip()
    if not text:
        raise ApiError("VALIDATION_FAILED", "Diary text is required.")
    c = case_store.add_diary(c, text, body.get("officer", "Investigating Officer"),
                             body.get("kind", "NOTE"), refs=body.get("refs"))
    return ok(request, t, {"case_id": case_id, "entries": len(c["diary"])}, status=201)


DOC_SLUGS = {
    "case-diary": "CASE_DIARY",
    "freeze-requisition": "FREEZE_REQUISITION",
    "covering-letter": "COVERING_LETTER",
    "victim-acknowledgement": "VICTIM_ACKNOWLEDGEMENT",
}


def _case(case_id: str) -> dict:
    c = case_store.load(case_id)
    if not c:
        raise ApiError("CASE_NOT_FOUND", f"{case_id} does not exist.")
    return c


def _freeze_blocks(accounts: list[str], trace: dict | None) -> tuple[list[dict], str]:
    """Per-account credited totals, recomputed with Decimal from the cited rows.

    Two different quantities exist and they must never be confused:

      TRACED_FROM_VICTIM    only the transactions this trace actually followed
                            into the account. This is the amount a freeze can
                            honestly be asked for.
      ALL_CREDITS_IN_WINDOW every credit the account received in the dataset
                            window, whatever its origin. Larger, and not
                            attributable to the complainant.

    When a trace is supplied the first is used; otherwise the second is used
    and the document says so in plain words.
    """
    basis = "TRACED_FROM_VICTIM" if trace else "ALL_CREDITS_IN_WINDOW"
    by_account: dict[str, list[dict]] = {}
    if trace:
        for ed in trace.get("edges", []):
            by_account.setdefault(ed["to"], []).append(
                {"amount": float(ed["amount"]), "source_row_id": int(ed["source_row_id"])})

    blocks = []
    for a in accounts:
        i = _acct(a)
        if trace:
            hits = by_account.get(a, [])
        else:
            hits = [{"amount": float(r[1]), "source_row_id": int(r[0])} for r in
                    STORE.db.execute(
                        "SELECT source_row_id, amount_f FROM txn WHERE Receiver_Account = ? "
                        "ORDER BY timestamp", [a]).fetchall()]
        bank = STORE.db.execute(
            "SELECT receiver_bank FROM txn WHERE Receiver_Account = ? LIMIT 1",
            [a]).fetchone()
        sc = risk.score_account(i, STORE.F, STORE.P, STORE.cooccurrence_rate)
        blocks.append({
            "account_id": a,
            "bank": bank[0] if bank else None,
            "credited_total": exact_total(hits),
            "transactions_cited": len(hits),
            "source_row_ids": [h["source_row_id"] for h in hits[:500]],
            "basis": basis,
            "mri": sc["mri"],
            "band": sc["band"],
        })
    return blocks, basis


def _store_document(case: dict, doc: dict) -> dict:
    case.setdefault("documents", [])
    case["documents"] = [d for d in case["documents"] if isinstance(d, dict)]
    case["documents"].append(doc)
    case_store.save(case)
    return doc


def _find_document(case: dict, document_id: str) -> dict:
    for d in case.get("documents", []):
        if d.get("document_id") == document_id:
            return d
    raise ApiError("DOCUMENT_NOT_FOUND", f"{document_id} is not a document of this case.",
                   hint="Generate the document first; documents are stored with the case.")


def _render(doc: dict, fmt: str, request: Request):
    """html | pdf | json -> an HTTP response."""
    if fmt == "json":
        return None
    if fmt == "html":
        return Response(content=documents.render_html(doc), media_type="text/html")
    if fmt == "pdf":
        if not documents.PDF_AVAILABLE:
            raise ApiError("PDF_ENGINE_UNAVAILABLE",
                           "No PDF engine is installed on the backend.",
                           detail={"engine": "weasyprint"},
                           hint="pip install weasyprint, or request format=html and print "
                                "from the browser.")
        pdf = documents.render_pdf(doc)
        name = f"{doc['reference'].replace('/', '_')}.pdf"
        return Response(content=pdf, media_type="application/pdf",
                        headers={"Content-Disposition": f'inline; filename="{name}"',
                                 "X-Document-Id": doc["document_id"]})
    raise ApiError("VALIDATION_FAILED", "format must be json, html or pdf.",
                   detail={"received": fmt})


@router.post("/cases/{case_id}/details")
async def update_case_details(request: Request, case_id: str):
    """Officer, station, FIR and complainant fields used by the letters."""
    t = time.perf_counter()
    c = _case(case_id)
    body = await request.json()
    for k in ("title", "officer", "status", "victim_account", "reported_amount"):
        if k in body and body[k] not in (None, ""):
            c[k] = body[k]
    details = c.get("details") or {}
    allowed = {"officer_rank", "officer_contact", "police_station", "district",
               "fir_number", "fir_date", "complainant_name", "complainant_address",
               "complainant_contact", "complaint_date", "response_days", "notes"}
    for k, v in (body.get("details") or {}).items():
        if k in allowed:
            details[k] = v
    c["details"] = details
    case_store.save(c)
    return ok(request, t, c)


@router.post("/cases/{case_id}/documents/{slug}")
async def create_document(request: Request, case_id: str, slug: str,
                          format: str = Query("json", pattern="^(json|html|pdf)$")):
    """Build a case document from the closed slug set. Deterministic, Decimal-exact."""
    t = time.perf_counter()
    _need_dataset()
    kind = DOC_SLUGS.get(slug)
    if not kind:
        raise ApiError("UNSUPPORTED_DOCUMENT_TYPE",
                       f"{slug} is not a document this system produces.",
                       detail={"supported": sorted(DOC_SLUGS)})
    c = _case(case_id)
    body = await request.json() if await request.body() else {}
    seq = sum(1 for d in c.get("documents", []) if d.get("type") == kind) + 1

    if kind == "CASE_DIARY":
        doc = documents.build_case_diary(c, STORE.fingerprint, seq)
    elif kind == "FREEZE_REQUISITION":
        accounts = body.get("accounts") or []
        if not accounts:
            raise ApiError("BASKET_EMPTY", "Select at least one account to requisition.")
        trace_id = body.get("trace_id")
        trace = investigate.TRACES.get(trace_id) if trace_id else None
        if trace_id and not trace:
            raise ApiError("TRACE_NOT_FOUND",
                           "That trace is no longer in memory, so the amounts cannot be "
                           "limited to it.",
                           hint="Re-run the trace, or omit trace_id to requisition on the "
                                "basis of all credits in the window.")
        blocks, basis = _freeze_blocks(accounts, trace)
        empty = [b["account_id"] for b in blocks if b["transactions_cited"] == 0]
        if empty:
            raise ApiError("VALIDATION_FAILED",
                           "No traced credit into " + ", ".join(empty) + " in this trace.",
                           detail={"accounts": empty},
                           hint="Those accounts were not reached by the trace; remove them "
                                "or omit trace_id.")
        doc = documents.build_freeze_requisition(c, blocks, STORE.fingerprint, seq,
                                                 basis=basis,
                                                 trace_id=trace_id,
                                                 victim=trace.get("victim_account") if trace
                                                 else c.get("victim_account"))
    else:
        req = None
        rid = body.get("requisition_id")
        reqs = [d for d in c.get("documents", []) if d.get("type") == "FREEZE_REQUISITION"]
        if rid:
            req = _find_document(c, rid)
        elif reqs:
            req = reqs[-1]
        if kind == "COVERING_LETTER":
            if not req:
                raise ApiError("DOCUMENT_NOT_FOUND",
                               "A covering letter forwards a freeze requisition, and this "
                               "case has none yet.",
                               hint="Generate the freeze requisition first.")
            doc = documents.build_covering_letter(c, req, body.get("bank_name"), seq)
        else:
            doc = documents.build_victim_acknowledgement(c, req, seq)

    _store_document(c, doc)
    rendered = _render(doc, format, request)
    return rendered if rendered is not None else ok(request, t, doc, status=201)


@router.get("/cases/{case_id}/documents")
def list_documents(request: Request, case_id: str):
    """Documents issued on this case, newest last."""
    t = time.perf_counter()
    c = _case(case_id)
    out = [{k: d.get(k) for k in ("document_id", "type", "reference", "title",
                                  "generated_at", "dataset_fingerprint")}
           for d in c.get("documents", [])]
    return ok(request, t, {"case_id": case_id, "documents": out,
                           "pdf_available": documents.PDF_AVAILABLE})


@router.get("/cases/{case_id}/documents/{document_id}")
def get_document(request: Request, case_id: str, document_id: str,
                 format: str = Query("json", pattern="^(json|html|pdf)$")):
    """Re-serve a stored document as json, html or pdf."""
    t = time.perf_counter()
    c = _case(case_id)
    doc = _find_document(c, document_id)
    rendered = _render(doc, format, request)
    return rendered if rendered is not None else ok(request, t, doc)


# --------------------------------------------------------------- reports
@router.get("/reports/trace/{trace_id}")
def trace_report(request: Request, trace_id: str,
                 case_id: str | None = Query(None),
                 format: str = Query("pdf", pattern="^(json|html|pdf)$")):
    """The whole trace as a signed PDF report."""
    t = time.perf_counter()
    p = investigate.TRACES.get(trace_id)
    if not p:
        raise ApiError("TRACE_NOT_FOUND", "That trace is no longer in memory.",
                       hint="Re-run the trace, then export again.")
    c = case_store.load(case_id) if case_id else None
    doc = documents.build_trace_report(c, p, STORE.fingerprint)
    rendered = _render(doc, format, request)
    return rendered if rendered is not None else ok(request, t, doc)


@router.get("/reports/account/{account_id}")
def account_report(request: Request, account_id: str,
                   case_id: str | None = Query(None),
                   format: str = Query("pdf", pattern="^(json|html|pdf)$")):
    """One account's observed behaviour as a signed PDF report."""
    t = time.perf_counter()
    _need_dataset()
    i = _acct(account_id)
    acct = _account_payload(account_id, i)
    rows = STORE.db.execute(
        "SELECT Transaction_ID, Sender_Account, Receiver_Account, Sender_IFSC, "
        "Receiver_IFSC, amount_f, timestamp, payment_mode, Narration, IP_Address, "
        "device_type, source_row_id, dup_txn_id, is_foreign_ip, is_automation_device, "
        "narr_crypto, narr_wallet, narr_cashout FROM txn WHERE Sender_Account = ? OR "
        "Receiver_Account = ? ORDER BY timestamp LIMIT 150",
        [account_id, account_id]).fetchall()
    from ..core.store import _txn_payload
    txns = [_txn_payload(r) for r in rows]
    c = case_store.load(case_id) if case_id else None
    doc = documents.build_account_report(c, acct, txns, STORE.fingerprint)
    rendered = _render(doc, format, request)
    return rendered if rendered is not None else ok(request, t, doc)


# ------------------------------------------------------------ bank hook
@router.get("/bank/status")
def bank_status(request: Request):
    """Whether a bank endpoint is configured. Never claims a connection it lacks."""
    t = time.perf_counter()
    return ok(request, t, bank_gateway.status())


@router.get("/bank/history")
def bank_history(request: Request, limit: int = Query(50, ge=1, le=500)):
    """The audit log of every transmission attempt, successful or not."""
    t = time.perf_counter()
    return ok(request, t, {"attempts": bank_gateway.history(limit)})


@router.post("/bank/freeze")
async def bank_freeze(request: Request):
    """Transmit a generated requisition to a configured bank endpoint.

    With no endpoint configured this returns 409 BANK_NOT_CONNECTED. It never
    reports a freeze that did not happen.
    """
    t = time.perf_counter()
    body = await request.json()
    case_id, document_id = body.get("case_id"), body.get("document_id")
    if not case_id or not document_id:
        raise ApiError("VALIDATION_FAILED", "case_id and document_id are required.")
    c = _case(case_id)
    doc = _find_document(c, document_id)
    if doc["type"] != "FREEZE_REQUISITION":
        raise ApiError("UNSUPPORTED_DOCUMENT_TYPE",
                       "Only a freeze requisition can be transmitted to a bank.",
                       detail={"type": doc["type"]})
    payload = {
        "reference": doc["reference"], "case_id": case_id,
        "document_id": doc["document_id"], "legal_basis": doc["legal_basis"],
        "dataset_fingerprint": doc["dataset_fingerprint"],
        "requested_by": doc["officer"],
        "accounts": [{"account_id": b["account_id"], "bank": b["bank"],
                      "amount": str(b["credited_total"]),
                      "transactions_cited": b["transactions_cited"]}
                     for b in doc["accounts"]],
    }
    try:
        result = bank_gateway.send_freeze(payload)
    except ConnectionError:
        raise ApiError("BANK_NOT_CONNECTED",
                       "No bank endpoint is configured, so nothing was transmitted.",
                       detail=bank_gateway.status(),
                       hint="Set ABHEDYA_BANK_URL to a demo bank server, or serve the "
                            "printed requisition by hand.")
    except Exception as ex:                                # noqa: BLE001
        raise ApiError("BANK_UNREACHABLE",
                       "The configured bank endpoint could not be reached. Nothing was "
                       "frozen.",
                       detail={"error": f"{type(ex).__name__}: {ex}"[:200]})
    case_store.add_diary(
        c, f"Freeze requisition {doc['reference']} transmitted to the configured bank "
           f"endpoint; outcome {result['outcome']}.",
        c.get("officer", "Investigating Officer"), kind="ACTION")
    return ok(request, t, result, status=201)


# --------------------------------------------------------------- evaluation
# These were 501 stubs while the system had no way to know whether labels
# existed. They now ASK: ground_truth.discover() looks for a label file, and
# the answer decides what is published. With labels, real metrics. Without
# them, an explicit "unavailable" that names where we looked - never a zero,
# never a placeholder, never an invented accuracy.
_NO_TRUTH = ("No ground-truth label file was found, so accuracy, precision, recall, F1 "
             "and the confusion matrix cannot be computed. Publishing a number here "
             "would be fabrication.")


def _eval_context():
    """(ground_truth, account_ids, scores) for the loaded dataset."""
    from ..core import ground_truth as gtm
    gt = gtm.discover()
    if not STORE.ready:
        return gt, [], None
    import numpy as np
    ids = [STORE.aid(i) for i in range(STORE.n_accounts)]
    return gt, ids, np.asarray(STORE.mri, dtype=float)


def _operating_threshold(scores, requested: float | None):
    """Where to cut the ranking for a binary prediction.

    Default is the HIGH band edge, which is a published decision in config.py,
    not a number chosen after seeing the labels.
    """
    if requested is not None:
        return float(requested)
    from ..config import MRI_BANDS
    return float(next(lo for name, lo, hi in MRI_BANDS if name == "HIGH"))


@router.get("/eval/summary")
def eval_summary(request: Request, threshold: float | None = None):
    """Detection metrics when labels exist; an explicit refusal when they do not."""
    t = time.perf_counter()
    from ..core import evaluate as ev
    gt, ids, scores = _eval_context()
    if not gt.available:
        return ok(request, t, ev.unavailable(_NO_TRUTH, gt.searched) | {
            "ground_truth_search": gt.payload()})
    _need_dataset()
    thr = _operating_threshold(scores, threshold)
    res = ev.evaluate(ids, scores, gt.labels, thr)
    return ok(request, t, {"ground_truth": gt.payload(), **res})


@router.get("/eval/confusion-matrix")
def eval_confusion(request: Request, threshold: float | None = None):
    """Confusion matrix at an operating threshold, if labels exist."""
    t = time.perf_counter()
    from ..core import evaluate as ev
    gt, ids, scores = _eval_context()
    if not gt.available:
        return ok(request, t, ev.unavailable(_NO_TRUTH, gt.searched))
    _need_dataset()
    thr = _operating_threshold(scores, threshold)
    res = ev.evaluate(ids, scores, gt.labels, thr)
    return ok(request, t, {"confusion": res["confusion"], "errors": res["errors"],
               "evaluated_accounts": res["evaluated_accounts"],
               "ground_truth": gt.payload()})


@router.get("/eval/ranking")
def eval_ranking(request: Request):
    """Precision@K and Recall@K - the two the brief insists are not the same.

    Precision@K: of the top K we ranked, how many are labelled positive.
    Recall@K:    of all labelled positives, how many are in the top K.
    """
    t = time.perf_counter()
    from ..core import evaluate as ev
    gt, ids, scores = _eval_context()
    if not gt.available:
        return ok(request, t, ev.unavailable(_NO_TRUTH, gt.searched))
    _need_dataset()
    res = ev.evaluate(ids, scores, gt.labels, _operating_threshold(scores, None))
    return ok(request, t, {"ranking": res["ranking"], "actual_positive": res["actual_positive"],
               "definitions": {
                   "precision_at_k": "of the top K ranked accounts, the share labelled positive",
                   "recall_at_k": "of all labelled positives, the share inside the top K"}})


@router.get("/eval/curves")
def eval_curves(request: Request):
    """ROC and precision-recall curves, computed backend-side."""
    t = time.perf_counter()
    from ..core import evaluate as ev
    gt, ids, scores = _eval_context()
    if not gt.available:
        return ok(request, t, ev.unavailable(_NO_TRUTH, gt.searched))
    _need_dataset()
    res = ev.evaluate(ids, scores, gt.labels, _operating_threshold(scores, None))
    return ok(request, t, {"roc": res["curves"]["roc"], "pr": res["curves"]["pr"],
               "roc_auc": res["roc_auc"], "pr_auc": res["pr_auc"],
               "pr_baseline": res["pr_baseline"],
               "note": res["priority_note"]})


@router.get("/eval/threshold-sweep")
def eval_sweep(request: Request):
    """Metrics across the score range, for choosing an operating point."""
    t = time.perf_counter()
    from ..core import evaluate as ev
    gt, ids, scores = _eval_context()
    if not gt.available:
        return ok(request, t, ev.unavailable(_NO_TRUTH, gt.searched))
    _need_dataset()
    res = ev.evaluate(ids, scores, gt.labels, _operating_threshold(scores, None))
    return ok(request, t, {"sweep": res["threshold_sweep"],
               "warning": ("Choose an operating threshold on validation data. "
                           "Reading the best row off this table and reporting it as "
                           "test performance is tuning on the test set.")})


@router.get("/eval/layers")
def eval_layers(request: Request):
    """Layer correctness needs per-account layer labels, which no file provides."""
    t = time.perf_counter()
    t = time.perf_counter()
    from ..core import evaluate as ev
    gt, _, _ = _eval_context()
    return ok(request, t, ev.unavailable(
        "Layer correctness would need ground-truth L1/L2/L3 labels per victim trace. "
        "No such labels exist. Layer is also victim-relative, so a global layer label "
        "would be meaningless.", gt.searched))


@router.post("/eval/self-validation")
def eval_self(request: Request):
    """Deterministic typology tests - what replaces accuracy when labels are absent."""
    t = time.perf_counter()
    from ..core import synthetic_tests
    return ok(request, t, synthetic_tests.run())
