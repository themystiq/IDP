"""Sidebar: branding, engine status, and compliance notice."""
import streamlit as st

from src import config
from src.sample_documents import build_sample, get_sample_catalog


def render_sidebar() -> None:
    with st.sidebar:
        st.markdown("## 🏛️ Mystiq Labs")
        st.caption("Intelligent Document Processing & GL Reconciliation")
        st.divider()

        if config.ANTHROPIC_API_KEY:
            st.success("Engine: Active", icon="🟢")
        else:
            st.error("Engine: Inactive — ANTHROPIC_API_KEY missing", icon="🔴")

        st.divider()
        st.markdown(
            '<div class="idp-privacy-card">'
            '<div class="idp-privacy-title">🔒 Data Privacy</div>'
            '<div class="idp-privacy-subtitle">Privacy-first processing</div>'
            '<div class="idp-privacy-desc">Processed <strong>transiently in memory</strong> — '
            "no documents, TINs/EINs, or dollar amounts are <strong>ever persisted</strong> "
            "or sent anywhere. Document Chaser may post a client's name and outstanding "
            "items to Slack or, once approved, by email.</div>"
            "</div>",
            unsafe_allow_html=True,
        )

        st.divider()
        with st.expander("🧪 Load Sample Document"):
            catalog = get_sample_catalog()
            doc_type = st.selectbox("Document type", list(catalog.keys()), key="sample_doc_type")
            label = st.selectbox("Sample", catalog[doc_type], key="sample_label")
            if st.button("Load Sample", use_container_width=True):
                st.session_state["sample_bytes"] = build_sample(doc_type, label)
                st.session_state["sample_name"] = f"{label}.pdf"
                st.session_state["loaded_sample_label"] = label
