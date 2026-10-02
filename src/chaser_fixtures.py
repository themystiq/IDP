"""Generates the Document Chaser demo fixtures under documents/clients/ — one folder per
CLIENT_CHECKLISTS entry, populated via sample_documents.build_sample() using the exact same
synthetic client data as the main IDP demo (see chaser_data.py for why each file was chosen,
including Sam Whitfield's deliberately-wrong W-2).

Run via `python -m src.chaser_fixtures` to (re)write documents/clients/*/*.pdf — mirrors
sample_documents.py's own __main__ regeneration script. These are synthetic demo fixtures
built from public IRS templates (no real PII), so — like documents/*.pdf — they're checked
into git rather than gitignored.
"""
from src.chaser_data import CLIENT_CHECKLISTS, client_folder_path
from src.sample_documents import build_sample

# doc_type -> label, per client folder. Sam Whitfield intentionally gets Jordan Ellis's W-2
# (a real tax form, for the wrong client) to demo the chaser catching a wrong document, not
# just a missing one.
_FOLDER_CONTENTS = {
    "John_Doe": [
        ("1099-NEC", "Sample K - Clean Match (John Doe consulting)"),
        ("W-2", "Sample L - Clean Match (John Doe employment)"),
    ],
    "Jane_Smith": [
        ("K-1", "Sample N - Variance Flag (Jane Smith)"),
    ],
    "Sam_Whitfield": [
        ("W-2", "Sample D - Clean Match (Jordan Ellis)"),  # deliberately wrong person
    ],
    "Rachel_Green": [],  # deliberately empty — nothing received
}


def build_chaser_fixtures() -> None:
    for client in CLIENT_CHECKLISTS:
        folder = client_folder_path(client["folder"])
        folder.mkdir(parents=True, exist_ok=True)
        contents = _FOLDER_CONTENTS[client["folder"]]
        for doc_type, label in contents:
            # Named by checklist slot (e.g. "W-2.pdf"), not by true contents — a filename
            # gives no hint that Sam Whitfield's W-2 is actually Jordan Ellis's; only
            # extraction reveals that.
            out_path = folder / f"{doc_type}.pdf"
            out_path.write_bytes(build_sample(doc_type, label))
            print(f"wrote {out_path.relative_to(folder.parents[2])}")
        if not contents:
            # git can't track an empty directory.
            (folder / ".gitkeep").touch()
            print(f"created empty {folder.relative_to(folder.parents[2])}/ (.gitkeep)")


if __name__ == "__main__":
    build_chaser_fixtures()
