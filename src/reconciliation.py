"""Pandas-based reconciliation of extracted document amounts against in-memory ledgers.

Design notes:
- Status is three-way: GREEN (no discrepancies), AMBER (a metadata-only mismatch — TIN/EIN or
  tax year — with the dollar amount tying out), or RED (a real dollar variance, or the amount
  couldn't be extracted at all). Each reconciler separates its findings into
  `monetary_flags` (plain-string messages — missing/mismatched box amount) and
  `metadata_mismatches` (structured records — TIN/EIN, tax year) before deciding status, so a
  document with only a TIN or tax-year mismatch reads as a milder "compliance notice" rather
  than the same red "variance" a real dollar mismatch gets — while still surfacing the issue
  rather than hiding it behind "variance == 0".
- `metadata_mismatches` is a list of dicts — `{"field", "label", "extracted", "ledger",
  "severity", "mask"}` — rather than pre-formatted strings, so the UI layer (results_panel.py)
  can render the exact "Extracted (...) vs Ledger (...)" callout with masked TIN/EIN/SSN values
  where `mask` is True, and pick `st.error`/`st.warning` from `severity` ("error"/"warning").
  `audit_flags` still carries a flattened, human-readable string for every finding (monetary
  and metadata alike) for CSV/JSON export and any place that just wants plain text — the two
  representations are built from the same checks so they can't drift out of sync.
- When no ledger entry exists for an extracted name, gl_amount defaults to 0.00 (not None) so
  that variance = extracted_amount - 0.00 is still a real, displayable/sortable number instead
  of a "None" that breaks currency formatting and downstream math. The "no ledger entry found"
  audit flag still fires so this isn't mistaken for a genuine zero-dollar ledger entry.
- All four form-type reconcilers below return the same dict shape so the UI layer can render
  any of them generically.
"""
import pandas as pd

from src.schemas import Form1099Misc, Form1099NEC, FormK1, FormW2

VARIANCE_TOLERANCE = 0.005  # tolerate sub-cent floating point rounding


def _tax_year_mismatch(extracted_tax_year, gl_tax_year) -> bool:
    """Both sides are optional/loosely typed (string vs int), so compare as strings
    and only flag a mismatch when both sides are actually present."""
    if not extracted_tax_year or gl_tax_year is None:
        return False
    return str(extracted_tax_year) != str(gl_tax_year)


def _metadata_mismatch(field: str, label: str, extracted_val, ledger_val, severity: str, mask: bool) -> dict:
    return {
        "field": field,
        "label": label,
        "extracted": extracted_val,
        "ledger": ledger_val,
        "severity": severity,
        "mask": mask,
    }


def _mismatch_flag_text(mismatch: dict) -> str:
    """Plain-string rendering of a structured mismatch, for audit_flags/CSV/JSON — the UI
    layer renders its own masked version of the same fields for on-screen callouts."""
    return (
        f"{mismatch['label']} mismatch: Extracted ({mismatch['extracted']}) "
        f"vs Ledger ({mismatch['ledger']})"
    )


def _no_match_result(extracted_amount, reason: str) -> dict:
    """Shared 'no ledger entry found' result: ledger defaults to 0.00, and variance is
    computed against that default whenever an extracted amount is available."""
    variance = round(extracted_amount - 0.0, 2) if extracted_amount is not None else None
    return {
        "status": "RED",
        "match_found": False,
        "gl_amount": 0.00,
        "extracted_amount": extracted_amount,
        "variance": variance,
        "audit_flags": [reason],
        "monetary_flags": [reason],
        "metadata_mismatches": [],
    }


def reconcile_1099_nec(extracted: Form1099NEC, ledger_df: pd.DataFrame) -> dict:
    if not extracted.recipient_name:
        return _no_match_result(
            extracted.nonemployee_compensation,
            "Recipient name could not be extracted from the document.",
        )

    matches = ledger_df[
        ledger_df["vendor_name"].str.strip().str.lower()
        == extracted.recipient_name.strip().lower()
    ]

    if matches.empty:
        return _no_match_result(
            extracted.nonemployee_compensation,
            f"No General Ledger entry found for recipient '{extracted.recipient_name}'.",
        )

    gl_row = matches.iloc[0]
    gl_amount = float(gl_row["amount"])
    monetary_flags = []
    metadata_mismatches = []

    if extracted.nonemployee_compensation is None:
        variance = None
        monetary_flags.append(
            "Nonemployee compensation (Box 1) could not be extracted from the document."
        )
    else:
        variance = round(extracted.nonemployee_compensation - gl_amount, 2)
        if abs(variance) > VARIANCE_TOLERANCE:
            monetary_flags.append(
                f"Variance of ${variance:,.2f} between extracted Box 1 and GL amount."
            )

    if (
        gl_row.get("gl_tin")
        and extracted.recipient_tin
        and gl_row["gl_tin"] != extracted.recipient_tin
    ):
        metadata_mismatches.append(
            _metadata_mismatch(
                "recipient_tin", "Recipient TIN", extracted.recipient_tin, gl_row["gl_tin"],
                "warning", mask=True,
            )
        )
    if _tax_year_mismatch(extracted.tax_year, gl_row.get("tax_year")):
        metadata_mismatches.append(
            _metadata_mismatch(
                "tax_year", "Tax year", extracted.tax_year, gl_row.get("tax_year"),
                "warning", mask=False,
            )
        )

    status = "RED" if monetary_flags else "AMBER" if metadata_mismatches else "GREEN"

    return {
        "status": status,
        "match_found": True,
        "gl_amount": gl_amount,
        "extracted_amount": extracted.nonemployee_compensation,
        "variance": variance,
        "audit_flags": monetary_flags + [_mismatch_flag_text(m) for m in metadata_mismatches],
        "monetary_flags": monetary_flags,
        "metadata_mismatches": metadata_mismatches,
        "gl_account": gl_row.get("gl_account"),
    }


def reconcile_1099_misc(extracted: Form1099Misc, ledger_df: pd.DataFrame) -> dict:
    extracted_amount = None
    if extracted.rents is not None or extracted.other_income is not None:
        extracted_amount = round((extracted.rents or 0) + (extracted.other_income or 0), 2)

    if not extracted.recipient_name:
        return _no_match_result(
            extracted_amount, "Recipient name could not be extracted from the document."
        )

    matches = ledger_df[
        ledger_df["vendor_name"].str.strip().str.lower()
        == extracted.recipient_name.strip().lower()
    ]

    if matches.empty:
        return _no_match_result(
            extracted_amount,
            f"No General Ledger entry found for recipient '{extracted.recipient_name}'.",
        )

    gl_row = matches.iloc[0]
    gl_amount = float(gl_row["amount"])
    monetary_flags = []
    metadata_mismatches = []

    if extracted_amount is None:
        variance = None
        monetary_flags.append(
            "Box 1 (rents) and Box 3 (other income) could not be extracted from the document."
        )
    else:
        variance = round(extracted_amount - gl_amount, 2)
        if abs(variance) > VARIANCE_TOLERANCE:
            monetary_flags.append(
                f"Variance of ${variance:,.2f} between extracted 1099-MISC total "
                "(Box 1 + Box 3) and GL amount."
            )

    if (
        gl_row.get("gl_tin")
        and extracted.recipient_tin
        and gl_row["gl_tin"] != extracted.recipient_tin
    ):
        metadata_mismatches.append(
            _metadata_mismatch(
                "recipient_tin", "Recipient TIN", extracted.recipient_tin, gl_row["gl_tin"],
                "warning", mask=True,
            )
        )
    if _tax_year_mismatch(extracted.tax_year, gl_row.get("tax_year")):
        metadata_mismatches.append(
            _metadata_mismatch(
                "tax_year", "Tax year", extracted.tax_year, gl_row.get("tax_year"),
                "warning", mask=False,
            )
        )

    status = "RED" if monetary_flags else "AMBER" if metadata_mismatches else "GREEN"

    return {
        "status": status,
        "match_found": True,
        "gl_amount": gl_amount,
        "extracted_amount": extracted_amount,
        "variance": variance,
        "audit_flags": monetary_flags + [_mismatch_flag_text(m) for m in metadata_mismatches],
        "monetary_flags": monetary_flags,
        "metadata_mismatches": metadata_mismatches,
        "gl_account": gl_row.get("gl_account"),
    }


def reconcile_w2(extracted: FormW2, payroll_df: pd.DataFrame) -> dict:
    if not extracted.employee_name:
        return _no_match_result(
            extracted.wages_tips_other_comp,
            "Employee name could not be extracted from the document.",
        )

    matches = payroll_df[
        payroll_df["employee_name"].str.strip().str.lower()
        == extracted.employee_name.strip().lower()
    ]

    if matches.empty:
        return _no_match_result(
            extracted.wages_tips_other_comp,
            f"No payroll ledger entry found for employee '{extracted.employee_name}'.",
        )

    gl_row = matches.iloc[0]
    gl_amount = float(gl_row["wages"])
    monetary_flags = []
    metadata_mismatches = []

    if extracted.wages_tips_other_comp is None:
        variance = None
        monetary_flags.append("Wages (Box 1) could not be extracted from the document.")
    else:
        variance = round(extracted.wages_tips_other_comp - gl_amount, 2)
        if abs(variance) > VARIANCE_TOLERANCE:
            monetary_flags.append(
                f"Variance of ${variance:,.2f} between extracted wages and payroll ledger amount."
            )

    if (
        gl_row.get("employer_ein")
        and extracted.employer_ein
        and gl_row["employer_ein"] != extracted.employer_ein
    ):
        metadata_mismatches.append(
            _metadata_mismatch(
                "employer_ein", "Employer EIN", extracted.employer_ein, gl_row["employer_ein"],
                "warning", mask=True,
            )
        )

    status = "RED" if monetary_flags else "AMBER" if metadata_mismatches else "GREEN"

    return {
        "status": status,
        "match_found": True,
        "gl_amount": gl_amount,
        "extracted_amount": extracted.wages_tips_other_comp,
        "variance": variance,
        "audit_flags": monetary_flags + [_mismatch_flag_text(m) for m in metadata_mismatches],
        "monetary_flags": monetary_flags,
        "metadata_mismatches": metadata_mismatches,
        "gl_account": gl_row.get("gl_account"),
    }


def reconcile_k1(extracted: FormK1, ledger_df: pd.DataFrame) -> dict:
    if not extracted.partner_name:
        return _no_match_result(
            extracted.ordinary_business_income,
            "Partner name could not be extracted from the document.",
        )

    matches = ledger_df[
        ledger_df["partner_name"].str.strip().str.lower()
        == extracted.partner_name.strip().lower()
    ]

    if matches.empty:
        return _no_match_result(
            extracted.ordinary_business_income,
            f"No K-1 ledger entry found for partner '{extracted.partner_name}'.",
        )

    gl_row = matches.iloc[0]
    gl_amount = float(gl_row["amount"])
    monetary_flags = []
    metadata_mismatches = []

    if extracted.ordinary_business_income is None:
        variance = None
        monetary_flags.append(
            "Ordinary business income (Box 1) could not be extracted from the document."
        )
    else:
        variance = round(extracted.ordinary_business_income - gl_amount, 2)
        if abs(variance) > VARIANCE_TOLERANCE:
            monetary_flags.append(
                f"Variance of ${variance:,.2f} between extracted Box 1 and K-1 ledger amount."
            )

    if (
        gl_row.get("gl_tin")
        and extracted.partner_tin
        and gl_row["gl_tin"] != extracted.partner_tin
    ):
        metadata_mismatches.append(
            _metadata_mismatch(
                "partner_tin", "Partner TIN", extracted.partner_tin, gl_row["gl_tin"],
                "warning", mask=True,
            )
        )
    if _tax_year_mismatch(extracted.tax_year, gl_row.get("tax_year")):
        metadata_mismatches.append(
            _metadata_mismatch(
                "tax_year", "Tax year", extracted.tax_year, gl_row.get("tax_year"),
                "warning", mask=False,
            )
        )

    status = "RED" if monetary_flags else "AMBER" if metadata_mismatches else "GREEN"

    return {
        "status": status,
        "match_found": True,
        "gl_amount": gl_amount,
        "extracted_amount": extracted.ordinary_business_income,
        "variance": variance,
        "audit_flags": monetary_flags + [_mismatch_flag_text(m) for m in metadata_mismatches],
        "monetary_flags": monetary_flags,
        "metadata_mismatches": metadata_mismatches,
        "gl_account": gl_row.get("gl_account"),
    }
