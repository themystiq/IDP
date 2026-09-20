"""Sample 1099-NEC/1099-MISC/W-2/Schedule K-1 PDFs, built by filling the real, blank IRS
form templates in documents/ with the same client data used by src/ledger_data.py.

Each builder fills the recipient/employee "Copy B" page of the official template (found by
searching each PDF's page text for "Copy B"/"For Recipient") via PyMuPDF's AcroForm widget
API, then extracts just that one filled page into a standalone single-page PDF — the app's
extraction pipeline only ever reads page 1 of an uploaded document, and the templates
themselves are multi-page (Copy A, Copy 1, Copy B, instructions, ...).

Field names on these templates are auto-generated and non-descriptive (e.g. "f2_20[0]"), so
each mapping below was derived by correlating each widget's on-page position with the nearby
printed box label, not by reading the field name itself.

The templates carry no fillable "tax year" field on their Copy B page for W-2 or Schedule
K-1 (the year is preprinted directly on the form), so `tax_year` has no effect for those two
builders — noted inline where it's silently ignored.
"""
import io
import re
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF

_DOCUMENTS_DIR = Path(__file__).resolve().parents[1] / "documents"

_NEC_TEMPLATE = _DOCUMENTS_DIR / "f1099nec.pdf"
_MISC_TEMPLATE = _DOCUMENTS_DIR / "f1099msc.pdf"
_W2_TEMPLATE = _DOCUMENTS_DIR / "fw2.pdf"
_K1_TEMPLATE = _DOCUMENTS_DIR / "f1065sk1.pdf"

_NEC_COPY_B_PAGE = 3
_MISC_COPY_B_PAGE = 3
_W2_COPY_B_PAGE = 3
_K1_PAGE = 0  # single-page form, no copy variants


def _fill_and_extract(template_path: Path, page_index: int, field_values: dict[str, str]) -> bytes:
    """Fill named AcroForm fields on one page of a template, then return that page alone
    as a new single-page PDF."""
    src_doc = fitz.open(template_path)
    page = src_doc[page_index]
    for widget in page.widgets():
        if widget.field_name in field_values:
            widget.field_value = field_values[widget.field_name]
            widget.update()

    out_doc = fitz.open()
    out_doc.insert_pdf(src_doc, from_page=page_index, to_page=page_index)
    buf = io.BytesIO()
    out_doc.save(buf)
    out_doc.close()
    src_doc.close()
    return buf.getvalue()


def _build_1099_nec_pdf(
    payer_name: str,
    payer_tin: str,
    recipient_name: str,
    recipient_tin: str,
    nonemployee_compensation: float,
    federal_tax_withheld: float,
    tax_year: str,
) -> bytes:
    fields = {
        "topmostSubform[0].CopyB[0].PgHeader[0].CalendarYear[0].f2_1[0]": tax_year,
        "topmostSubform[0].CopyB[0].LeftCol[0].f2_2[0]": payer_name,
        "topmostSubform[0].CopyB[0].LeftCol[0].f2_10[0]": payer_tin,
        "topmostSubform[0].CopyB[0].LeftCol[0].f2_11[0]": recipient_tin,
        "topmostSubform[0].CopyB[0].LeftCol[0].f2_12[0]": recipient_name,
        "topmostSubform[0].CopyB[0].RightCol[0].f2_20[0]": f"{nonemployee_compensation:,.2f}",
        "topmostSubform[0].CopyB[0].RightCol[0].f2_26[0]": f"{federal_tax_withheld:,.2f}",
    }
    return _fill_and_extract(_NEC_TEMPLATE, _NEC_COPY_B_PAGE, fields)


def _build_1099_misc_pdf(
    payer_name: str,
    payer_tin: str,
    recipient_name: str,
    recipient_tin: str,
    rents: Optional[float],
    other_income: Optional[float],
    tax_year: str,
) -> bytes:
    fields = {
        "topmostSubform[0].CopyB[0].CopyHeader[0].CalendarYear[0].f2_1[0]": tax_year,
        "topmostSubform[0].CopyB[0].LeftColumn[0].f2_2[0]": payer_name,
        "topmostSubform[0].CopyB[0].LeftColumn[0].f2_10[0]": payer_tin,
        "topmostSubform[0].CopyB[0].LeftColumn[0].f2_11[0]": recipient_tin,
        "topmostSubform[0].CopyB[0].LeftColumn[0].f2_12[0]": recipient_name,
    }
    # Boxes are only filled when populated, matching a real form where an unused box is
    # left blank rather than printed as "$0.00".
    if rents is not None:
        fields["topmostSubform[0].CopyB[0].RightColumn[0].f2_20[0]"] = f"{rents:,.2f}"
    if other_income is not None:
        fields["topmostSubform[0].CopyB[0].RightColumn[0].Box3_ReadOrder[0].f2_22[0]"] = (
            f"{other_income:,.2f}"
        )
    return _fill_and_extract(_MISC_TEMPLATE, _MISC_COPY_B_PAGE, fields)


def _build_w2_pdf(
    employer_name: str,
    employer_ein: str,
    employee_name: str,
    employee_ssn: str,
    wages_tips_other_comp: float,
    federal_income_tax_withheld: float,
    tax_year: str,  # noqa: ARG001 — no fillable year field on this template's Copy B page
) -> bytes:
    first_name, _, last_name = employee_name.rpartition(" ")
    fields = {
        "topmostSubform[0].CopyB[0].CopyB_Top[0].BoxA_ReadOrder[0].f2_01[0]": employee_ssn,
        "topmostSubform[0].CopyB[0].CopyB_Top[0].Col_Left[0].f2_02[0]": employer_ein,
        "topmostSubform[0].CopyB[0].CopyB_Top[0].Col_Left[0].f2_03[0]": employer_name,
        "topmostSubform[0].CopyB[0].CopyB_Top[0].Col_Left[0]."
        "FirstName_ReadOrder[0].f2_05[0]": first_name or employee_name,
        "topmostSubform[0].CopyB[0].CopyB_Top[0].Col_Left[0]."
        "LastName_ReadOrder[0].f2_06[0]": last_name,
        "topmostSubform[0].CopyB[0].CopyB_Top[0].Col_Right[0]."
        "Box1_ReadOrder[0].f2_09[0]": f"{wages_tips_other_comp:,.2f}",
        "topmostSubform[0].CopyB[0].CopyB_Top[0].Col_Right[0].f2_10[0]": (
            f"{federal_income_tax_withheld:,.2f}"
        ),
    }
    return _fill_and_extract(_W2_TEMPLATE, _W2_COPY_B_PAGE, fields)


def _build_k1_pdf(
    partnership_name: str,
    partnership_ein: str,
    partner_name: str,
    partner_tin: str,
    ordinary_business_income: float,
    net_rental_real_estate_income: Optional[float],
    tax_year: str,  # noqa: ARG001 — no fillable year field on this template
) -> bytes:
    fields = {
        "topmostSubform[0].Page1[0].LeftCol[0].f1_6[0]": partnership_ein,
        "topmostSubform[0].Page1[0].LeftCol[0].f1_7[0]": partnership_name,
        "topmostSubform[0].Page1[0].LeftCol[0].f1_9[0]": partner_tin,
        "topmostSubform[0].Page1[0].LeftCol[0].f1_10[0]": partner_name,
        "topmostSubform[0].Page1[0].RightCol[0].RightCol1[0].f1_34[0]": (
            f"{ordinary_business_income:,.2f}"
        ),
    }
    if net_rental_real_estate_income is not None:
        fields["topmostSubform[0].Page1[0].RightCol[0].RightCol1[0].f1_35[0]"] = (
            f"{net_rental_real_estate_income:,.2f}"
        )
    return _fill_and_extract(_K1_TEMPLATE, _K1_PAGE, fields)


_BUILDERS = {
    "1099-NEC": _build_1099_nec_pdf,
    "1099-MISC": _build_1099_misc_pdf,
    "W-2": _build_w2_pdf,
    "K-1": _build_k1_pdf,
}

# Declarative client data only — no PDF is built until a specific sample is requested,
# since building all of them means opening the (multi-MB) real templates repeatedly.
_SAMPLE_SPECS: dict[str, dict[str, dict]] = {
    "1099-NEC": {
        "Sample A - Clean Match (Alpine Consulting)": dict(
            payer_name="Meridian Partners Group", payer_tin="77-9182736",
            recipient_name="Alpine Consulting LLC", recipient_tin="12-3456789",
            nonemployee_compensation=48500.00, federal_tax_withheld=6798.00, tax_year="2025",
        ),
        "Sample B - Clean Match (Harbor Creative)": dict(
            payer_name="Meridian Partners Group", payer_tin="77-9182736",
            recipient_name="Harbor Creative Studio", recipient_tin="98-7654321",
            nonemployee_compensation=22750.00, federal_tax_withheld=3185.00, tax_year="2025",
        ),
        "Sample C - Variance Flag (Redwood Analytics)": dict(
            payer_name="Meridian Partners Group", payer_tin="77-9182736",
            recipient_name="Redwood Analytics Inc", recipient_tin="45-1122334",
            nonemployee_compensation=16200.00, federal_tax_withheld=2268.00, tax_year="2025",
        ),
        "Sample J - Clean Match (Dwarum Inc)": dict(
            payer_name="Meridian Partners Group", payer_tin="77-9182736",
            recipient_name="Dwarum Inc", recipient_tin="88-1234567",
            nonemployee_compensation=65228.00, federal_tax_withheld=9132.00, tax_year="2025",
        ),
        "Sample K - Clean Match (John Doe consulting)": dict(
            payer_name="Meridian Partners Group", payer_tin="77-9182736",
            recipient_name="John Doe", recipient_tin="111-22-3333",
            nonemployee_compensation=12500.00, federal_tax_withheld=1750.00, tax_year="2025",
        ),
    },
    "1099-MISC": {
        "Sample G - Clean Match (Cedar Point Properties)": dict(
            payer_name="Meridian Partners Group", payer_tin="77-9182736",
            recipient_name="Cedar Point Properties LLC", recipient_tin="33-2211445",
            rents=24000.00, other_income=None, tax_year="2025",
        ),
        "Sample H - Clean Match (Bright Path Media)": dict(
            payer_name="Meridian Partners Group", payer_tin="77-9182736",
            recipient_name="Bright Path Media Group", recipient_tin="56-7788990",
            rents=None, other_income=5400.00, tax_year="2025",
        ),
        "Sample I - Variance Flag (Lakeside Storage)": dict(
            payer_name="Meridian Partners Group", payer_tin="77-9182736",
            recipient_name="Lakeside Storage Partners", recipient_tin="61-3344556",
            rents=7200.00, other_income=None, tax_year="2025",
        ),
    },
    "W-2": {
        "Sample D - Clean Match (Jordan Ellis)": dict(
            employer_name="Meridian Partners Group", employer_ein="77-9182736",
            employee_name="Jordan Ellis", employee_ssn="123-45-6789",
            wages_tips_other_comp=82000.00, federal_income_tax_withheld=11480.00, tax_year="2025",
        ),
        "Sample E - Clean Match (Priya Nandakumar)": dict(
            employer_name="Meridian Partners Group", employer_ein="77-9182736",
            employee_name="Priya Nandakumar", employee_ssn="234-56-7890",
            wages_tips_other_comp=95500.00, federal_income_tax_withheld=14325.00, tax_year="2025",
        ),
        "Sample F - Variance Flag (Sam Whitfield)": dict(
            employer_name="Meridian Partners Group", employer_ein="77-9182736",
            employee_name="Sam Whitfield", employee_ssn="345-67-8901",
            wages_tips_other_comp=58000.00, federal_income_tax_withheld=7250.00, tax_year="2025",
        ),
        "Sample L - Clean Match (John Doe employment)": dict(
            employer_name="Acme Corp", employer_ein="20-1234567",
            employee_name="John Doe", employee_ssn="111-22-3333",
            wages_tips_other_comp=85000.00, federal_income_tax_withheld=11900.00, tax_year="2025",
        ),
        "Sample M - Variance Flag (Rachel Green)": dict(
            employer_name="Meridian Partners Group", employer_ein="77-9182736",
            employee_name="Rachel Green", employee_ssn="222-33-4444",
            wages_tips_other_comp=138958.41, federal_income_tax_withheld=19454.00, tax_year="2025",
        ),
    },
    "K-1": {
        "Sample N - Variance Flag (Jane Smith)": dict(
            partnership_name="Blue Ridge Holdings LP", partnership_ein="99-8765432",
            partner_name="Jane Smith", partner_tin="333-44-5555",
            ordinary_business_income=45000.00, net_rental_real_estate_income=None, tax_year="2025",
        ),
    },
}


def get_sample_catalog() -> dict[str, list[str]]:
    """doc_type -> list of sample labels, with no PDF built — cheap enough to call on
    every rerun to populate a picker."""
    return {doc_type: list(samples.keys()) for doc_type, samples in _SAMPLE_SPECS.items()}


def build_sample(doc_type: str, label: str) -> bytes:
    """Fill and return just the one requested sample document."""
    return _BUILDERS[doc_type](**_SAMPLE_SPECS[doc_type][label])


def get_sample_documents() -> dict[str, dict[str, bytes]]:
    """Eagerly build every sample. Used by the documents/ generation script below, not by
    the live app (see build_sample for the on-demand, single-sample path the sidebar uses)."""
    return {
        doc_type: {label: build_sample(doc_type, label) for label in labels}
        for doc_type, labels in get_sample_catalog().items()
    }


if __name__ == "__main__":
    for doc_type, samples in get_sample_documents().items():
        for label, pdf_bytes in samples.items():
            slug = re.sub(r"[^A-Za-z0-9]+", "_", label).strip("_")
            out_path = _DOCUMENTS_DIR / f"{doc_type}__{slug}.pdf"
            out_path.write_bytes(pdf_bytes)
            print(f"wrote {out_path.relative_to(_DOCUMENTS_DIR.parent)}")
