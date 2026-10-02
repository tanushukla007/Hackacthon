"""Outbound bank connector — the hook for a future demo bank server.

Nothing here pretends to freeze anything. The connector is DISCONNECTED unless
an operator explicitly configures an endpoint:

    export ABHEDYA_BANK_URL=http://localhost:9000
    export ABHEDYA_BANK_TOKEN=<optional bearer token>

With no endpoint configured, send_freeze() refuses and the UI shows the request
as NOT SENT. There is no simulated success path: a freeze that did not happen
must never look like a freeze that did.

Expected contract of the counterpart server (deliberately small, so a demo bank
can be written in an afternoon):

    POST {ABHEDYA_BANK_URL}/freeze
      {
        "reference":  "CASE-2026-001/FRZ/01",
        "case_id":    "CASE-2026-001",
        "document_id": "doc_...",
        "requested_by": {"officer": "...", "police_station": "..."},
        "legal_basis": "Section 94 BNSS, 2023 (...)",
        "dataset_fingerprint": "sha256:...",
        "accounts": [{"account_id": "4029...", "bank": "HDFC0001234",
                      "amount": "125000.00", "transactions_cited": 12}]
      }
    -> 200 {"accepted": true, "bank_reference": "...", "per_account": [...]}

Every attempt, successful or not, is appended to data/cases/bank_requests.jsonl
so the audit trail survives a restart.
"""
from __future__ import annotations

import json, os, time, urllib.error, urllib.request
from pathlib import Path

from ..config import CASE_DIR

LOG_PATH: Path = CASE_DIR / "bank_requests.jsonl"
TIMEOUT_S = 10


def _endpoint() -> str | None:
    url = (os.environ.get("ABHEDYA_BANK_URL") or "").strip().rstrip("/")
    return url or None


def status() -> dict:
    url = _endpoint()
    return {
        "connected": bool(url),
        "endpoint": url,
        "auth": bool(os.environ.get("ABHEDYA_BANK_TOKEN")),
        "mode": "LIVE_ENDPOINT" if url else "DISCONNECTED",
        "note": (
            "A bank endpoint is configured. Freeze requests will be transmitted to it "
            "and its reply is recorded verbatim."
            if url else
            "No bank endpoint is configured, so freeze requests cannot be transmitted. "
            "Documents can still be generated, printed and served by hand. Set "
            "ABHEDYA_BANK_URL to enable transmission."
        ),
        "attempts_logged": _count_log(),
    }


def _count_log() -> int:
    if not LOG_PATH.exists():
        return 0
    return sum(1 for _ in LOG_PATH.open())


def _log(entry: dict) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a") as fh:
        fh.write(json.dumps(entry) + "\n")


def history(limit: int = 50) -> list[dict]:
    if not LOG_PATH.exists():
        return []
    lines = LOG_PATH.read_text().splitlines()[-limit:]
    out = []
    for ln in lines:
        try:
            out.append(json.loads(ln))
        except json.JSONDecodeError:
            continue
    return list(reversed(out))


def send_freeze(payload: dict) -> dict:
    """Transmit a freeze request. Raises ConnectionError when not configured."""
    url = _endpoint()
    attempt = {
        "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "reference": payload.get("reference"),
        "case_id": payload.get("case_id"),
        "document_id": payload.get("document_id"),
        "accounts": [a.get("account_id") for a in payload.get("accounts", [])],
        "endpoint": url,
    }

    if not url:
        attempt |= {"transmitted": False, "outcome": "NOT_CONNECTED"}
        _log(attempt)
        raise ConnectionError("NOT_CONNECTED")

    req = urllib.request.Request(
        f"{url}/freeze",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    token = os.environ.get("ABHEDYA_BANK_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")

    started = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            raw = resp.read().decode()
            body = json.loads(raw) if raw.strip().startswith("{") else {"raw": raw}
            attempt |= {"transmitted": True, "outcome": "DELIVERED",
                        "http_status": resp.status,
                        "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
                        "bank_response": body}
            _log(attempt)
            return attempt
    except urllib.error.HTTPError as ex:
        body = ex.read().decode()[:500]
        attempt |= {"transmitted": True, "outcome": "REJECTED",
                    "http_status": ex.code, "bank_response": {"raw": body}}
        _log(attempt)
        return attempt
    except Exception as ex:                                # noqa: BLE001
        attempt |= {"transmitted": False, "outcome": "UNREACHABLE",
                    "error": f"{type(ex).__name__}: {ex}"[:300]}
        _log(attempt)
        raise
