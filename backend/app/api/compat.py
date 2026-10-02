"""Contract-compatibility routes.

`docs/BACKEND_API.md` is the binding contract. The implementation grew its own
naming in places (`/api/system/health` instead of `/api/health`, risk and graph
data folded into the account and trace payloads instead of standing on their
own). Rather than let the document drift away from the server, every path the
contract names is served here.

Three rules for this module:

1. **No new analysis.** Every alias reshapes data the canonical routes already
   produce - the same features, the same risk object, the same rows. If an
   alias had to invent a number it is not implemented.
2. **Unbuilt contract routes answer honestly.** They return `501
   NOT_IMPLEMENTED` with the reason, never an empty success or a plausible
   fabrication. `/api/eval/*` is the important case: there is no labelled
   ground truth in this dataset, so accuracy is never published.
3. **Aliases are thin.** Business logic stays in `core/`; the canonical route
   stays the one the frontend calls.
"""
from __future__ import annotations

import time

from fastapi import APIRouter, Query, Request
from starlette.responses import Response

from ..config import (ARTIFACT_DIR, AUTOMATION_DEVICES, CASHOUT_KEYWORDS,
                      CRYPTO_KEYWORDS, FOREIGN_IP_PREFIXES,
                      TERMINAL_SIGNAL_SOLO_CAP, WALLET_KEYWORDS)
from ..errors import ApiError, ok
from ..core import cases as case_store
from ..core import investigate, risk
from ..core.store import STORE
from . import routes as R

router = APIRouter(prefix="/api")

ALIAS_NOTE = ("Contract alias. The canonical route is {canonical}; this path exists "
              "because docs/BACKEND_API.md names it.")


def _alias(canonical: str) -> dict:
    return {"canonical_route": canonical, "note": ALIAS_NOTE.format(canonical=canonical)}


# --------------------------------------------------------------- service
@router.get("/health")
def health_alias(request: Request):
    """Contract alias of `GET /api/system/health`."""
    t = time.perf_counter()
    from ..config import API_VERSION
    return ok(request, t, {"status": "ok", "api_version": API_VERSION,
                           "dataset_state": STORE.state,
                           "_alias": _alias("/api/system/health")})


# --------------------------------------------------------------- ingestion
@router.get("/ingest/status/{job_id}")
def ingest_status_alias(request: Request, job_id: str):
    """Contract alias of `GET /api/ingest/status`.

    This backend runs one ingestion at a time, so a job id identifies the run
    rather than selecting between concurrent ones. An unknown id still returns
    the current state - with a warning saying so, never a silent substitution.
    """
    t = time.perf_counter()
    warn = None
    if STORE.job_id and job_id != STORE.job_id:
        warn = [f"Job {job_id} is not the ingestion this server is tracking "
                f"({STORE.job_id}). The current state is returned instead."]
    elif not STORE.job_id:
        warn = ["No ingestion has been started on this server process; the state below "
                "describes the dataset loaded at boot."]
    return ok(request, t, {
        "job_id": STORE.job_id, "requested_job_id": job_id,
        "state": STORE.state, "current_stage": STORE.stage, "stages": STORE.stages,
        "error": STORE.error, "source_file": STORE.source_path.name if STORE.source_path else None,
        "_alias": _alias("/api/ingest/status"),
    }, warnings=warn)


@router.get("/ingest/manifest")
def ingest_manifest(request: Request):
    """What ingestion actually wrote to disk. Sizes are read from the files."""
    t = time.perf_counter()
    files = []
    if ARTIFACT_DIR.exists():
        for f in sorted(ARTIFACT_DIR.iterdir()):
            if f.is_file():
                st = f.stat()
                files.append({"name": f.name, "bytes": st.st_size,
                              "modified": time.strftime("%Y-%m-%dT%H:%M:%S",
                                                        time.localtime(st.st_mtime))})
    return ok(request, t, {
        "state": STORE.state,
        "source_file": STORE.source_path.name if STORE.source_path else None,
        "dataset_fingerprint": STORE.fingerprint,
        "rows": STORE.n_rows, "accounts": STORE.n_accounts,
        "stages": STORE.stages,
        "artifacts": files,
        "artifact_dir": str(ARTIFACT_DIR),
        "note": "Row counts come from the loaded dataset; file sizes are read from disk. "
                "Nothing here is estimated.",
    })


# --------------------------------------------------------------- accounts
@router.get("/accounts/{account_no}/exists")
def account_exists(request: Request, account_no: str):
    """Cheap existence probe - the one account route that does not 404."""
    t = time.perf_counter()
    R._need_dataset()
    from ..config import ACCOUNT_PATTERN
    if not R.ACCT_RE.match(account_no):
        raise ApiError("INVALID_ACCOUNT_FORMAT", "Account numbers are 12-digit strings.",
                       detail={"received": account_no, "pattern": ACCOUNT_PATTERN})
    i = STORE.idx(account_no)
    return ok(request, t, {"account_id": account_no, "exists": i is not None,
                           "note": "Absence means the account does not appear in this "
                                   "dataset. It says nothing about the account itself."})


@router.get("/accounts/{account_no}/classification")
def classification_global(request: Request, account_no: str):
    """Global role hint. Deliberately NOT a layer - layer is per investigation."""
    t = time.perf_counter()
    R._need_dataset()
    i = R._acct(account_no)
    role = risk.role_assessment(i, STORE.F, STORE.P)
    return ok(request, t, {
        "account_id": account_no,
        "scope": "GLOBAL_HINT",
        "role": role,
        "is_hub": bool(STORE.is_hub[i]),
        "layer": None,
        "layer_note": "No global layer exists. Layer is assigned per investigation, "
                      "relative to that investigation's victim. Use "
                      "/api/cases/{case_id}/accounts/{account_no}/classification.",
        "_alias": _alias("/api/accounts/{account_id} -> role"),
    })


@router.get("/cases/{case_id}/accounts/{account_no}/classification")
def classification_case(request: Request, case_id: str, account_no: str):
    """Case-relative classification: the layer this account held in the case's trace."""
    t = time.perf_counter()
    R._need_dataset()
    c = R._case(case_id)
    R._acct(account_no)
    trace_ids = [tr.get("trace_id") for tr in c.get("traces", []) if tr.get("trace_id")]
    trace = None
    for tid in reversed(trace_ids):
        trace = investigate.TRACES.get(tid)
        if trace:
            break
    if trace is None:
        raise ApiError("TRACE_NOT_FOUND",
                       "This case has no trace in memory, so there is no case-relative "
                       "classification to report.",
                       detail={"case_id": case_id, "traces_recorded": len(trace_ids)},
                       hint="Re-run the trace from the victim account.")
    node = next((n for n in trace["nodes"] if n["account_id"] == account_no), None)
    if node is None:
        raise ApiError("NO_PATH_FOUND",
                       f"Account {account_no} was not reached by this case's trace.",
                       detail={"trace_id": trace["trace_id"],
                               "victim_account": trace["victim_account"]},
                       hint="An account can be high risk globally and still be outside "
                            "this victim's money flow.")
    return ok(request, t, {
        "case_id": case_id, "account_id": account_no,
        "scope": "CASE_RELATIVE", "trace_id": trace["trace_id"],
        "victim_account": trace["victim_account"],
        "layer": node["layer"], "layer_reason": node["layer_reason"],
        "hop_distance": node["hop_distance"],
        "attributed_value": node["attributed_value"],
        "role": node["role"], "role_reasons": node["role_reasons"],
        "mri": node["mri"], "band": node["band"],
    })


@router.get("/accounts/{account_no}/terminal-evidence")
def terminal_evidence(request: Request, account_no: str, limit: int = Query(50, ge=1, le=500)):
    """The rows behind the terminal-behaviour signals, cited individually.

    The flags are read from the facts table written at ingestion - the same
    columns the feature builder counted - so the numbers here and in the risk
    object cannot disagree.
    """
    t = time.perf_counter()
    R._need_dataset()
    i = R._acct(account_no)
    F = STORE.F
    rows = STORE.db.execute(
        "SELECT source_row_id, Transaction_ID, Sender_Account, Receiver_Account, "
        "       amount_f, ts_epoch, payment_mode, narration, ip_address, device_type, "
        "       is_foreign_ip, is_automation_device, narr_crypto, narr_wallet, narr_cashout "
        "FROM txn WHERE Sender_Account = ? AND (is_foreign_ip OR is_automation_device "
        "  OR narr_crypto OR narr_wallet OR narr_cashout) "
        "ORDER BY ts_epoch LIMIT ?", [account_no, limit]).fetchall()
    cited = [{"source_row_id": int(r[0]), "transaction_id": r[1],
              "from": r[2], "to": r[3], "amount": round(float(r[4]), 2),
              "ts_epoch": int(r[5]), "payment_mode": r[6], "narration": r[7],
              "ip_address": r[8], "device_type": r[9],
              "flags": [k for k, v in (("foreign_ip", r[10]), ("automation_device", r[11]),
                                       ("crypto_narration", r[12]), ("wallet_narration", r[13]),
                                       ("cashout_narration", r[14])) if v]}
             for r in rows]
    families = int(F["distinct_signal_families"][i])
    return ok(request, t, {
        "account_id": account_no,
        "counts": {"foreign_ip_txns": int(F["is_foreign_ip_txns"][i]),
                   "automation_txns": int(F["is_automation_device_txns"][i]),
                   "crypto_txns": int(F["narr_crypto_txns"][i]),
                   "wallet_txns": int(F["narr_wallet_txns"][i]),
                   "cashout_txns": int(F["narr_cashout_txns"][i]),
                   "distinct_families": families},
        "rows_cited": cited, "rows_returned": len(cited), "limit": limit,
        "definitions": {"foreign_ip_prefixes": list(FOREIGN_IP_PREFIXES),
                        "automation_devices": list(AUTOMATION_DEVICES),
                        "crypto_keywords": list(CRYPTO_KEYWORDS),
                        "wallet_keywords": list(WALLET_KEYWORDS),
                        "cashout_keywords": list(CASHOUT_KEYWORDS)},
        "cap": {"terminal_signal_solo_cap": TERMINAL_SIGNAL_SOLO_CAP,
                "meaning": "Terminal signals alone can never push an account into the "
                           "CRITICAL band."},
        "verdict": None,
        "possible_readings": [
            "transfers consistent with exit or conversion behaviour",
            "a VPN, hosting provider or integration used by an ordinary customer",
            "test or batch traffic",
        ] if families else [],
        "disclaimer": "These are observations about rows, not a finding about a person.",
    })


# --------------------------------------------------------------- graph
def _neighbourhood(account_no: str, limit: int) -> dict:
    i = R._acct(account_no)
    edges = STORE.db.execute(
        "SELECT source_row_id, Sender_Account, Receiver_Account, amount_f, ts_epoch "
        "FROM txn WHERE Sender_Account = ? OR Receiver_Account = ? "
        "ORDER BY amount_f DESC LIMIT ?", [account_no, account_no, limit]).fetchall()
    ids = {account_no} | {e[1] for e in edges} | {e[2] for e in edges}
    nodes = []
    for a in sorted(ids):
        j = STORE.idx(a)
        if j is None:
            continue
        s = risk.score_account(j, STORE.F, STORE.P, STORE.cooccurrence_rate)
        nodes.append({"account_id": a, "mri": s["mri"], "band": s["band"],
                      "role": risk.role_assessment(j, STORE.F, STORE.P)["role"],
                      "is_hub": bool(STORE.is_hub[j]),
                      "in_degree": int(STORE.F["in_degree"][j]),
                      "out_degree": int(STORE.F["out_degree"][j]),
                      "is_centre": a == account_no})
    return {
        "centre": account_no,
        "nodes": nodes,
        "edges": [{"edge_id": f"e{int(e[0])}", "source_row_id": int(e[0]),
                   "from": e[1], "to": e[2], "amount": round(float(e[3]), 2),
                   "ts_epoch": int(e[4])} for e in edges],
        "node_count": len(nodes), "edge_count": len(edges),
        "truncated": len(edges) >= limit,
        "truncation_reason": "MAX_EDGES" if len(edges) >= limit else None,
        "layer_note": "A neighbourhood has no layers. Layer only exists relative to a "
                      "victim, which this view does not have.",
        "attribution_note": "Edges here are raw transactions, not value attributed from a "
                            "victim. Use POST /api/trace for attributed flow.",
    }


@router.get("/graph/rings")
def graph_rings(request: Request):
    """Ring and cycle detection: specified (11.3, P2) but not built."""
    raise ApiError("NOT_IMPLEMENTED",
                   "Ring and cycle detection is specified but not built.",
                   detail={"specified_in": "BACKEND_API.md 11.3 (P2)"},
                   hint="Nothing in the UI depends on it; it is not approximated here "
                        "because a wrong ring would be worse than no ring.")


@router.get("/graph/{account_no}")
def graph_neighbourhood(request: Request, account_no: str,
                        limit: int = Query(200, ge=1, le=1500)):
    """One-hop neighbourhood around an account, largest transfers first."""
    t = time.perf_counter()
    R._need_dataset()
    return ok(request, t, _neighbourhood(account_no, limit))


@router.get("/graph/{account_no}/expand")
def graph_expand(request: Request, account_no: str,
                 limit: int = Query(100, ge=1, le=1500)):
    """Expand one node of a displayed graph. Same shape as the neighbourhood."""
    t = time.perf_counter()
    R._need_dataset()
    p = _neighbourhood(account_no, limit)
    p["expanded"] = account_no
    return ok(request, t, p)


# --------------------------------------------------------------- timeline
@router.get("/timeline")
def timeline_alias(request: Request, trace_id: str = Query(...),
                   buckets: int = Query(180, ge=10, le=2000)):
    """Contract alias of `GET /api/trace/{trace_id}/timeline`.

    A timeline is always the timeline *of an investigation*; there is no global
    timeline, so `trace_id` is required rather than defaulted.
    """
    t = time.perf_counter()
    p = investigate.TRACES.get(trace_id)
    if not p:
        raise ApiError("TRACE_NOT_FOUND", "That trace is no longer in memory.",
                       detail={"trace_id": trace_id})
    out = investigate.timeline(p, buckets)
    out["_alias"] = _alias("/api/trace/{trace_id}/timeline")
    return ok(request, t, out)


# --------------------------------------------------------------- risk
@router.get("/risk/distribution")
def risk_distribution_alias(request: Request):
    """Contract alias of `GET /api/accounts/risk-distribution`."""
    return R.risk_distribution(request)


@router.get("/risk/{account_no}")
def risk_alias(request: Request, account_no: str):
    """Contract alias of the `risk` block inside `GET /api/accounts/{account_id}`."""
    t = time.perf_counter()
    R._need_dataset()
    i = R._acct(account_no)
    s = risk.score_account(i, STORE.F, STORE.P, STORE.cooccurrence_rate)
    s["account_id"] = account_no
    s["_alias"] = _alias("/api/accounts/{account_id} -> risk")
    return ok(request, t, s)


@router.post("/risk/batch")
async def risk_batch(request: Request):
    """Score up to 100 accounts in one call. Same scorer, no shortcuts."""
    t = time.perf_counter()
    R._need_dataset()
    body = await request.json() if await request.body() else {}
    accounts = body.get("accounts") or []
    if not isinstance(accounts, list) or not accounts:
        raise ApiError("VALIDATION_FAILED", "Provide a non-empty 'accounts' list.")
    if len(accounts) > 100:
        raise ApiError("VALIDATION_FAILED", "At most 100 accounts per batch.",
                       detail={"received": len(accounts), "max": 100})
    out, unknown = [], []
    for a in accounts:
        i = STORE.idx(a) if R.ACCT_RE.match(str(a)) else None
        if i is None:
            unknown.append(a)
            continue
        s = risk.score_account(i, STORE.F, STORE.P, STORE.cooccurrence_rate)
        out.append({"account_id": a, "mri": s["mri"], "band": s["band"],
                    "reason": s["reason"]})
    return ok(request, t, {"scored": out, "count": len(out),
                           "not_in_dataset": unknown,
                           "disclaimer": "The index ranks where to look first. It is not "
                                         "a finding of wrongdoing."})


# --------------------------------------------------------------- evidence basket
@router.post("/evidence/basket")
async def basket_add(request: Request):
    """Contract alias of `POST /api/cases/{case_id}/evidence` (case_id in the body)."""
    t = time.perf_counter()
    body = await request.json() if await request.body() else {}
    case_id = body.get("case_id")
    if not case_id:
        raise ApiError("VALIDATION_FAILED", "case_id is required in the body.")
    items = body.get("items") or ([body["item"]] if body.get("item") else [])
    if not items:
        raise ApiError("VALIDATION_FAILED", "Provide 'items' to add to the basket.")
    c = R._case(case_id)
    try:
        c = case_store.add_evidence(c, items, STORE.fingerprint)
    except ValueError:
        raise ApiError("FINGERPRINT_MISMATCH",
                       "That evidence was built on a different dataset.",
                       detail={"current": STORE.fingerprint}) from None
    return ok(request, t, {"case_id": case_id, "basket_size": len(c["basket"]),
                           "basket": c["basket"][-len(items):]}, status=201)


@router.get("/evidence/basket/{case_id}")
def basket_get(request: Request, case_id: str):
    """Read a case's evidence basket by case id."""
    t = time.perf_counter()
    c = R._case(case_id)
    return ok(request, t, {"case_id": case_id, "items": c.get("basket", []),
                           "count": len(c.get("basket", []))})


@router.delete("/evidence/basket/{case_id}/{item_id}")
def basket_delete_item(request: Request, case_id: str, item_id: str):
    """Remove one basket item. The diary records the removal - nothing vanishes."""
    t = time.perf_counter()
    c = R._case(case_id)
    before = len(c.get("basket", []))
    item = next((i for i in c.get("basket", []) if i.get("basket_item_id") == item_id), None)
    if item is None:
        raise ApiError("EVIDENCE_NOT_FOUND", f"No basket item {item_id} in {case_id}.",
                       detail={"case_id": case_id, "item_id": item_id})
    c["basket"] = [i for i in c["basket"] if i.get("basket_item_id") != item_id]
    case_store.add_diary(c, f"Removed evidence item {item_id} ({item.get('claim_type')}) "
                            f"from the basket.", "SYSTEM", kind="ACTION")
    return ok(request, t, {"case_id": case_id, "removed": item_id,
                           "basket_size": len(c["basket"]), "was": before})


@router.delete("/evidence/basket/{case_id}")
def basket_clear(request: Request, case_id: str):
    """Empty a case's basket. The diary records how many items went."""
    t = time.perf_counter()
    c = R._case(case_id)
    n = len(c.get("basket", []))
    c["basket"] = []
    case_store.add_diary(c, f"Cleared the evidence basket ({n} item(s)).", "SYSTEM",
                         kind="ACTION")
    return ok(request, t, {"case_id": case_id, "cleared": n, "basket_size": 0})


# --------------------------------------------------------------- documents
def _find_any_document(document_id: str) -> tuple[dict, dict]:
    for row in case_store.listing():
        c = case_store.load(row["case_id"])
        if not c:
            continue
        for d in c.get("documents", []):
            if d.get("document_id") == document_id:
                return c, d
    raise ApiError("DOCUMENT_NOT_FOUND", f"No document {document_id} on any case.",
                   detail={"document_id": document_id})


@router.get("/documents/{document_id}")
def document_alias(request: Request, document_id: str,
                   format: str = Query("json", pattern="^(json|html|pdf)$")):
    """Contract alias of `GET /api/cases/{case_id}/documents/{document_id}`."""
    t = time.perf_counter()
    _c, doc = _find_any_document(document_id)
    rendered = R._render(doc, format, request)
    return rendered if rendered is not None else ok(request, t, doc)


@router.get("/documents/{document_id}/meta")
def document_meta(request: Request, document_id: str):
    """Metadata only, so a client never has to download a PDF to describe it."""
    t = time.perf_counter()
    c, doc = _find_any_document(document_id)
    return ok(request, t, {
        "document_id": doc.get("document_id"), "type": doc.get("type"),
        "reference": doc.get("reference"), "title": doc.get("title"),
        "case_id": c.get("case_id"), "generated_at": doc.get("generated_at"),
        "dataset_fingerprint": doc.get("dataset_fingerprint"),
        "accounts": [b.get("account_id") for b in doc.get("blocks", [])],
        "rows_cited": sum(len(b.get("source_row_ids", [])) for b in doc.get("blocks", [])),
        "formats": ["json", "html"] + (["pdf"] if R.documents.PDF_AVAILABLE else []),
        "pdf_available": R.documents.PDF_AVAILABLE,
    })


# --------------------------------------------------------------- cases
@router.get("/cases/{case_id}/holdings")
def case_holdings(request: Request, case_id: str):
    """Observed residual per account in the case's trace - the freeze-picker view.

    This is NOT a bank balance and the response says so in the payload, because
    an officer reading a number next to the word "holdings" will otherwise
    assume it is money still sitting in the account.
    """
    t = time.perf_counter()
    R._need_dataset()
    c = R._case(case_id)
    trace = None
    for tr in reversed(c.get("traces", [])):
        trace = investigate.TRACES.get(tr.get("trace_id"))
        if trace:
            break
    if trace is None:
        raise ApiError("TRACE_NOT_FOUND",
                       "No trace is in memory for this case, so there is nothing to "
                       "list for freezing.",
                       hint="Re-run the trace from the victim account.")
    # Two different, easily confused figures - so both are returned, named.
    #   traced_credit_in     : sum of the traced transfers INTO this account.
    #                          This is what a freeze requisition quotes.
    #   attributed_value     : the victim's seed amount attenuated through splits.
    credit: dict[str, float] = {}
    cited: dict[str, int] = {}
    for ed in trace["edges"]:
        credit[ed["to"]] = credit.get(ed["to"], 0.0) + float(ed["amount"])
        cited[ed["to"]] = cited.get(ed["to"], 0) + 1
    out = []
    for n in trace["nodes"]:
        if n["layer"] == "VICTIM":
            continue
        i = STORE.idx(n["account_id"])
        if i is None:
            continue
        out.append({
            "account_id": n["account_id"], "layer": n["layer"],
            "band": n["band"], "mri": n["mri"], "role": n["role"],
            "traced_credit_in": round(credit.get(n["account_id"], 0.0), 2),
            "traced_transactions": cited.get(n["account_id"], 0),
            "attributed_value": n["attributed_value"],
            "observed_in": round(float(STORE.F["total_in_amount"][i]), 2),
            "observed_out": round(float(STORE.F["total_out_amount"][i]), 2),
            "observed_residual": round(float(STORE.F["net_balance"][i]), 2),
        })
    out.sort(key=lambda r: r["traced_credit_in"], reverse=True)
    return ok(request, t, {
        "case_id": case_id, "trace_id": trace["trace_id"],
        "victim_account": trace["victim_account"],
        "accounts": out, "count": len(out),
        "figures": {
            "traced_credit_in": "Sum of the traced transfers into this account in this "
                                "trace. This is the figure the freeze requisition quotes, "
                                "and the only one tied to a list of source_row_ids.",
            "attributed_value": "The victim's seed amount carried forward and divided at "
                                "each split. It is an attribution model, not a sum of "
                                "transfers, and it is always smaller than or equal to the "
                                "traced credit.",
            "observed_residual": "Inflow minus outflow within the dataset window. It is "
                                 "NOT the bank balance and must never be sent to a bank "
                                 "as one.",
        },
    })


@router.patch("/cases/{case_id}")
async def case_patch(request: Request, case_id: str):
    """Contract alias of `POST /api/cases/{case_id}/details`."""
    return await R.update_case_details(request, case_id)


@router.delete("/cases/{case_id}")
def case_delete(request: Request, case_id: str):
    """Refused by design: case records are append-only."""
    raise ApiError("NOT_IMPLEMENTED",
                   "Case records are append-only; they cannot be deleted through the API.",
                   detail={"case_id": case_id},
                   hint="Set the case status to CLOSED with POST /api/cases/{case_id}"
                        "/details. The diary and evidence must survive for provenance.")


# --------------------------------------------------------------- benchmarks
@router.get("/benchmarks")
def benchmarks(request: Request):
    """Measured benchmarks, or null. Never an estimate, never a target."""
    t = time.perf_counter()
    b = R._bench()
    return ok(request, t, {
        "benchmarks": b,
        "measured": bool(b) and not b.get("stale"),
        "dataset_fingerprint": STORE.fingerprint,
        "note": "null means nobody has run `make bench` against this dataset. An "
                "unmeasured benchmark is never published.",
    })


@router.post("/benchmarks/run")
def benchmarks_run(request: Request):
    """Refused by design: benchmarks are measured from the CLI, not the API."""
    raise ApiError("NOT_IMPLEMENTED",
                   "Benchmarks are run from the command line, not from the API.",
                   hint="Run `make bench`, which writes data/artifacts/bench.json; "
                        "GET /api/benchmarks then serves the measured file.")
