"""Right panel: batch summary metrics, customer-grouped detail cards, and export.

Documents are grouped for the detail view by taxpayer ID (SSN/TIN/EIN) rather than by name,
since that's the only identifier guaranteed to be the same across a person's W-2 and their
1099s/K-1s — a business name and the underlying individual's name are literally different
strings and can't be linked without an explicit client/entity mapping (out of scope here).
"""
import io
import json
import re
import time

import pandas as pd
import streamlit as st

from src.exceptions import ExtractionError, ExtractionTimeoutError
from src.extraction import extract_and_classify
from src.ledger_data import (
    get_sample_1099_misc_ledger,
    get_sample_general_ledger,
    get_sample_k1_ledger,
    get_sample_payroll_ledger,
)
from src.reconciliation import (
    reconcile_1099_misc,
    reconcile_1099_nec,
    reconcile_k1,
    reconcile_w2,
)

RECONCILERS = {
    "1099-NEC": {
        "reconcile": reconcile_1099_nec,
        "ledger": get_sample_general_ledger,
        "subject": lambda extracted: extracted.recipient_name or "Unknown Recipient",
        "payer": lambda extracted: extracted.payer_name or "Unknown Payer",
        "tin": lambda extracted: extracted.recipient_tin,
        "box_label": "Non-Emp Comp",
    },
    "1099-MISC": {
        "reconcile": reconcile_1099_misc,
        "ledger": get_sample_1099_misc_ledger,
        "subject": lambda extracted: extracted.recipient_name or "Unknown Recipient",
        "payer": lambda extracted: extracted.payer_name or "Unknown Payer",
        "tin": lambda extracted: extracted.recipient_tin,
        "box_label": "Rents + Other",
    },
    "W-2": {
        "reconcile": reconcile_w2,
        "ledger": get_sample_payroll_ledger,
        "subject": lambda extracted: extracted.employee_name or "Unknown Employee",
        "payer": lambda extracted: extracted.employer_name or "Unknown Employer",
        "tin": lambda extracted: extracted.employee_ssn,
        "box_label": "Wages",
    },
    "K-1": {
        "reconcile": reconcile_k1,
        "ledger": get_sample_k1_ledger,
        "subject": lambda extracted: extracted.partner_name or "Unknown Partner",
        "payer": lambda extracted: extracted.partnership_name or "Unknown Partnership",
        "tin": lambda extracted: extracted.partner_tin,
        "box_label": "Ordinary Income",
    },
}


def _process_document(doc: dict) -> dict:
    """Run extraction + reconciliation for one uploaded document. Never raises —
    a failure is captured in the returned dict's "error" key instead."""
    outcome = {
        "doc_name": doc["name"],
        "doc_type": None,
        "extracted": None,
        "reconciliation": None,
        "error": None,
    }
    try:
        extracted, doc_type = extract_and_classify(doc["base64_images"][0])
        reconciler = RECONCILERS[doc_type]
        reconciliation = reconciler["reconcile"](extracted, reconciler["ledger"]())
        outcome["doc_type"] = doc_type
        outcome["extracted"] = extracted
        outcome["reconciliation"] = reconciliation
    except ExtractionTimeoutError as e:
        outcome["error"] = str(e)
    except ExtractionError as e:
        outcome["error"] = str(e)
    except Exception as e:
        outcome["error"] = f"Unexpected error: {e}"
    return outcome


def _currency(value) -> str:
    return f"${value:,.2f}" if value is not None else "N/A"


def _kpi_card(accent: str, label: str, value: str) -> str:
    """Render one Batch Summary card as custom HTML (styled in src/ui/theme.py). Plain
    label + value like st.metric, plus an optional small accent dot (pass accent="" to omit
    it) — st.metric can't render a per-instance colored dot next to its label."""
    accent_class = f" idp-kpi-{accent}" if accent else ""
    dot_html = '<span class="idp-kpi-dot"></span>' if accent else ""
    return (
        f'<div class="idp-kpi-card{accent_class}">'
        f'<div class="idp-kpi-label-row">{dot_html}'
        f'<span class="idp-kpi-label">{label}</span>'
        f"</div>"
        f'<div class="idp-kpi-value">{value}</div>'
        f"</div>"
    )


def _pipeline_stage_html(status: str, label: str) -> str:
    return (
        f'<div class="idp-pipeline-stage idp-pipeline-{status}">'
        f'<span class="idp-pipeline-dot"></span>'
        f'<span class="idp-pipeline-label">{label}</span>'
        f"</div>"
    )


def _pipeline_line_html(connects_completed_stages: bool) -> str:
    cls = "idp-pipeline-line" + (" idp-pipeline-line-done" if connects_completed_stages else "")
    return f'<span class="{cls}"></span>'


def _render_workflow_indicator(documents: list, batch_results) -> None:
    """A small, static state indicator for the Ingested -> Extracted -> Validated ->
    Reconciled workflow shown on the app's own real state (uploaded documents /
    batch_results). Nothing here is animated or advances on its own — each stage requires
    the user's own action (loading files, then clicking Extract & Audit) and this only
    reflects what has already happened as a result of that.

    Extracted and Validated always resolve together: extract_and_classify() performs the
    vision call and Pydantic schema validation as one atomic step (see extraction.py), and
    _process_document() has no way to tell "extraction failed" apart from "extraction
    succeeded but validation failed" — both raise the same ExtractionError. Rather than
    fabricate a distinction the app's data doesn't actually have, both stages share the same
    real signal: whether at least one document has a non-None `extracted` value.
    """
    ingested_done = bool(documents) or bool(batch_results)

    if not batch_results:
        extracted_status = "next" if ingested_done else "pending"
        validated_status = "pending"
        reconciled_status = "pending"
    else:
        validated_count = sum(1 for r in batch_results if r["extracted"] is not None)
        reconciled_count = sum(1 for r in batch_results if r["reconciliation"] is not None)
        reconciled_needs_review = sum(
            1
            for r in batch_results
            if r["reconciliation"] is not None and r["reconciliation"]["status"] != "GREEN"
        )

        extracted_status = "done" if validated_count > 0 else "failed"
        validated_status = extracted_status
        if reconciled_count == 0:
            reconciled_status = "failed"
        elif reconciled_needs_review > 0:
            reconciled_status = "amber"
        else:
            reconciled_status = "done"

    stages = [
        ("done" if ingested_done else "pending", "Ingested"),
        (extracted_status, "Extracted"),
        (validated_status, "Validated"),
        (reconciled_status, "Reconciled"),
    ]

    parts = ['<div class="idp-pipeline">']
    prev_completed = False
    for i, (status, label) in enumerate(stages):
        if i > 0:
            parts.append(_pipeline_line_html(prev_completed))
        parts.append(_pipeline_stage_html(status, label))
        prev_completed = status in ("done", "amber")
    parts.append("</div>")

    st.markdown("".join(parts), unsafe_allow_html=True)


def _mask_tin(tin: str) -> str:
    """Show only the last 4 digits, preserving whichever dash placement the TIN actually
    has: an EIN (business, XX-XXXXXXX) masks as "**-***1234", an SSN (individual,
    XXX-XX-XXXX) as "***-**-1234". Detected from the *input string's own* dash position —
    not digit count alone — since both formats are 9 digits; blindly reformatting every
    9-digit TIN into the SSN shape mislabeled business EINs as if they were personal SSNs.
    Falls back to a plain run of stars for anything that isn't one of those two shapes (e.g.
    a bare 9-digit run with no separators at all, where the format genuinely can't be told
    apart from the digits alone).

    Asterisks are backslash-escaped because this string gets embedded directly in an
    st.expander label, which renders as Markdown — unescaped "***-**-1234" gets parsed as
    bold/italic markup and mangles into something like "*--1234"."""
    raw = (tin or "").strip()
    digits = re.sub(r"\D", "", raw)
    if len(digits) < 4:
        return "Unknown"
    last4 = digits[-4:]
    if re.match(r"^\d{2}-\d{7}$", raw):
        masked = f"**-***{last4}"
    elif re.match(r"^\d{3}-\d{2}-\d{4}$", raw):
        masked = f"***-**-{last4}"
    elif len(digits) == 9:
        # No dash in the source value to go on — keep the prior SSN-shaped default rather
        # than guess, since real extracted/ledger TINs in this app always carry the dash.
        masked = f"***-**-{last4}"
    else:
        masked = f"{'*' * (len(digits) - 4)}{last4}"
    return masked.replace("*", "\\*")


def _mismatch_callout(doc_type: str, mismatch: dict) -> str:
    """Render one structured metadata_mismatch (see reconciliation.py) as
    '[doc_type] Label mismatch: Extracted (...) vs Ledger (...)', masking TIN/EIN/SSN-type
    values to last-4 the same way every other TIN display in this app does."""
    extracted_val = mismatch["extracted"]
    ledger_val = mismatch["ledger"]
    if mismatch["mask"]:
        extracted_val = _mask_tin(extracted_val)
        ledger_val = _mask_tin(ledger_val)
    return (
        f"[{doc_type}] {mismatch['label']} mismatch: "
        f"Extracted ({extracted_val}) vs Ledger ({ledger_val})"
    )


def _customer_badge(green: int, amber: int, red: int) -> str:
    """e.g. '🟢 2 Matches', '🟡 1 Compliance Notice', '🔴 1 Variance', or a combination like
    '🟢 1 Match | 🔴 1 Variance' for a mix."""
    parts = []
    if green:
        parts.append(f"🟢 {green} Match{'es' if green != 1 else ''}")
    if amber:
        parts.append(f"🟡 {amber} Compliance Notice{'s' if amber != 1 else ''}")
    if red:
        parts.append(f"🔴 {red} Variance{'s' if red != 1 else ''}")
    return " | ".join(parts) if parts else "—"


def _status_cell(recon: dict) -> str:
    if recon["status"] == "GREEN":
        return "🟢 Clean Match"
    if recon["status"] == "AMBER":
        return "🟡 Compliance Notice"
    if recon["variance"] is not None:
        sign = "+" if recon["variance"] >= 0 else "-"
        return f"🔴 {sign}${abs(recon['variance']):,.2f}"
    return "🔴 " + (recon["audit_flags"][0] if recon["audit_flags"] else "Discrepancy")


def _group_by_taxpayer(batch_results: list) -> dict:
    """Group successfully-processed documents by normalized taxpayer ID. Documents with no
    extractable TIN each get their own unmerged group (never silently combined)."""
    groups = {}
    for r in batch_results:
        if r["error"]:
            continue
        reconciler = RECONCILERS[r["doc_type"]]
        raw_tin = reconciler["tin"](r["extracted"]) or ""
        digits = re.sub(r"\D", "", raw_tin)
        key = digits if digits else f"__no_tin_{id(r)}"
        group = groups.setdefault(
            key, {"tin_raw": raw_tin, "name": reconciler["subject"](r["extracted"]), "docs": []}
        )
        group["docs"].append(r)
    return groups


def render_results_panel(extract_clicked: bool, documents: list) -> None:
    st.subheader("🧾 Extracted Data & Audit")

    if extract_clicked and documents:
        with st.spinner(
            f"Detecting document type & extracting data for {len(documents)} document(s)..."
        ):
            start = time.time()
            st.session_state["batch_results"] = [_process_document(doc) for doc in documents]
            elapsed = time.time() - start
        st.caption(f"Processed {len(documents)} document(s) in {elapsed:.1f}s")

    batch_results = st.session_state.get("batch_results")

    if documents or batch_results:
        _render_workflow_indicator(documents, batch_results)

    if not batch_results:
        st.info("Upload or load sample document(s), then click **Extract & Audit Document(s)**.")
        return

    # --- Summary metrics -----------------------------------------------------------------
    total_count = len(batch_results)
    green_count = sum(
        1 for r in batch_results if not r["error"] and r["reconciliation"]["status"] == "GREEN"
    )
    amber_count = sum(
        1 for r in batch_results if not r["error"] and r["reconciliation"]["status"] == "AMBER"
    )
    red_count = sum(
        1 for r in batch_results if not r["error"] and r["reconciliation"]["status"] == "RED"
    )
    error_count = sum(1 for r in batch_results if r["error"])

    # "Action Required" reflects the worst thing actually present in the batch: a real dollar
    # variance (or a failed extraction, folded in alongside genuine variances since both need a
    # human to look at the document) turns it red; with no dollar variance but a TIN/tax-year
    # mismatch present, it's a milder amber "compliance notice" instead.
    action_count = red_count + error_count
    if action_count > 0:
        action_accent, action_label = "danger", f"{action_count} Variance{'s' if action_count != 1 else ''}"
    elif amber_count > 0:
        action_accent = "warning"
        action_label = f"{amber_count} Compliance Notice{'s' if amber_count != 1 else ''}"
    else:
        action_accent, action_label = "warning", "0 Variances"

    metric_col1, metric_col2, metric_col3 = st.columns(3)
    metric_col1.markdown(
        _kpi_card(
            "",
            "Documents Processed",
            f"{total_count} File{'s' if total_count != 1 else ''}",
        ),
        unsafe_allow_html=True,
    )
    metric_col2.markdown(
        _kpi_card("success", "Clean Reconciled", f"{green_count} Matched"),
        unsafe_allow_html=True,
    )
    metric_col3.markdown(
        _kpi_card(action_accent, "Action Required", action_label),
        unsafe_allow_html=True,
    )

    error_rows = [r for r in batch_results if r["error"]]
    if error_rows:
        st.markdown("**⚠️ Failed to Process:**")
        for r in error_rows:
            st.error(f"{r['doc_name']}: {r['error']}")

    # --- Customer-grouped detail ---------------------------------------------------------
    st.divider()
    st.markdown("### Customer Reconciliation")

    taxpayer_groups = _group_by_taxpayer(batch_results)

    if not taxpayer_groups:
        st.caption("No successfully extracted documents to group.")
    else:
        for key, group in taxpayer_groups.items():
            docs = group["docs"]
            green = sum(1 for d in docs if d["reconciliation"]["status"] == "GREEN")
            amber = sum(1 for d in docs if d["reconciliation"]["status"] == "AMBER")
            red = sum(1 for d in docs if d["reconciliation"]["status"] == "RED")
            badge = _customer_badge(green, amber, red)
            masked_tin = _mask_tin(group["tin_raw"]) if group["tin_raw"] else "Unknown"

            # Keep the card open across the rerun triggered by its own JSON toggle below —
            # st.expander otherwise snaps back to collapsed on every script rerun, which would
            # hide the JSON the instant a user turns the toggle on.
            json_key = f"json_toggle_{key}"
            with st.expander(
                f"Customer: {group['name']} (TIN: {masked_tin}) — {badge}",
                expanded=st.session_state.get(json_key, False),
            ):
                detail_rows = []
                for d in docs:
                    reconciler = RECONCILERS[d["doc_type"]]
                    recon = d["reconciliation"]
                    payer_name = reconciler["payer"](d["extracted"])
                    detail_rows.append(
                        {
                            "Form Type": f"{d['doc_type']} ({payer_name})",
                            "Box": reconciler["box_label"],
                            "Extracted": _currency(recon["extracted_amount"]),
                            "Ledger Value": _currency(recon["gl_amount"]),
                            "Audit Status": _status_cell(recon),
                        }
                    )
                st.dataframe(pd.DataFrame(detail_rows), use_container_width=True, hide_index=True)

                monetary_items = [
                    (d["doc_type"], flag)
                    for d in docs
                    for flag in d["reconciliation"].get("monetary_flags", [])
                ]
                metadata_items = [
                    (d["doc_type"], mismatch)
                    for d in docs
                    for mismatch in d["reconciliation"].get("metadata_mismatches", [])
                ]

                if monetary_items or metadata_items:
                    st.markdown("**Audit Flags:**")
                    for doc_type, flag in monetary_items:
                        st.warning(f"[{doc_type}] {flag}", icon="⚠️")
                    for doc_type, mismatch in metadata_items:
                        message = _mismatch_callout(doc_type, mismatch)
                        if mismatch["severity"] == "error":
                            st.error(message, icon="🛑")
                        else:
                            st.warning(message, icon="⚠️")
                else:
                    st.caption("No audit flags raised.")

                if st.toggle("Show Raw Extracted JSON", key=json_key):
                    st.json([d["extracted"].model_dump() for d in docs])

    # --- Export ----------------------------------------------------------------------
    # The final workflow stage (Process → Review → Reconcile → Export) — CSV is the primary
    # action (the common CPA/spreadsheet path), JSON secondary but equally accessible. Extra
    # export formats (e.g. a future "Export Audit Report") can join as additional columns
    # without restructuring this section.
    st.divider()
    st.markdown("### Export Results")
    st.caption("Download the processed and audited data")

    export_payload = []
    csv_rows = []
    for r in batch_results:
        if r["error"]:
            export_payload.append({"document_name": r["doc_name"], "error": r["error"]})
            csv_rows.append({"document_name": r["doc_name"], "error": r["error"]})
            continue

        data_dict = r["extracted"].model_dump()
        export_payload.append(
            {
                "document_name": r["doc_name"],
                "document_type": r["doc_type"],
                "extracted_data": data_dict,
                "reconciliation": r["reconciliation"],
            }
        )
        csv_rows.append(
            {
                "document_name": r["doc_name"],
                **data_dict,
                **{f"reconciliation_{k}": v for k, v in r["reconciliation"].items()},
            }
        )

    csv_buf = io.StringIO()
    pd.DataFrame(csv_rows).to_csv(csv_buf, index=False)

    st.download_button(
        "⬇️ Export CSV",
        data=csv_buf.getvalue(),
        file_name="batch_audit.csv",
        mime="text/csv",
        type="primary",
        use_container_width=True,
    )
    # Export JSON disabled per request — hidden from the UI but kept, not deleted, for
    # possible future re-enable. (This was previously the second half of a two-column layout
    # alongside Export CSV; Export CSV now renders full-width on its own.)
    # export_col1, export_col2 = st.columns(2)
    # export_col2.download_button(
    #     "⬇️ Export JSON",
    #     data=json.dumps(export_payload, indent=2, default=str),
    #     file_name="batch_audit.json",
    #     mime="application/json",
    #     use_container_width=True,
    # )
