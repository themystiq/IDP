"""Document Chaser: per-client checklist scanning, independent of the UI.

For each client (see chaser_data.CLIENT_CHECKLISTS), scans their folder, runs every file
through the exact same extraction pipeline the main IDP workflow uses
(document_processor.render_upload_to_images / image_to_base64_png, then
extraction.extract_and_classify), and matches what it finds against the checklist — catching
not just missing documents but the wrong document for this client (right doc_type, wrong
identity).
"""
from src import config
from src.chaser_data import client_folder_path
from src.document_processor import image_to_base64_png, render_upload_to_images
from src.exceptions import ExtractionError, ExtractionTimeoutError
from src.extraction import extract_and_classify

# Which extracted field identifies "whose document this is" per reconciled doc type. This
# intentionally duplicates the "subject" lambdas in results_panel.RECONCILERS rather than
# importing from a UI module into this business-logic one — a 4-entry map is cheaper than
# crossing that layering boundary.
_SUBJECT_ATTR = {
    "1099-NEC": "recipient_name",
    "1099-MISC": "recipient_name",
    "W-2": "employee_name",
    "K-1": "partner_name",
}


def scan_client_folder(client: dict) -> list[dict]:
    """Extract + classify every allowed file in one client's folder. Never raises — a
    per-file extraction failure is captured in that entry's "error" key, same resilience
    pattern as _process_document in results_panel.py, so one bad file can't abort the scan."""
    folder = client_folder_path(client["folder"])
    if not folder.exists():
        return []

    files = sorted(
        f for f in folder.iterdir() if f.suffix.lstrip(".").lower() in config.ALLOWED_EXTENSIONS
    )

    extracted_docs = []
    for f in files:
        entry = {"file_name": f.name, "doc_type": None, "extracted": None, "error": None}
        try:
            images = render_upload_to_images(f.read_bytes(), f.name)
            base64_image = image_to_base64_png(images[0])
            extracted, doc_type = extract_and_classify(base64_image)
            entry["doc_type"] = doc_type
            entry["extracted"] = extracted
        except (ExtractionError, ExtractionTimeoutError) as e:
            entry["error"] = str(e)
        except Exception as e:
            entry["error"] = f"Unexpected error: {e}"
        extracted_docs.append(entry)
    return extracted_docs


def _match_checklist(checklist: list[dict], extracted_docs: list[dict]) -> list[dict]:
    results = []
    for item in checklist:
        doc_type, expected = item["doc_type"], item["expected_subject"]
        candidates = [d for d in extracted_docs if d["doc_type"] == doc_type]

        if not candidates:
            results.append(
                {**item, "status": "missing", "detail": f"No {doc_type} received."}
            )
            continue

        subject_attr = _SUBJECT_ATTR.get(doc_type)
        match = next(
            (
                d for d in candidates
                if (getattr(d["extracted"], subject_attr, None) or "").strip().lower()
                == expected.strip().lower()
            ),
            None,
        )
        if match:
            results.append(
                {**item, "status": "satisfied", "detail": f"{doc_type} received and verified."}
            )
        else:
            found_name = getattr(candidates[0]["extracted"], subject_attr, None) or "unknown"
            results.append(
                {
                    **item,
                    "status": "mismatched",
                    "detail": f"Found {doc_type} for '{found_name}', expected '{expected}'.",
                }
            )
    return results


def compose_reminder_email(client_name: str, outstanding_items: list[dict]) -> dict:
    bullet_lines = [f"- {item['doc_type']}: {item['detail']}" for item in outstanding_items]
    subject = f"Action Required: Outstanding Tax Documents for {client_name}"
    body = (
        f"Hi {client_name},\n\n"
        "To complete your tax filing, we still need the following document(s):\n\n"
        + "\n".join(bullet_lines)
        + "\n\nPlease send these at your earliest convenience.\n\nThank you,\nMystiq Labs"
    )
    return {"subject": subject, "body": body}


def run_chaser_for_client(client: dict) -> dict:
    extracted_docs = scan_client_folder(client)
    checklist_results = _match_checklist(client["checklist"], extracted_docs)
    outstanding = [r for r in checklist_results if r["status"] != "satisfied"]
    email = compose_reminder_email(client["client_name"], outstanding) if outstanding else None
    return {
        "client_name": client["client_name"],
        "checklist_results": checklist_results,
        "email": email,
    }
