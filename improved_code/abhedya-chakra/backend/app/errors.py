"""Closed error-code set + the single response envelope (BACKEND_API.md)."""
from __future__ import annotations
import time, uuid
from typing import Any
import orjson
from fastapi import Request
from starlette.responses import Response


class FastJSON(Response):
    """orjson-backed JSON response (avoids FastAPI's deprecated ORJSONResponse)."""
    media_type = "application/json"

    def render(self, content) -> bytes:
        return orjson.dumps(content, option=orjson.OPT_SERIALIZE_NUMPY |
                            orjson.OPT_NON_STR_KEYS)

from .config import API_VERSION

ERROR_CODES: dict[str, int] = {
    "DATASET_NOT_LOADED": 409,
    "INGEST_IN_PROGRESS": 409,
    "INGEST_FAILED": 500,
    "FILE_NOT_FOUND": 404,
    "SCHEMA_MISMATCH": 422,
    "ACCOUNT_NOT_FOUND": 404,
    "INVALID_ACCOUNT_FORMAT": 422,
    "TRANSACTION_NOT_FOUND": 404,
    "AMBIGUOUS_TRANSACTION_ID": 409,
    "ROW_NOT_FOUND": 404,
    "TRACE_NOT_FOUND": 404,
    "INVALID_HOPS": 422,
    "INVALID_TIME_WINDOW": 422,
    "INVALID_AMOUNT": 422,
    "NO_PATH_FOUND": 404,
    "GRAPH_TOO_LARGE": 413,
    "CASE_NOT_FOUND": 404,
    "CASE_EXISTS": 409,
    "EVIDENCE_NOT_FOUND": 404,
    "BASKET_EMPTY": 409,
    "FINGERPRINT_MISMATCH": 409,
    "DOCUMENT_NOT_FOUND": 404,
    "UNSUPPORTED_DOCUMENT_TYPE": 422,
    "VALIDATION_FAILED": 422,
    "PDF_ENGINE_UNAVAILABLE": 503,
    "BANK_NOT_CONNECTED": 409,
    "BANK_UNREACHABLE": 502,
    "RATE_LIMITED": 429,
    "NOT_IMPLEMENTED": 501,
    "INTERNAL_ERROR": 500,
}


class ApiError(Exception):
    def __init__(self, code: str, message: str, detail: Any = None, hint: str | None = None):
        if code not in ERROR_CODES:
            raise KeyError("error code not in the closed set: " + code)
        self.code, self.message, self.detail, self.hint = code, message, detail, hint
        super().__init__(message)


def new_request_id() -> str:
    return "req_" + uuid.uuid4().hex[:16]


def meta(request: Request, started: float, warnings: list[str] | None = None) -> dict:
    from .core.store import STORE
    m = {
        "request_id": getattr(request.state, "request_id", new_request_id()),
        "processing_ms": round((time.perf_counter() - started) * 1000, 2),
        "dataset_fingerprint": STORE.fingerprint,
        "api_version": API_VERSION,
    }
    if warnings:
        m["warnings"] = warnings
    return m


def ok(request: Request, started: float, data: Any, warnings: list[str] | None = None,
       status: int = 200) -> FastJSON:
    return FastJSON(
        {"success": True, "data": data, "meta": meta(request, started, warnings)},
        status_code=status,
    )


def fail(request: Request, started: float, err: ApiError) -> FastJSON:
    body = {
        "success": False,
        "error": {"code": err.code, "message": err.message},
        "meta": meta(request, started),
    }
    if err.detail is not None:
        body["error"]["detail"] = err.detail
    if err.hint:
        body["error"]["hint"] = err.hint
    return FastJSON(body, status_code=ERROR_CODES[err.code])
