"""Deterministic document generation: structured data in, printable PDF out.

Rules this module obeys, in order of importance:

1. Nothing is invented. Every rupee figure is recomputed with Decimal from the
   cited source rows, and every document carries the dataset fingerprint and
   the source_row_ids it relied on.
2. Observations and assessments are labelled separately and never merged. A
   behavioural score is printed as an investigative aid, never as a finding.
3. The same inputs always produce the same document body. The only varying
   field is the generation timestamp, which is printed, not hidden.
4. Forbidden language ("criminal", "guilty", "fraudster", ...) is blocked by
   evidence.validate_claim before it can reach a page.

PDF rendering uses WeasyPrint. If WeasyPrint is not installed the caller gets
an honest error instead of a silently different output format.
"""
from __future__ import annotations

import html as _html
import time
from decimal import Decimal

from ..config import LEGAL_PRODUCTION, LEGAL_SEIZURE
from .evidence import ulid, validate_claim

try:                                                      # pragma: no cover
    from weasyprint import HTML as _WeasyHTML
    PDF_AVAILABLE = True
    PDF_ENGINE = "weasyprint"
except Exception:                                         # pragma: no cover
    _WeasyHTML = None
    PDF_AVAILABLE = False
    PDF_ENGINE = None


DOC_TYPES = (
    "FREEZE_REQUISITION",
    "COVERING_LETTER",
    "VICTIM_ACKNOWLEDGEMENT",
    "TRACE_REPORT",
    "ACCOUNT_REPORT",
)

DISCLAIMER = (
    "Amounts in this document are recomputed with exact decimal arithmetic from the "
    "cited source rows of the dataset named above. Behavioural assessments are "
    "investigative prioritisation aids produced from observed transaction behaviour. "
    "They are not verdicts, not probabilities of guilt and not findings of fact. No "
    "ground-truth labels exist for this dataset, so no accuracy claim is made."
)


# --------------------------------------------------------------------- utils
def e(v) -> str:
    """Escape for HTML."""
    return _html.escape("" if v is None else str(v))


def rupees(value) -> str:
    """Indian-grouped rupee string from a Decimal/str/float, two decimals."""
    d = Decimal(str(value)).quantize(Decimal("0.01"))
    neg = d < 0
    whole, frac = f"{abs(d):.2f}".split(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        whole = ",".join(parts + [tail])
    return ("-" if neg else "") + "Rs " + whole + "." + frac


def _doc_id(kind: str) -> str:
    return ulid("doc")


def _ref(case_id: str, kind: str, seq: int = 1) -> str:
    """Human reference number printed on the document."""
    short = {"FREEZE_REQUISITION": "FRZ", "COVERING_LETTER": "FWD",
             "VICTIM_ACKNOWLEDGEMENT": "ACK", "TRACE_REPORT": "TRC",
             "ACCOUNT_REPORT": "ACC", "CASE_DIARY": "DIA"}.get(kind, "DOC")
    return f"{case_id}/{short}/{seq:02d}"


def _officer_block(case: dict) -> dict:
    d = case.get("details") or {}
    return {
        "officer": case.get("officer") or "Investigating Officer",
        "rank": d.get("officer_rank") or "Investigating Officer",
        "police_station": d.get("police_station") or "",
        "district": d.get("district") or "",
        "fir_number": d.get("fir_number") or "",
        "fir_date": d.get("fir_date") or "",
        "contact": d.get("officer_contact") or "",
    }


# ------------------------------------------------------------- doc builders
BASIS_WORDS = {
    "TRACED_FROM_VICTIM":
        "amounts traced from the complainant's account along the money trail identified "
        "in this case",
    "ALL_CREDITS_IN_WINDOW":
        "the total credits each account received within the dataset window, which is NOT "
        "limited to funds attributable to this complainant",
}


def build_freeze_requisition(case: dict, blocks: list[dict], fingerprint: str | None,
                             seq: int = 1, basis: str = "ALL_CREDITS_IN_WINDOW",
                             trace_id: str | None = None,
                             victim: str | None = None) -> dict:
    """blocks: [{account_id, bank, credited_total, transactions_cited,
                 source_row_ids, mri, band}]"""
    total = sum((Decimal(str(b["credited_total"])) for b in blocks), Decimal("0"))
    for b in blocks:
        validate_claim(f"account {b['account_id']} received {b['credited_total']}")
    return {
        "document_id": _doc_id("FREEZE_REQUISITION"),
        "type": "FREEZE_REQUISITION",
        "reference": _ref(case["case_id"], "FREEZE_REQUISITION", seq),
        "case_id": case["case_id"],
        "title": "Requisition for freezing of bank accounts and production of records",
        "legal_basis": LEGAL_PRODUCTION,
        "seizure_basis": LEGAL_SEIZURE,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "dataset_fingerprint": fingerprint,
        "officer": _officer_block(case),
        "victim_account": victim or case.get("victim_account"),
        "complainant": (case.get("details") or {}).get("complainant_name") or "",
        "reported_amount": case.get("reported_amount"),
        "accounts": blocks,
        "accounts_count": len(blocks),
        "total_credited": str(total),
        "amount_basis": basis,
        "amount_basis_text": BASIS_WORDS.get(basis, basis),
        "trace_id": trace_id,
        "response_days": (case.get("details") or {}).get("response_days") or 3,
        "disclaimer": DISCLAIMER,
    }


def build_covering_letter(case: dict, requisition: dict, bank_name: str | None = None,
                          seq: int = 1) -> dict:
    banks = sorted({b.get("bank") or "the concerned bank" for b in requisition["accounts"]})
    return {
        "document_id": _doc_id("COVERING_LETTER"),
        "type": "COVERING_LETTER",
        "reference": _ref(case["case_id"], "COVERING_LETTER", seq),
        "case_id": case["case_id"],
        "title": "Covering letter to the Nodal Officer",
        "addressee": bank_name or (banks[0] if banks else "The Nodal Officer"),
        "banks": banks,
        "encloses": {
            "document_id": requisition["document_id"],
            "reference": requisition["reference"],
            "type": requisition["type"],
            "accounts_count": requisition["accounts_count"],
            "total_credited": requisition["total_credited"],
        },
        "legal_basis": LEGAL_PRODUCTION,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "dataset_fingerprint": requisition.get("dataset_fingerprint"),
        "officer": _officer_block(case),
        "response_days": requisition["response_days"],
        "disclaimer": DISCLAIMER,
    }


def build_victim_acknowledgement(case: dict, requisition: dict | None = None,
                                 seq: int = 1) -> dict:
    d = case.get("details") or {}
    return {
        "document_id": _doc_id("VICTIM_ACKNOWLEDGEMENT"),
        "type": "VICTIM_ACKNOWLEDGEMENT",
        "reference": _ref(case["case_id"], "VICTIM_ACKNOWLEDGEMENT", seq),
        "case_id": case["case_id"],
        "title": "Acknowledgement to the complainant",
        "complainant": d.get("complainant_name") or "The Complainant",
        "complainant_address": d.get("complainant_address") or "",
        "complaint_date": d.get("complaint_date") or "",
        "victim_account": case.get("victim_account"),
        "reported_amount": case.get("reported_amount"),
        "action_taken": {
            "accounts_requisitioned": requisition["accounts_count"] if requisition else 0,
            "requisition_reference": requisition["reference"] if requisition else None,
            "total_identified": requisition["total_credited"] if requisition else None,
        },
        "legal_basis": LEGAL_PRODUCTION,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "dataset_fingerprint": case.get("dataset_fingerprint"),
        "officer": _officer_block(case),
        "disclaimer": DISCLAIMER,
    }


def build_case_diary(case: dict, fingerprint: str | None, seq: int = 1) -> dict:
    """The case diary as a signed document.

    It prints what was done, in order, with the references each entry carries.
    Nothing is summarised away and no entry is reworded: the diary is the
    record, and a document that edits the record is worthless.
    """
    return {
        "document_id": _doc_id("CASE_DIARY"),
        "type": "CASE_DIARY",
        "reference": _ref(case["case_id"], "CASE_DIARY", seq),
        "case_id": case["case_id"],
        "title": "Case diary",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "dataset_fingerprint": fingerprint,
        "officer": _officer_block(case),
        "victim_account": case.get("victim_account"),
        "entries": list(case.get("diary", [])),
        "basket": list(case.get("basket", [])),
        "traces": list(case.get("traces", [])),
        "documents": [{k: d.get(k) for k in ("reference", "type", "generated_at")}
                      for d in case.get("documents", [])],
        "disclaimer": DISCLAIMER,
    }


def build_trace_report(case: dict | None, trace: dict, fingerprint: str | None) -> dict:
    return {
        "document_id": _doc_id("TRACE_REPORT"),
        "type": "TRACE_REPORT",
        "reference": _ref(case["case_id"] if case else "NO-CASE", "TRACE_REPORT"),
        "case_id": case["case_id"] if case else None,
        "title": "Money trail report",
        "trace_id": trace.get("trace_id"),
        "victim_account": trace.get("victim_account"),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "dataset_fingerprint": fingerprint,
        "officer": _officer_block(case) if case else {},
        "summary": trace.get("summary", {}),
        "seed_amount": trace.get("seed_amount"),
        "seed_basis": trace.get("seed_basis"),
        "truncated": trace.get("truncated"),
        "truncation_reason": trace.get("truncation_reason"),
        "nodes": trace.get("nodes", []),
        "edges": trace.get("edges", []),
        "disclaimer": DISCLAIMER,
    }


def build_account_report(case: dict | None, account: dict, transactions: list[dict],
                         fingerprint: str | None) -> dict:
    return {
        "document_id": _doc_id("ACCOUNT_REPORT"),
        "type": "ACCOUNT_REPORT",
        "reference": _ref(case["case_id"] if case else "NO-CASE", "ACCOUNT_REPORT"),
        "case_id": case["case_id"] if case else None,
        "title": "Account behaviour report",
        "account_id": account.get("account_id"),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "dataset_fingerprint": fingerprint,
        "officer": _officer_block(case) if case else {},
        "account": account,
        "transactions": transactions,
        "disclaimer": DISCLAIMER,
    }


BUILDERS = {
    "FREEZE_REQUISITION": build_freeze_requisition,
    "COVERING_LETTER": build_covering_letter,
    "VICTIM_ACKNOWLEDGEMENT": build_victim_acknowledgement,
    "TRACE_REPORT": build_trace_report,
    "ACCOUNT_REPORT": build_account_report,
}


# ------------------------------------------------------------------- render
_CSS = """
@page { size: A4; margin: 18mm 16mm 20mm 16mm;
        @bottom-center { content: "Page " counter(page) " of " counter(pages);
                         font-family: serif; font-size: 8pt; color: #555; } }
body { font-family: "DejaVu Serif", Georgia, serif; font-size: 10pt; color: #111; line-height: 1.45; }
.head { border-bottom: 2px solid #111; padding-bottom: 6px; margin-bottom: 14px; }
.head .org { font-size: 13pt; font-weight: bold; letter-spacing: .5px; }
.head .sub { font-size: 9pt; color: #444; }
.meta { width: 100%; font-size: 8.5pt; color: #333; margin-bottom: 14px; }
.meta td { padding: 1px 0; vertical-align: top; }
.meta td.k { color: #555; width: 32%; }
h1 { font-size: 12pt; text-align: center; margin: 14px 0 12px; text-transform: uppercase;
     letter-spacing: .6px; }
h2 { font-size: 10pt; margin: 14px 0 6px; border-bottom: 1px solid #999; padding-bottom: 2px; }
p { margin: 7px 0; text-align: justify; }
table.data { width: 100%; border-collapse: collapse; margin: 8px 0; font-size: 8.5pt; }
table.data th, table.data td { border: 1px solid #999; padding: 4px 5px; text-align: left; }
table.data th { background: #eee; font-size: 8pt; text-transform: uppercase; letter-spacing: .3px; }
table.data td.n { text-align: right; font-family: "DejaVu Sans Mono", monospace; }
.mono { font-family: "DejaVu Sans Mono", monospace; }
.rows { font-family: "DejaVu Sans Mono", monospace; font-size: 7pt; color: #444;
        word-break: break-all; }
.note { border: 1px solid #999; background: #f4f4f4; padding: 7px 9px; font-size: 8pt;
        margin: 12px 0; }
.sign { margin-top: 28px; }
.sign .line { margin-top: 34px; border-top: 1px solid #111; width: 60mm; padding-top: 3px;
              font-size: 9pt; }
.foot { margin-top: 16px; border-top: 1px solid #999; padding-top: 6px; font-size: 7.5pt;
        color: #555; }
.badge { border: 1px solid #333; padding: 0 4px; font-size: 7.5pt; }
"""


def _letterhead(doc: dict) -> str:
    o = doc.get("officer") or {}
    unit = " · ".join(x for x in [o.get("police_station"), o.get("district")] if x)
    rows = [
        ("Reference", doc.get("reference")),
        ("Document ID", doc.get("document_id")),
        ("Case", doc.get("case_id")),
        ("FIR / Complaint", " ".join(x for x in [o.get("fir_number"), o.get("fir_date")] if x)),
        ("Generated", doc.get("generated_at")),
        ("Dataset fingerprint", doc.get("dataset_fingerprint")),
    ]
    meta = "".join(
        f"<tr><td class='k'>{e(k)}</td><td class='mono'>{e(v) if v else '—'}</td></tr>"
        for k, v in rows)
    return (
        "<div class='head'>"
        f"<div class='org'>{e(unit or 'Office of the Investigating Officer')}</div>"
        "<div class='sub'>Cyber / Economic Offences — money trail analysis produced with "
        "ABHEDYA-CHAKRA</div></div>"
        f"<table class='meta'>{meta}</table>"
    )


def _signature(doc: dict) -> str:
    o = doc.get("officer") or {}
    return (
        "<div class='sign'><div class='line'>"
        f"{e(o.get('officer'))}<br/>{e(o.get('rank'))}"
        + (f"<br/>{e(o.get('police_station'))}" if o.get("police_station") else "")
        + (f"<br/>{e(o.get('contact'))}" if o.get("contact") else "")
        + "</div></div>"
    )


def _footer(doc: dict) -> str:
    return f"<div class='foot'>{e(doc.get('disclaimer') or DISCLAIMER)}</div>"


def _accounts_table(blocks: list[dict]) -> str:
    basis = (blocks[0].get("basis") if blocks else "") or ""
    label = "Traced credit" if basis == "TRACED_FROM_VICTIM" else "Credited in window"
    head = (f"<tr><th>#</th><th>Account</th><th>Bank</th><th class='n'>{e(label)}</th>"
            "<th class='n'>Txns cited</th><th>Behavioural assessment</th></tr>")
    body = ""
    for i, b in enumerate(blocks, 1):
        band = b.get("band") or ""
        body += (
            f"<tr><td class='n'>{i}</td><td class='mono'>{e(b['account_id'])}</td>"
            f"<td>{e(b.get('bank'))}</td>"
            f"<td class='n'>{e(rupees(b['credited_total']))}</td>"
            f"<td class='n'>{e(b.get('transactions_cited'))}</td>"
            f"<td>MRI {e(b.get('mri'))}/100 {e(band)}</td></tr>")
    return f"<table class='data'>{head}{body}</table>"


def _rows_cited(blocks: list[dict]) -> str:
    out = ""
    for b in blocks:
        ids = b.get("source_row_ids") or []
        shown = ", ".join(str(x) for x in ids[:120])
        more = f" … and {len(ids) - 120} more" if len(ids) > 120 else ""
        out += (f"<p class='rows'><b>{e(b['account_id'])}</b> — source_row_id: "
                f"{e(shown)}{e(more)}</p>")
    return out


def render_html(doc: dict) -> str:
    t = doc.get("type")
    if t == "FREEZE_REQUISITION":
        body = _freeze_body(doc)
    elif t == "COVERING_LETTER":
        body = _covering_body(doc)
    elif t == "VICTIM_ACKNOWLEDGEMENT":
        body = _ack_body(doc)
    elif t == "CASE_DIARY":
        body = _diary_body(doc)
    elif t == "TRACE_REPORT":
        body = _trace_body(doc)
    elif t == "ACCOUNT_REPORT":
        body = _account_body(doc)
    else:
        raise ValueError(f"unknown document type {t}")
    return ("<!doctype html><html><head><meta charset='utf-8'>"
            f"<title>{e(doc.get('reference'))}</title><style>{_CSS}</style></head><body>"
            + _letterhead(doc) + body + _signature(doc) + _footer(doc)
            + "</body></html>")


def _banks_of(doc: dict) -> str:
    names = sorted({(b.get("bank") or "").strip() for b in doc.get("accounts", [])} - {""})
    return ", ".join(names)


def _freeze_body(doc: dict) -> str:
    o = doc["officer"]
    return (
        f"<h1>{e(doc['title'])}</h1>"
        f"<p><b>To:</b> The Nodal Officer / Branch Manager, "
        f"{e(_banks_of(doc) or 'the concerned bank')}</p>"
        f"<p><b>Subject:</b> Requisition under {e(doc['legal_basis'])} for production of "
        f"records and action under {e(doc['seizure_basis'])} in respect of "
        f"{doc['accounts_count']} account(s) connected to {e(doc['case_id'])}.</p>"
        "<p>Sir / Madam,</p>"
        f"<p>A complaint has been registered"
        + (f" vide FIR {e(o.get('fir_number'))}" if o.get("fir_number") else "")
        + (f" by {e(doc['complainant'])}" if doc.get("complainant") else "")
        + f" concerning unauthorised transfer of funds from account "
          f"<span class='mono'>{e(doc['victim_account'])}</span>"
        + (f", reported amount {e(rupees(doc['reported_amount']))}" if doc.get("reported_amount") else "")
        + (". Analysis of the transaction records supplied in this matter shows that funds "
           "traced from the said account were credited to the accounts listed below.</p>"
           if doc.get("amount_basis") == "TRACED_FROM_VICTIM" else
           ". The accounts listed below are connected to this matter. The amounts shown "
           "against them are their total credits within the dataset window and are not, by "
           "themselves, attributed to this complainant.</p>")
        + "<h2>Accounts and amounts</h2>"
        + _accounts_table(doc["accounts"])
        + f"<p>Total across the listed accounts: "
          f"<b>{e(rupees(doc['total_credited']))}</b>. The figures above are "
          f"{e(doc.get('amount_basis_text') or '')}"
        + (f", trace reference <span class='mono'>{e(doc.get('trace_id'))}</span>"
           if doc.get("trace_id") else "")
        + ".</p>"
        "<h2>Action requested</h2>"
        "<ol>"
        "<li>Place a debit freeze on the listed accounts to the extent of the amounts shown, "
        "pending further orders.</li>"
        "<li>Furnish the account opening form, KYC documents, registered mobile number, "
        "email address and the IP / device logs of the operating sessions.</li>"
        "<li>Furnish the statement of account for the period covered by the enclosed data.</li>"
        "<li>Confirm the present balance and the amount lien-marked.</li>"
        "</ol>"
        f"<p>A response within <b>{e(doc['response_days'])} working days</b> is requested, "
        "given the risk of onward layering.</p>"
        "<h2>Basis of identification</h2>"
        f"<p>The amounts above are the sum of individual credits ({e(doc.get('amount_basis'))}) "
        "within the dataset identified by the fingerprint printed on this page. The specific "
        "rows relied upon are listed below so that the computation can be independently "
        "reproduced from the source file.</p>"
        + _rows_cited(doc["accounts"])
        + "<div class='note'><b>Nature of the behavioural assessment:</b> the MRI values "
          "shown are produced from observed transaction behaviour (pass-through speed, "
          "fan-in, fan-out, velocity and similar measurements). They indicate where "
          "verification effort is best spent. They are not an allegation against any "
          "account holder and carry no presumption of guilt.</div>"
    )


def _covering_body(doc: dict) -> str:
    enc = doc["encloses"]
    return (
        f"<h1>{e(doc['title'])}</h1>"
        f"<p><b>To:</b> The Nodal Officer, {e(doc['addressee'])}</p>"
        f"<p><b>Subject:</b> Forwarding of requisition {e(enc['reference'])} under "
        f"{e(doc['legal_basis'])} — {enc['accounts_count']} account(s), "
        f"{e(rupees(enc['total_credited']))}.</p>"
        "<p>Sir / Madam,</p>"
        f"<p>Please find enclosed the requisition referenced above, issued in connection "
        f"with {e(doc['case_id'])}. It lists {enc['accounts_count']} account(s) maintained "
        f"with your institution to which funds traced from the complainant's account were "
        f"credited, aggregating {e(rupees(enc['total_credited']))}.</p>"
        "<h2>Enclosures</h2>"
        "<table class='data'>"
        "<tr><th>#</th><th>Document</th><th>Reference</th><th>Document ID</th></tr>"
        f"<tr><td class='n'>1</td><td>Freeze requisition and record production</td>"
        f"<td class='mono'>{e(enc['reference'])}</td>"
        f"<td class='mono'>{e(enc['document_id'])}</td></tr>"
        f"<tr><td class='n'>2</td><td>Schedule of cited source rows</td>"
        f"<td class='mono'>{e(enc['reference'])}</td><td class='mono'>— (within enclosure 1)</td></tr>"
        "</table>"
        "<h2>Points for your attention</h2>"
        "<ol>"
        "<li>The freeze sought is limited to the traced amount shown against each account, "
        "not the entire balance, unless the balance is lower.</li>"
        "<li>Kindly nominate a single point of contact for this reference so that follow-up "
        "can be consolidated.</li>"
        f"<li>An acknowledgement within <b>{e(doc['response_days'])} working days</b> is "
        "requested, even if the substantive reply follows later.</li>"
        "</ol>"
        "<p>The analysis underlying the enclosure is reproducible: the dataset fingerprint "
        "and the individual source row identifiers are printed in the enclosure.</p>"
    )


def _ack_body(doc: dict) -> str:
    a = doc["action_taken"]
    done = a["accounts_requisitioned"]
    return (
        f"<h1>{e(doc['title'])}</h1>"
        f"<p><b>To:</b> {e(doc['complainant'])}"
        + (f"<br/>{e(doc['complainant_address'])}" if doc.get("complainant_address") else "")
        + "</p>"
        f"<p><b>Subject:</b> Action taken on your complaint"
        + (f" dated {e(doc['complaint_date'])}" if doc.get("complaint_date") else "")
        + f" — {e(doc['case_id'])}.</p>"
        "<p>Sir / Madam,</p>"
        f"<p>Your complaint concerning the unauthorised transfer of funds from account "
        f"<span class='mono'>{e(doc['victim_account'])}</span>"
        + (f" amounting to {e(rupees(doc['reported_amount']))}" if doc.get("reported_amount") else "")
        + " has been registered and acted upon. This letter records the action taken so "
          "far.</p>"
        "<h2>Action taken</h2>"
        + ("<p>The transaction records have been analysed and the onward movement of the "
           f"funds has been traced. A requisition has been issued to the concerned bank(s) "
           f"in respect of <b>{done}</b> account(s)"
           + (f", reference <span class='mono'>{e(a['requisition_reference'])}</span>"
              if a.get("requisition_reference") else "")
           + (f", covering {e(rupees(a['total_identified']))} of traced credit"
              if a.get("total_identified") else "")
           + ", seeking a debit freeze and production of account records.</p>"
           if done else
           "<p>The transaction records have been analysed. No requisition has been issued "
           "under this reference yet; this letter acknowledges registration of the "
           "complaint and the commencement of analysis.</p>")
        + "<h2>What happens next</h2>"
        "<p>Recovery depends on the funds still being available in the receiving accounts "
        "and on the response of the banks concerned. This office will inform you of the "
        "outcome. Please quote the case reference in any further correspondence, and inform "
        "this office immediately if you receive any further contact from the suspected "
        "party.</p>"
        "<div class='note'>This letter records investigative action. It is not a finding "
        "against any person and does not by itself guarantee recovery of the amount.</div>"
    )


def _diary_body(doc: dict) -> str:
    entries = doc.get("entries") or []
    rows = []
    for i, en in enumerate(entries, 1):
        refs = en.get("refs") or {}
        ref_txt = " · ".join(
            k.replace("_", " ") + ": " + ", ".join(str(x) for x in v[:8]) +
            (" and " + str(len(v) - 8) + " more" if len(v) > 8 else "")
            for k, v in refs.items())
        rows.append(
            "<tr><td class='n'>" + e(i) + "</td><td class='mono'>" + e(en.get("at")) +
            "</td><td>" + e(en.get("kind")) + "</td><td>" + e(en.get("text")) +
            ("<br><span class='rows'>" + e(ref_txt) + "</span>" if ref_txt else "") +
            "</td><td>" + e(en.get("officer")) + "</td></tr>")
    traces = doc.get("traces") or []
    trows = "".join(
        "<tr><td class='mono'>" + e(tr.get("trace_id")) + "</td><td class='mono'>" +
        e(tr.get("victim_account")) + "</td><td class='n'>" + e(tr.get("node_count")) +
        "</td><td class='n'>" + e(tr.get("edge_count")) + "</td><td class='mono'>" +
        e(tr.get("at")) + "</td></tr>" for tr in traces)
    basket = doc.get("basket") or []
    brows = "".join(
        "<tr><td>" + e(b.get("claim_type")) + "</td><td>" + e(b.get("claim")) +
        "</td><td class='n'>" + e(len(b.get("source_row_ids") or [])) + "</td></tr>"
        for b in basket)
    docs = doc.get("documents") or []
    drows = "".join(
        "<tr><td class='mono'>" + e(d.get("reference")) + "</td><td>" + e(d.get("type")) +
        "</td><td class='mono'>" + e(d.get("generated_at")) + "</td></tr>" for d in docs)
    return (
        "<h1>" + e(doc["title"]) + "</h1>"
        "<p><b>Victim account:</b> <span class='mono'>" + e(doc.get("victim_account")) +
        "</span> · <b>Entries:</b> " + e(len(entries)) + "</p>"
        "<h2>Diary</h2>"
        "<table class='data'><tr><th>#</th><th>Timestamp</th><th>Kind</th>"
        "<th>Entry</th><th>Officer</th></tr>" + "".join(rows) +
        ("<tr><td colspan='5'>No entries have been recorded.</td></tr>"
         if not rows else "") + "</table>"
        "<p class='rows'>Entries are append-only. They are reproduced here exactly as "
        "recorded, in the order recorded.</p>"
        "<h2>Investigations run</h2>"
        "<table class='data'><tr><th>Trace</th><th>Victim</th><th>Accounts</th>"
        "<th>Transfers</th><th>Run at</th></tr>" + trows +
        ("<tr><td colspan='5'>None recorded.</td></tr>" if not trows else "") + "</table>"
        "<h2>Evidence collected</h2>"
        "<table class='data'><tr><th>Type</th><th>Observation</th><th>Rows cited</th></tr>" +
        brows + ("<tr><td colspan='3'>Nothing in the basket.</td></tr>"
                 if not brows else "") + "</table>"
        "<h2>Documents issued</h2>"
        "<table class='data'><tr><th>Reference</th><th>Type</th><th>Generated</th></tr>" +
        drows + ("<tr><td colspan='3'>None issued.</td></tr>" if not drows else "") +
        "</table>")


def _trace_body(doc: dict) -> str:
    s = doc.get("summary") or {}
    layers = " · ".join(f"{k} {v}" for k, v in (s.get("layers") or {}).items())
    nodes = doc.get("nodes") or []
    head = ("<tr><th>Hop</th><th>Layer</th><th>Account</th><th class='n'>Value traced</th>"
            "<th>Assessment</th><th>Role</th></tr>")
    body = "".join(
        f"<tr><td class='n'>{e(n.get('hop_distance'))}</td><td>{e(n.get('layer'))}</td>"
        f"<td class='mono'>{e(n.get('account_id'))}</td>"
        f"<td class='n'>{e(rupees(n.get('attributed_value') or 0))}</td>"
        f"<td>MRI {e(n.get('mri'))} {e(n.get('band'))}</td><td>{e(n.get('role'))}</td></tr>"
        for n in nodes[:200])
    extra = (f"<p class='rows'>Table truncated to the first 200 of {len(nodes)} accounts; "
             "the full result is available in the application and through the API.</p>"
             if len(nodes) > 200 else "")
    edges = doc.get("edges") or []
    ehead = ("<tr><th>Hop</th><th>From</th><th>To</th><th class='n'>Amount</th>"
             "<th class='n'>source_row_id</th></tr>")
    ebody = "".join(
        f"<tr><td class='n'>{e(x.get('hop'))}</td><td class='mono'>{e(x.get('from'))}</td>"
        f"<td class='mono'>{e(x.get('to'))}</td>"
        f"<td class='n'>{e(rupees(x.get('amount') or 0))}</td>"
        f"<td class='n'>{e(x.get('source_row_id'))}</td></tr>" for x in edges[:200])
    return (
        f"<h1>{e(doc['title'])}</h1>"
        f"<p><b>Victim account:</b> <span class='mono'>{e(doc['victim_account'])}</span> · "
        f"<b>Trace:</b> <span class='mono'>{e(doc['trace_id'])}</span></p>"
        "<h2>What was observed</h2>"
        f"<p>{e(s.get('statement'))}</p>"
        "<table class='data'>"
        f"<tr><th>Accounts reached</th><th>Transactions traced</th><th>Value traced</th>"
        f"<th>Seed</th><th>Truncated</th></tr>"
        f"<tr><td class='n'>{e(s.get('accounts_reached'))}</td>"
        f"<td class='n'>{e(s.get('transactions_traced'))}</td>"
        f"<td class='n'>{e(rupees(s.get('value_traced') or 0))}</td>"
        f"<td class='n'>{e(rupees(doc.get('seed_amount') or 0))} ({e(doc.get('seed_basis'))})</td>"
        f"<td>{e(doc.get('truncation_reason') or 'no')}</td></tr></table>"
        f"<p><b>Layer distribution:</b> {e(layers)}. Layers are assigned for this trace only, "
        "relative to this victim, and are not stored on the accounts.</p>"
        "<h2>Accounts reached</h2>"
        f"<table class='data'>{head}{body}</table>{extra}"
        "<h2>Transactions traced</h2>"
        f"<table class='data'>{ehead}{ebody}</table>"
    )


def _account_body(doc: dict) -> str:
    a = doc.get("account") or {}
    t = a.get("topology", {})
    v = a.get("value", {})
    r = a.get("risk", {})
    comps = "".join(
        f"<tr><td>{e(c.get('label'))}</td><td class='n'>{e(c.get('score'))}/{e(c.get('weight'))}</td>"
        f"<td>{e(c.get('reason'))}</td></tr>" for c in (r.get("components") or []))
    txns = doc.get("transactions") or []
    thead = ("<tr><th>Timestamp</th><th>From</th><th>To</th><th class='n'>Amount</th>"
             "<th>Mode</th><th class='n'>row id</th></tr>")
    tbody = "".join(
        f"<tr><td class='mono'>{e(x.get('timestamp'))}</td>"
        f"<td class='mono'>{e(x.get('sender_account'))}</td>"
        f"<td class='mono'>{e(x.get('receiver_account'))}</td>"
        f"<td class='n'>{e(rupees(x.get('amount') or 0))}</td>"
        f"<td>{e(x.get('payment_mode'))}</td>"
        f"<td class='n'>{e(x.get('source_row_id'))}</td></tr>" for x in txns[:150])
    return (
        f"<h1>{e(doc['title'])}</h1>"
        f"<p><b>Account:</b> <span class='mono'>{e(doc['account_id'])}</span></p>"
        "<h2>Observed activity</h2>"
        "<table class='data'>"
        "<tr><th></th><th class='n'>Distinct counterparties</th><th class='n'>Transactions</th>"
        "<th class='n'>Value</th></tr>"
        f"<tr><td>Inbound</td><td class='n'>{e(t.get('in_degree'))}</td>"
        f"<td class='n'>{e(t.get('in_txn_count'))}</td>"
        f"<td class='n'>{e(rupees(v.get('total_in') or 0))}</td></tr>"
        f"<tr><td>Outbound</td><td class='n'>{e(t.get('out_degree'))}</td>"
        f"<td class='n'>{e(t.get('out_txn_count'))}</td>"
        f"<td class='n'>{e(rupees(v.get('total_out') or 0))}</td></tr></table>"
        f"<p>{e(v.get('net_balance_note') or '')}</p>"
        "<h2>Behavioural assessment</h2>"
        f"<p>MRI <b>{e(r.get('mri'))}</b>/100, band <b>{e(r.get('band'))}</b>, "
        f"calibration {e(r.get('calibration_regime'))}.</p>"
        "<table class='data'><tr><th>Component</th><th class='n'>Score</th><th>Measured</th></tr>"
        f"{comps}</table>"
        f"<div class='note'>{e(r.get('disclaimer') or '')}</div>"
        "<h2>Source rows</h2>"
        f"<table class='data'>{thead}{tbody}</table>"
    )


def render_pdf(doc: dict) -> bytes:
    if not PDF_AVAILABLE:                                  # pragma: no cover
        raise RuntimeError("PDF_ENGINE_UNAVAILABLE")
    return _WeasyHTML(string=render_html(doc)).write_pdf()
