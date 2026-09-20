"""Mystiq Labs — Intelligent Document Processing & GL Reconciliation demo.

Thin Streamlit entry point: wires the sidebar, upload panel, and results panel together.
All business logic lives in src/ (see CLAUDE.md for architecture and run instructions).
"""
import streamlit as st

from src.ui.results_panel import render_results_panel
from src.ui.sidebar import render_sidebar
from src.ui.theme import inject_custom_theme
from src.ui.upload_panel import render_upload_panel

st.set_page_config(
    page_title="Mystiq Labs | IDP & GL Reconciliation",
    page_icon="🏛️",
    layout="wide",
)

inject_custom_theme()

render_sidebar()

st.title("Intelligent Document Processing & GL Reconciliation")
st.caption(
    "CPA-grade extraction and audit engine for IRS Form 1099-NEC · 1099-MISC · W-2 · "
    "Schedule K-1"
)

left, right = st.columns([1, 1.4], gap="large")

with left:
    extract_clicked, documents = render_upload_panel()

with right:
    render_results_panel(extract_clicked, documents)
