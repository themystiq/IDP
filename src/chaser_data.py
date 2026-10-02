"""Declarative client/checklist data for the Document Chaser feature (see document_chaser.py
for the scanning/matching logic, and chaser_fixtures.py for how each client's folder is
populated). Nothing here is persisted beyond the checked-in demo fixtures — this mirrors
ledger_data.py's role for the main IDP workflow.

Each checklist item's "expected_subject" is matched against the extracted document's own
identity field (see document_chaser._SUBJECT_ATTR) to catch not just missing documents but
the wrong document for this client — see Sam Whitfield below.
"""
from pathlib import Path

CLIENTS_DIR = Path(__file__).resolve().parents[1] / "documents" / "clients"

CLIENT_CHECKLISTS = [
    {
        "client_name": "John Doe",
        "folder": "John_Doe",
        "checklist": [
            {"doc_type": "1099-NEC", "expected_subject": "John Doe"},
            {"doc_type": "W-2", "expected_subject": "John Doe"},
        ],
    },
    {
        "client_name": "Jane Smith",
        "folder": "Jane_Smith",
        "checklist": [
            {"doc_type": "K-1", "expected_subject": "Jane Smith"},
            {"doc_type": "1099-NEC", "expected_subject": "Jane Smith"},
        ],
    },
    {
        "client_name": "Sam Whitfield",
        "folder": "Sam_Whitfield",
        "checklist": [
            {"doc_type": "W-2", "expected_subject": "Sam Whitfield"},
        ],
    },
    {
        "client_name": "Rachel Green",
        "folder": "Rachel_Green",
        "checklist": [
            {"doc_type": "W-2", "expected_subject": "Rachel Green"},
        ],
    },
]


def client_folder_path(folder: str) -> Path:
    return CLIENTS_DIR / folder
