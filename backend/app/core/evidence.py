"""
EvidenceObject (DATA_CONTEXT.md §27).

Every claim carries source_row_ids[] and the dataset fingerprint. Money that
reaches a document is recomputed with Decimal from the cited rows.
"""
from __future__ import annotations

import os, time
from decimal import Decimal

_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def ulid(prefix: str) -> str:
    v = int(time.time() * 1000) << 48 | int.from_bytes(os.urandom(6), "big")
    out = ""
    for _ in range(26):
        v, r = divmod(v, 32)
        out = _ALPHABET[r] + out
    return f"{prefix}_{out[-16:]}"


CLAIM_TYPES = ("OBSERVED", "INFERRED", "ASSESSED")
FORBIDDEN = ("criminal", "guilty", "confirmed mule", "fraudster", "proven")


def validate_claim(text: str) -> None:
    low = text.lower()
    for w in FORBIDDEN:
        if w in low:
            raise ValueError(f"forbidden assertion in claim text: '{w}'")


def make_evidence(claim: str, claim_type: str, measurement: dict,
                  source_row_ids: list[int], fingerprint: str,
                  account_id: str | None = None) -> dict:
    if claim_type not in CLAIM_TYPES:
        raise ValueError("claim_type must be OBSERVED / INFERRED / ASSESSED")
    validate_claim(claim)
    return {
        "evidence_id": ulid("ev"),
        "claim": claim,
        "claim_type": claim_type,
        "account_id": account_id,
        "measurement": measurement,
        "source_row_ids": source_row_ids,
        "source_row_count": len(source_row_ids),
        "dataset_fingerprint": fingerprint,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }


def exact_total(rows: list[dict]) -> str:
    """Decimal sum recomputed from the cited rows - never carried forward."""
    total = sum((Decimal(str(round(r["amount"], 2))) for r in rows), Decimal("0.00"))
    return f"{total:.2f}"
