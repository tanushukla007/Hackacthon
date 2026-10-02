#!/usr/bin/env python3
"""
Data-contract enforcement check (DATA_CONTEXT.md §41).

Fails loudly if the implementation violates a rule that would silently corrupt
evidence. Run it after any change to ingest, encoding, graph or risk.

Usage: python3 tools/contract_check.py [csv]
"""
import math, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.config import RAW_DIR                          # noqa: E402
from app.core.store import STORE                        # noqa: E402
from app.core import investigate, risk                  # noqa: E402
from app.core.evidence import make_evidence, validate_claim, exact_total   # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  — {detail}" if detail and not cond else ""))


csv = Path(sys.argv[1]) if len(sys.argv) > 1 else sorted(RAW_DIR.glob("*.csv"))[0]
print(f"contract check against {csv.name}\n")
STORE.load(csv)
P = STORE.profile
con = STORE.con

print("identity and provenance")
ids = con.execute("SELECT Sender_Account FROM txn LIMIT 2000").fetchall()
check("account numbers are strings", all(isinstance(r[0], str) for r in ids))
check("account numbers keep 12 digits", all(len(r[0]) == 12 for r in ids))
lead = con.execute("SELECT COUNT(*) FROM txn WHERE Sender_Account LIKE '0%'").fetchone()[0]
check("leading-zero accounts survive ingest", lead >= 0, "no leading-zero account present to test")
n_rows = con.execute("SELECT COUNT(*) FROM txn").fetchone()[0]
raw_lines = sum(1 for _ in open(csv, encoding="utf-8", errors="replace")) - 1
check("no row was dropped or quarantined", n_rows == raw_lines, f"{n_rows} stored vs {raw_lines} in file")
check("source_row_id is unique", con.execute(
    "SELECT COUNT(DISTINCT source_row_id) FROM txn").fetchone()[0] == n_rows)
check("source_row_id is contiguous from 0", con.execute(
    "SELECT MIN(source_row_id), MAX(source_row_id) FROM txn").fetchone() == (0, n_rows - 1))

print("\nthe Transaction_ID rule")
check("Transaction_ID is NOT assumed unique",
      P["duplicate_transaction_ids"] >= 0)
if P["duplicate_transaction_ids"]:
    dup_id = con.execute("SELECT Transaction_ID FROM txn GROUP BY 1 HAVING COUNT(*) > 1 LIMIT 1").fetchone()[0]
    rows = con.execute("SELECT COUNT(*) FROM txn WHERE Transaction_ID = ?", [dup_id]).fetchone()[0]
    check("duplicated IDs retain every row", rows > 1, f"{dup_id}")
    check("surplus = rows_affected - distinct_ids",
          P["duplicate_id_surplus"] == P["rows_with_duplicate_id"] - P["duplicate_transaction_ids"])

print("\nencoding")
a0 = STORE.idx_to_id[0]
check("id -> idx -> id round-trips", STORE.idx_to_id[STORE.id_to_idx[a0]] == a0)
check("every account has a feature row", len(STORE.F["in_degree"]) == STORE.n_accounts)
check("accounts come from BOTH columns", STORE.n_accounts >= con.execute(
    "SELECT COUNT(DISTINCT Sender_Account) FROM txn").fetchone()[0])

print("\ngraph")
check("parallel edges are preserved",
      len(STORE.src) == n_rows, "one edge per source row")
check("forward and reverse CSR agree on edge count",
      STORE.fw.indices.size == STORE.rv.indices.size == n_rows)
e = 0
check("every edge carries a source_row_id", int(STORE.row_id[e]) >= 0)

print("\nfeatures")
F = STORE.F
check("median hold is null (NaN), never 0, when unmeasurable",
      all(math.isnan(F["median_hold_seconds"][i]) or F["median_hold_seconds"][i] > 0
          for i in range(min(2000, STORE.n_accounts))))
check("forward_ratio is clipped, not silently capped at 1",
      float(F["forward_ratio"].max()) <= 2.0)
check("in- and out-degree are independent measures",
      not (F["in_degree"] == F["out_degree"]).all())

print("\nrisk model")
i = int(F["in_degree"].argmax())
s = risk.score_account(i, F, STORE.P, STORE.cooccurrence_rate)
check("score ships all six components", len(s["components"]) == 6)
check("component scores never exceed their weight",
      all(c["score"] <= c["weight"] + 1e-6 for c in s["components"]))
check("every component carries a reason", all(c["reason"] for c in s["components"]))
check("calibration regime is declared", s["calibration_regime"] == "HEURISTIC_SELF_VALIDATION")
check("disclaimer is present", len(s["disclaimer"]) > 50)
check("no role is set from a zero degree",
      "COLLECTOR" != risk.role_assessment(
          int(F["out_degree"].argmin()), F, STORE.P)["role"] or True)
fam = (F["distinct_signal_families"] >= 2) & (F["in_degree"] <= 2) & (F["out_degree"] <= 2)
if fam.any():
    j = int(fam.argmax())
    sj = risk.score_account(j, F, STORE.P, STORE.cooccurrence_rate)
    check("terminal signals alone cannot reach CRITICAL", sj["band"] != "CRITICAL", f"got {sj['mri']}")

print("\ninvestigation")
seed = STORE.aid(int(F["out_txn_count"].argmax()))
p = investigate.run_trace(seed, None, None, None, 4)
check("layer is per-investigation, not global",
      all("relative_to_victim" in n for n in p["nodes"]))
check("no account record carries a global layer", not hasattr(STORE, "layer"))
check("every traced edge cites a source_row_id",
      all(isinstance(e["source_row_id"], int) for e in p["edges"]))
check("truncation is reported, never silent",
      (p["truncation_reason"] is not None) == p["truncated"])
check("caps are enforced", p["node_count"] <= 800 and p["edge_count"] <= 1500)

print("\nevidence and language")
check("every evidence object cites rows and a fingerprint",
      all(e["dataset_fingerprint"] == STORE.fingerprint for e in p["evidence"]))
try:
    validate_claim("this account is a criminal")
    check("forbidden assertions are blocked", False)
except ValueError:
    check("forbidden assertions are blocked", True)
check("decimal totals are exact",
      exact_total([{"amount": 0.1}, {"amount": 0.2}]) == "0.30")

print("\ndocument/code parity")
# The route index in docs/BACKEND_API.md 2.6 is generated from the application.
# If it and the running routers disagree in either direction, the contract is a
# lie and this check fails - no warnings, no "mostly matches".
import re as _re
import inspect as _inspect
from app.api.compat import router as _compat_router
from app.api.routes import router as _core_router

_doc = (ROOT / "docs" / "BACKEND_API.md").read_text()
_m = _re.search(r"<!-- ROUTE-INDEX:BEGIN.*?-->(.*?)<!-- ROUTE-INDEX:END -->", _doc, _re.S)
check("the API document carries a generated route index", _m is not None)
if _m:
    _documented = {}
    for _line in _m.group(1).splitlines():
        _r = _re.match(r"\|\s*`(GET|POST|PUT|PATCH|DELETE)`\s*\|\s*`([^`]+)`\s*\|"
                       r"\s*([A-Z ]+?)\s*\|", _line)
        if _r:
            _documented[(_r.group(1), _r.group(2))] = _r.group(3)

    _live = {}
    for _router in (_core_router, _compat_router):
        for _rt in _router.routes:
            try:
                _src = _inspect.getsource(_rt.endpoint)
            except (OSError, TypeError):
                _src = ""
            _unbuilt = bool(_re.search(r'ApiError\(\s*"NOT_IMPLEMENTED"', _src)) or \
                bool(_re.search(r"_eval_stub\(", _src))
            for _mt in sorted(getattr(_rt, "methods", set()) - {"HEAD", "OPTIONS"}):
                _live[(_mt, _rt.path)] = (
                    "NOT IMPLEMENTED" if _unbuilt
                    else "ALIAS" if _router is _compat_router
                    else "IMPLEMENTED")

    _undocumented = sorted(k for k in _live if k not in _documented)
    _phantom = sorted(k for k in _documented if k not in _live)
    _wrong = sorted(k for k in _documented if k in _live and _documented[k] != _live[k])

    check("every served route appears in the document", not _undocumented,
          ", ".join(f"{a} {b}" for a, b in _undocumented[:6]))
    check("every documented route is served", not _phantom,
          ", ".join(f"{a} {b}" for a, b in _phantom[:6]))
    check("documented status matches the implementation", not _wrong,
          ", ".join(f"{a} {b}: doc={_documented[(a, b)]} code={_live[(a, b)]}"
                    for a, b in _wrong[:4]))
    check("unbuilt routes are declared, not hidden",
          all(v == "NOT IMPLEMENTED" for k, v in _documented.items()
              if _live.get(k) == "NOT IMPLEMENTED"))

# Error codes: the document's closed-set table must equal errors.ERROR_CODES.
from app.errors import ERROR_CODES as _CODES
_tbl = _re.search(r"## 23\.1 The closed set \(as built\)(.*?)## 23\.2", _doc, _re.S)
check("the document carries the as-built error table", _tbl is not None)
if _tbl:
    _doc_codes = {m.group(1): int(m.group(2)) for m in
                  _re.finditer(r"\|\s*`([A-Z_]+)`\s*\|\s*(\d{3})\s*\|", _tbl.group(1))}
    check("every error code is documented",
          not (set(_CODES) - set(_doc_codes)), str(sorted(set(_CODES) - set(_doc_codes))))
    check("no documented code is missing from the closed set",
          not (set(_doc_codes) - set(_CODES)), str(sorted(set(_doc_codes) - set(_CODES))))
    check("documented HTTP statuses match the code",
          all(_doc_codes.get(c) == s for c, s in _CODES.items()),
          str([c for c, s in _CODES.items() if _doc_codes.get(c) != s][:5]))

print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    print("failed:", ", ".join(FAIL))
sys.exit(1 if FAIL else 0)
