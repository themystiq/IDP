"""Pydantic schemas for extraction output.

Form1099NEC / Form1099Misc / FormW2 / FormK1 are the four *reconciled* form types — each has
a matching ledger and reconcile_<type> function (see reconciliation.py). BankStatement /
PayrollSummary / EINLetter / BalanceSheet / CreditCardStatement are *informational* document
types: the model can identify them and pull a few headline fields, but there's no ledger to
audit them against, so they're classified and displayed as-is rather than run through
reconciliation — see extraction.py's INFORMATIONAL_DOC_TYPES and results_panel.py's handling
of doc types in that set.

All fields except document_type are optional: the vision model is instructed to return null
for anything it can't read rather than guess, and the reconciliation engine handles missing
values explicitly (see reconciliation.py) instead of relying on schema validation to reject
incomplete extractions.
"""
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class Form1099NEC(BaseModel):
    document_type: str = "1099-NEC"
    payer_name: Optional[str] = None
    payer_tin: Optional[str] = None
    recipient_name: Optional[str] = None
    recipient_tin: Optional[str] = None
    nonemployee_compensation: Optional[float] = Field(None, description="Box 1 compensation")
    federal_tax_withheld: Optional[float] = Field(None, description="Box 4 tax withheld")
    tax_year: Optional[str] = None

    @field_validator("nonemployee_compensation", "federal_tax_withheld")
    @classmethod
    def validate_amount(cls, v: Optional[float]) -> Optional[float]:
        if v is None:
            return v
        if v < 0:
            raise ValueError("amount cannot be negative")
        return round(v, 2)


class Form1099Misc(BaseModel):
    document_type: str = "1099-MISC"
    payer_name: Optional[str] = None
    payer_tin: Optional[str] = None
    recipient_name: Optional[str] = None
    recipient_tin: Optional[str] = None
    rents: Optional[float] = Field(None, description="Box 1 rents")
    other_income: Optional[float] = Field(None, description="Box 3 other income")
    tax_year: Optional[str] = None

    @field_validator("rents", "other_income")
    @classmethod
    def validate_amount(cls, v: Optional[float]) -> Optional[float]:
        if v is None:
            return v
        if v < 0:
            raise ValueError("amount cannot be negative")
        return round(v, 2)


class FormW2(BaseModel):
    document_type: str = "W2"
    employer_name: Optional[str] = None
    employer_ein: Optional[str] = None
    employee_name: Optional[str] = None
    employee_ssn: Optional[str] = None
    wages_tips_other_comp: Optional[float] = Field(None, description="Box 1 wages")
    federal_income_tax_withheld: Optional[float] = Field(None, description="Box 2 tax withheld")
    tax_year: Optional[str] = None

    @field_validator("wages_tips_other_comp", "federal_income_tax_withheld")
    @classmethod
    def validate_amount(cls, v: Optional[float]) -> Optional[float]:
        if v is None:
            return v
        if v < 0:
            raise ValueError("amount cannot be negative")
        return round(v, 2)


class BankStatement(BaseModel):
    """Informational only — no ledger exists to reconcile a bank statement against, so
    this (and the three schemas below it) are classify-and-display, not audited."""

    document_type: str = "Bank Statement"
    bank_statement_holder_name: Optional[str] = None
    bank_name: Optional[str] = None
    bank_account_last4: Optional[str] = None
    bank_statement_period: Optional[str] = None
    bank_statement_ending_balance: Optional[float] = None


class PayrollSummary(BaseModel):
    """Informational only — see BankStatement docstring."""

    document_type: str = "Payroll Summary"
    payroll_company_name: Optional[str] = None
    payroll_period: Optional[str] = None
    payroll_total_gross_pay: Optional[float] = None
    payroll_employee_count: Optional[int] = None


class EINLetter(BaseModel):
    """Informational only — see BankStatement docstring."""

    document_type: str = "EIN Letter"
    ein_letter_entity_name: Optional[str] = None
    ein_letter_ein: Optional[str] = None
    ein_letter_date_issued: Optional[str] = None


class BalanceSheet(BaseModel):
    """Informational only — see BankStatement docstring."""

    document_type: str = "Balance Sheet"
    balance_sheet_company_name: Optional[str] = None
    balance_sheet_as_of_date: Optional[str] = None
    balance_sheet_total_assets: Optional[float] = None
    balance_sheet_total_liabilities: Optional[float] = None
    balance_sheet_total_equity: Optional[float] = None


class CreditCardStatement(BaseModel):
    """Informational only — see BankStatement docstring."""

    document_type: str = "Credit Card Statement"
    credit_card_holder_name: Optional[str] = None
    credit_card_issuer: Optional[str] = None
    credit_card_last4: Optional[str] = None
    credit_card_statement_period: Optional[str] = None
    credit_card_statement_balance: Optional[float] = None


class FormK1(BaseModel):
    document_type: str = "K-1"
    partnership_name: Optional[str] = None
    partnership_ein: Optional[str] = None
    partner_name: Optional[str] = None
    partner_tin: Optional[str] = None
    ordinary_business_income: Optional[float] = Field(
        None, description="Box 1 ordinary business income (loss)"
    )
    net_rental_real_estate_income: Optional[float] = Field(
        None, description="Box 2 net rental real estate income (loss)"
    )
    tax_year: Optional[str] = None

    @field_validator("ordinary_business_income", "net_rental_real_estate_income")
    @classmethod
    def round_amount(cls, v: Optional[float]) -> Optional[float]:
        # Unlike the other forms' box amounts, K-1 Box 1/Box 2 are legitimately allowed to
        # be negative (a partner's share can be a loss), so no non-negative check here.
        if v is None:
            return v
        return round(v, 2)
