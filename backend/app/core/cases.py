"""Mutable investigator state: cases, evidence baskets, diary. JSON on disk."""
from __future__ import annotations

import json, time
from pathlib import Path

from ..config import CASE_DIR
from .evidence import ulid


def _path(case_id: str) -> Path:
    return CASE_DIR / f"{case_id}.json"


def next_case_id() -> str:
    year = time.strftime("%Y")
    n = len([p for p in CASE_DIR.glob(f"CASE-{year}-*.json")]) + 1
    return f"CASE-{year}-{n:03d}"


def create(title: str, victim_account: str, officer: str, reported_amount: float | None,
           fingerprint: str | None) -> dict:
    case = {
        "case_id": next_case_id(),
        "title": title, "victim_account": victim_account, "officer": officer,
        "reported_amount": reported_amount,
        "status": "OPEN",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "dataset_fingerprint": fingerprint,
        "basket": [], "diary": [], "traces": [], "documents": [],
    }
    _path(case["case_id"]).write_text(json.dumps(case, indent=2))
    return case


def load(case_id: str) -> dict | None:
    p = _path(case_id)
    return json.loads(p.read_text()) if p.exists() else None


def save(case: dict) -> dict:
    _path(case["case_id"]).write_text(json.dumps(case, indent=2))
    return case


def listing() -> list[dict]:
    out = []
    for p in sorted(CASE_DIR.glob("CASE-*.json")):
        c = json.loads(p.read_text())
        out.append({k: c[k] for k in ("case_id", "title", "victim_account", "officer",
                                      "status", "created_at")} |
                   {"evidence_count": len(c["basket"]), "diary_count": len(c["diary"])})
    return out


def add_evidence(case: dict, items: list[dict], fingerprint: str | None) -> dict:
    for it in items:
        if it.get("dataset_fingerprint") and fingerprint and \
           it["dataset_fingerprint"] != fingerprint:
            raise ValueError("FINGERPRINT_MISMATCH")
        it = dict(it)
        it["basket_item_id"] = ulid("itm")
        it["added_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        case["basket"].append(it)
    return save(case)


REF_KINDS = ("accounts", "source_row_ids", "trace_ids", "document_ids")


def add_diary(case: dict, text: str, officer: str, kind: str = "NOTE",
              refs: dict | None = None) -> dict:
    """Append one diary entry. Entries are never edited or removed.

    `refs` lets an entry point at what it is about - accounts, source rows, a
    trace, a document - so a later reader can follow the entry back to the
    evidence instead of trusting the sentence.
    """
    entry = {"entry_id": ulid("dry"), "kind": kind, "text": text,
             "officer": officer, "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    if refs:
        clean = {k: list(dict.fromkeys(refs[k])) for k in REF_KINDS
                 if isinstance(refs.get(k), (list, tuple)) and refs.get(k)}
        if clean:
            entry["refs"] = clean
    case["diary"].append(entry)
    return save(case)


def add_trace(case: dict, trace: dict) -> dict:
    """Record that an investigation was run for this case.

    Only the identity and shape of the trace is stored - never the node list.
    The trace itself lives in memory and expires; the case keeps the receipt.
    """
    case.setdefault("traces", []).append({
        "trace_id": trace.get("trace_id"),
        "victim_account": trace.get("victim_account"),
        "seed_amount": trace.get("seed_amount"),
        "max_hops": trace.get("max_hops"),
        "node_count": trace.get("node_count"),
        "edge_count": trace.get("edge_count"),
        "truncated": trace.get("truncated"),
        "truncation_reason": trace.get("truncation_reason"),
        "dataset_fingerprint": trace.get("dataset_fingerprint"),
        "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    })
    return save(case)
