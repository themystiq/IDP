"""Left panel: multi-file uploader, size guardrail, document previews, and the extract action.

Document type is no longer chosen here — the vision model detects it from each image itself
(see src/extraction.py's extract_and_classify)."""
import streamlit as st

from src import config
from src.document_processor import image_to_base64_png, render_upload_to_images
from src.exceptions import IDPBaseError


def render_upload_panel():
    st.subheader("📄 Document Upload")

    uploaded_files = st.file_uploader(
        "Upload one or more 1099-NEC · 1099-MISC · W-2 · Schedule K-1 files (PDF, PNG, or JPG)",
        type=config.ALLOWED_EXTENSIONS,
        accept_multiple_files=True,
        help=(
            f"Maximum file size per file: {config.MAX_UPLOAD_SIZE_MB}MB. Bank statements, "
            "credit card statements, payroll summaries, EIN letters, and balance sheets are "
            "also recognized, but shown as informational only — no reconciliation ledger "
            "exists for them."
        ),
    )

    documents = []  # each: {"name": str, "images": list[PIL.Image], "base64_images": list[str]}

    if uploaded_files:
        st.session_state.pop("sample_bytes", None)  # an explicit upload takes precedence
        for uploaded_file in uploaded_files:
            if uploaded_file.size > config.MAX_UPLOAD_SIZE_BYTES:
                st.error(
                    f"'{uploaded_file.name}' exceeds the {config.MAX_UPLOAD_SIZE_MB}MB limit "
                    f"({uploaded_file.size / (1024 * 1024):.1f}MB) and was skipped."
                )
                continue
            try:
                images = render_upload_to_images(uploaded_file.getvalue(), uploaded_file.name)
                base64_images = [image_to_base64_png(img) for img in images]
                documents.append(
                    {"name": uploaded_file.name, "images": images, "base64_images": base64_images}
                )
            except IDPBaseError as e:
                st.error(f"Could not process '{uploaded_file.name}': {e}")
            except Exception as e:
                st.error(f"Unexpected error processing '{uploaded_file.name}': {e}")
    elif st.session_state.get("sample_bytes"):
        active_bytes = st.session_state["sample_bytes"]
        active_name = st.session_state["sample_name"]
        st.caption(f"Using loaded sample: **{st.session_state.get('loaded_sample_label')}**")
        try:
            images = render_upload_to_images(active_bytes, active_name)
            base64_images = [image_to_base64_png(img) for img in images]
            documents.append({"name": active_name, "images": images, "base64_images": base64_images})
        except IDPBaseError as e:
            st.error(f"Could not process sample document: {e}")
        except Exception as e:
            st.error(f"Unexpected error while processing sample document: {e}")

    # Placed directly below the drop zone, above the file list — the primary next action
    # stays reachable without scrolling past the list as more documents are uploaded.
    extract_clicked = st.button(
        "🔍 Extract & Audit Document(s)",
        type="primary",
        use_container_width=True,
        disabled=not bool(documents),
    )

    if documents:
        # Only badge a document type once it's a real, confirmed result — matched by
        # filename against the last extraction run — never a guess from the filename itself.
        batch_results = st.session_state.get("batch_results") or []
        confirmed_types = {
            r["doc_name"]: r["doc_type"] for r in batch_results if not r["error"] and r["doc_type"]
        }

        # Raw <p>/<strong> (not "**bold**" markdown) so the extra margin-bottom below can be
        # scoped to this exact line via a CSS class — gives the group of document cards a
        # bit more separation from the summary line above it without touching every gap.
        st.markdown(
            f'<p class="idp-group-heading"><strong>{len(documents)} document(s) ready</strong></p>',
            unsafe_allow_html=True,
        )
        for doc in documents:
            doc_type = confirmed_types.get(doc["name"])
            label = f"📄 [{doc_type}] {doc['name']}" if doc_type else f"📄 {doc['name']}"
            with st.expander(label, expanded=len(documents) == 1):
                st.image(
                    doc["images"][0],
                    use_container_width=True,
                    caption=f"Page 1 of {len(doc['images'])}",
                )
                if len(doc["images"]) > 1:
                    st.caption(f"{len(doc['images']) - 1} additional page(s) not shown in preview.")

    return extract_clicked, documents
