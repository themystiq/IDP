"""In-memory sample General Ledger. Nothing here is persisted to disk."""
import pandas as pd

def get_sample_general_ledger() -> pd.DataFrame:
    """1099-NEC Ledger Baseline"""
    return pd.DataFrame([
        # 🟢 Clean Match
        {"gl_account": "6010-Contractor Expense", "vendor_name": "Alpine Consulting LLC", "gl_tin": "12-3456789", "amount": 48500.00, "tax_year": 2025},
        # 🟡 Compliance Notice (Zero monetary variance, but TIN typo in GL)
        {"gl_account": "6010-Contractor Expense", "vendor_name": "Harbor Creative Studio", "gl_tin": "98-0000000", "amount": 22750.00, "tax_year": 2025},
        # 🔴 Monetary Variance ($15,000 GL vs $16,200 Doc)
        {"gl_account": "6010-Contractor Expense", "vendor_name": "Redwood Analytics Inc", "gl_tin": "45-1122334", "amount": 15000.00, "tax_year": 2025},
        # 🟢 Clean Match
        {"gl_account": "6010-Contractor Expense", "vendor_name": "Dwarum Inc", "gl_tin": "88-1234567", "amount": 65228.00, "tax_year": 2025},
        # 🟢 Clean Match (John Doe #1 - Groups under TIN 111-22-3333)
        {"gl_account": "6010-Contractor Expense", "vendor_name": "John Doe", "gl_tin": "111-22-3333", "amount": 12500.00, "tax_year": 2025},
    ])

def get_sample_1099_misc_ledger() -> pd.DataFrame:
    """1099-MISC Ledger Baseline"""
    return pd.DataFrame([
        # 🟢 Clean Match
        {"gl_account": "6030-Rent Expense", "vendor_name": "Cedar Point Properties LLC", "gl_tin": "33-2211445", "amount": 24000.00, "tax_year": 2025},
        # 🟢 Clean Match
        {"gl_account": "6040-Other Income", "vendor_name": "Bright Path Media Group", "gl_tin": "56-7788990", "amount": 5400.00, "tax_year": 2025},
        # 🔴 Monetary Variance ($9,600 GL vs $7,200 Doc)
        {"gl_account": "6030-Rent Expense", "vendor_name": "Lakeside Storage Partners", "gl_tin": "61-3344556", "amount": 9600.00, "tax_year": 2025},
    ])

def get_sample_payroll_ledger() -> pd.DataFrame:
    """W-2 Payroll Ledger Baseline"""
    return pd.DataFrame([
        # 🟢 Clean Match
        {"gl_account": "6020-Salaries & Wages", "employee_name": "Jordan Ellis", "employee_ssn": "123-45-6789", "employer_ein": "77-9182736", "wages": 82000.00, "tax_year": 2025},
        # 🟢 Clean Match
        {"gl_account": "6020-Salaries & Wages", "employee_name": "Priya Nandakumar", "employee_ssn": "234-56-7890", "employer_ein": "77-9182736", "wages": 95500.00, "tax_year": 2025},
        # 🔴 Monetary Variance ($61,000 GL vs $58,000 Doc)
        {"gl_account": "6020-Salaries & Wages", "employee_name": "Sam Whitfield", "employee_ssn": "345-67-8901", "employer_ein": "77-9182736", "wages": 61000.00, "tax_year": 2025},
        # 🔴 Monetary Variance ($82,000 GL vs $85,000 Doc) — John Doe #2 (Groups under TIN 111-22-3333)
        {"gl_account": "6020-Salaries & Wages", "employee_name": "John Doe", "employee_ssn": "111-22-3333", "employer_ein": "20-1234567", "wages": 82000.00, "tax_year": 2025},
        # 🔴 Monetary Variance ($130,000 GL vs $138,958.41 Doc)
        {"gl_account": "6020-Salaries & Wages", "employee_name": "Rachel Green", "employee_ssn": "222-33-4444", "employer_ein": "77-9182736", "wages": 130000.00, "tax_year": 2025},
    ])

def get_sample_k1_ledger() -> pd.DataFrame:
    """Schedule K-1 Ledger Baseline"""
    return pd.DataFrame([
        # 🟡 Compliance Notice ($45,000 matches, but GL is tax year 2024 vs 2025 Form)
        {"gl_account": "6050-K-1 Pass-Through", "partner_name": "Jane Smith", "gl_tin": "333-44-5555", "amount": 45000.00, "tax_year": 2024},
    ])
