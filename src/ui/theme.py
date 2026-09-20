"""Custom CSS for the dark, executive-style theme. Injected once from app.py.

This is a deliberate single dark theme, not a light/dark toggle — the colors below are fixed
hex values, not tied to Streamlit's own runtime theme switch. .streamlit/config.toml sets the
same palette as the app's *default* theme so the two agree out of the box; if a user manually
flips Streamlit's built-in theme picker (top-right ⋮ menu → Settings) to "light", this CSS
will still force dark backgrounds and the two will visually clash — acceptable here since the
goal is one consistent look, not a toggle.
"""
import streamlit as st

from src import config

_CSS = """
<style>
:root {
    --idp-bg-primary: #0E1117;
    --idp-bg-secondary: #1E232F;
    --idp-text-primary: #FFFFFF;
    --idp-text-secondary: #A0AEC0;
    --idp-accent-success: #10B981;
    --idp-accent-danger: #EF4444;
    --idp-accent-warning: #F59E0B;
    --idp-accent-neutral: #64748B;
    --idp-accent-info: #3B82F6;
}

/* ---- Base layout ---- */
.stApp {
    background-color: var(--idp-bg-primary);
}
.block-container {
    padding-top: 1.75rem;
    padding-bottom: 2rem;
    padding-left: 3rem;
    padding-right: 3rem;
}
[data-testid="stSidebar"] {
    background-color: var(--idp-bg-secondary);
    border-right: 1px solid rgba(255, 255, 255, 0.06);
}
/* Left (Upload) / Right (Extraction & Audit) panel gap. Streamlit's own gap="large" on
   st.columns() computes to 64px (4rem) — more than intended — so this pins the actual value
   to a precise 2rem instead of layering on top of it. !important is needed because Streamlit
   sets its own gap via an emotion-generated class on this same element. */
[data-testid="stHorizontalBlock"] {
    gap: 2rem !important;
}
hr {
    /* Dividers mark major section boundaries (Batch Summary -> Customer Reconciliation ->
       Export, sidebar sections) — a bit more room than the ambient element gap so those
       transitions read as bigger breaks, without touching spacing *within* a section. */
    margin: 1.1rem 0;
    opacity: 0.15;
}

/* ---- Selective vertical breathing room between major content groups ----
   Deliberately NOT a blanket increase to every element's gap (that would make in-group
   content feel just as loose as between-group transitions). Each rule below targets one
   specific, named transition via :has() on Streamlit's generic stElementContainer wrapper
   (every element shares that one class, so :has() + a stable inner data-testid/class is the
   only reliable way to target a specific transition without editing every call site). */
div[data-testid="stElementContainer"]:has([data-testid="stFileUploaderDropzone"]) {
    margin-bottom: 0.9rem; /* upload dropzone -> the "N document(s) ready" / file list below it */
}
div[data-testid="stElementContainer"]:has([data-testid="stExpander"]) {
    margin-bottom: 0.5rem; /* modest — keeps stacked document/customer cards themselves compact */
}
div[data-testid="stElementContainer"]:has(> div.stButton),
div[data-testid="stElementContainer"]:has(> div.stDownloadButton) {
    margin-top: 0.6rem; /* extra room before an action button following a group of content */
}
.idp-group-heading {
    margin: 0 0 0.9rem 0; /* the "N document(s) ready" line -> the document cards beneath it */
}

/* ---- Sidebar privacy card (compact, replaces a tall st.info) ---- */
.idp-privacy-card {
    background-color: var(--idp-bg-secondary); /* #1E232F */
    border: 1px solid #2D3748;
    border-radius: 8px;
    padding: 0.6rem 0.75rem;
}
.idp-privacy-title {
    font-size: 0.825rem; /* 13px */
    font-weight: 700;
    color: var(--idp-text-primary); /* #FFFFFF */
    margin-bottom: 0.2rem;
}
.idp-privacy-subtitle {
    font-size: 0.68rem;
    font-weight: 500;
    font-style: italic;
    color: var(--idp-text-secondary);
    margin-bottom: 0.3rem;
}
.idp-privacy-desc {
    font-size: 0.825rem; /* 13px — compact enough to avoid sidebar overflow */
    font-weight: 400;
    line-height: 1.35;
    color: #E2E8F0;
}

/* ---- Typography ----
   Weight hierarchy: main page title (h1) keeps Streamlit's native 700 — untouched. Section
   headings (h3 — "Document Upload", "Extracted Data & Audit", "Customer Reconciliation",
   "Export Results", "Quick Sample Document Loader") step down from the native 600, which
   reads heavier than intended at these large sizes. Card/customer titles (st.expander
   summaries — file list entries, Customer Reconciliation cards) step UP from the native 400,
   which left them visually indistinguishable from plain body text. h2 (the sidebar "Mystiq
   Labs" wordmark) is deliberately left alone — it's brand identity, not a section heading. */
h1, h2, h3, h4, h5, h6 {
    color: var(--idp-text-primary) !important;
    letter-spacing: -0.01em;
}
h3 {
    font-weight: 550 !important;
    margin-bottom: 0.85rem; /* section heading -> its content: a bit more separation */
}
[data-testid="stExpander"] summary {
    font-weight: 500 !important;
}
[data-testid="stCaptionContainer"], .stCaption, small {
    color: var(--idp-text-secondary) !important;
}

/* ---- Batch Summary KPI cards (custom HTML — see results_panel.py's _kpi_card) ----
   The global stHorizontalBlock gap above (2rem, meant for the outer Left/Right panel split)
   also applies to this inner 3-column row since Streamlit gives every horizontal block the
   same data-testid. At the right panel's typical width, 2rem gaps left no room for a 3rd
   321px-wide column, so Streamlit's own default flex-wrap: wrap pushed it onto its own line.
   Scoped via :has() to just this row so nothing else's wrapping/gap behavior changes. */
[data-testid="stHorizontalBlock"]:has(.idp-kpi-card) {
    flex-wrap: nowrap !important;
}
.idp-kpi-card {
    background-color: var(--idp-bg-secondary);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 12px;
    padding: 1.1rem 1.25rem;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.25);
    min-height: 92px;
}
.idp-kpi-label-row {
    display: flex;
    align-items: center;
    gap: 0.45rem;
    margin-bottom: 0.35rem;
}
.idp-kpi-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    flex-shrink: 0;
    background-color: var(--idp-accent-neutral);
}
.idp-kpi-success .idp-kpi-dot {
    background-color: var(--idp-accent-success);
}
.idp-kpi-warning .idp-kpi-dot {
    background-color: var(--idp-accent-warning);
}
.idp-kpi-danger .idp-kpi-dot {
    background-color: var(--idp-accent-danger);
}
.idp-kpi-label {
    color: var(--idp-text-secondary);
    font-weight: 600;
    font-size: 0.7rem;
    letter-spacing: 0.06em;
    text-transform: uppercase;
}
.idp-kpi-value {
    color: var(--idp-text-primary);
    font-weight: 700;
    font-size: 1.85rem;
    line-height: 1.2;
}
.idp-kpi-value .idp-kpi-slash {
    color: var(--idp-text-secondary);
    font-weight: 400;
    font-size: 1.25rem;
    padding: 0 0.15rem;
}
.idp-kpi-desc {
    color: var(--idp-text-secondary);
    font-weight: 400;
    font-size: 0.78rem;
    margin-top: 0.2rem;
}

/* ---- Workflow pipeline indicator (a state readout, not a progress animation — see
   _render_workflow_indicator in results_panel.py). Nothing here transitions or animates;
   each stage's look is fixed per render based on the app's real state. ---- */
.idp-pipeline {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    row-gap: 0.35rem;
    margin: 0.5rem 0 1.15rem 0;
}
.idp-pipeline-stage {
    display: flex;
    align-items: center;
    gap: 0.35rem;
}
.idp-pipeline-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    flex-shrink: 0;
    background-color: transparent;
    border: 1.5px solid rgba(160, 174, 192, 0.3);
}
.idp-pipeline-label {
    font-size: 0.72rem;
    font-weight: 500;
    color: rgba(160, 174, 192, 0.45);
    letter-spacing: 0.01em;
    white-space: nowrap;
}
.idp-pipeline-line {
    width: 22px;
    height: 1px;
    background-color: rgba(160, 174, 192, 0.2);
    margin: 0 0.55rem;
    flex-shrink: 0;
}
.idp-pipeline-line-done {
    background-color: rgba(16, 185, 129, 0.35);
}
.idp-pipeline-done .idp-pipeline-dot {
    background-color: var(--idp-accent-success);
    border-color: var(--idp-accent-success);
}
.idp-pipeline-done .idp-pipeline-label {
    color: var(--idp-text-secondary);
}
.idp-pipeline-amber .idp-pipeline-dot {
    background-color: var(--idp-accent-warning);
    border-color: var(--idp-accent-warning);
}
.idp-pipeline-amber .idp-pipeline-label {
    color: var(--idp-text-secondary);
}
.idp-pipeline-failed .idp-pipeline-dot {
    background-color: var(--idp-accent-danger);
    border-color: var(--idp-accent-danger);
}
.idp-pipeline-failed .idp-pipeline-label {
    color: var(--idp-text-secondary);
}
.idp-pipeline-next .idp-pipeline-dot {
    background-color: transparent;
    border-color: var(--idp-accent-info);
}
.idp-pipeline-next .idp-pipeline-label {
    color: rgba(160, 174, 192, 0.8);
}
.idp-pipeline-pending .idp-pipeline-dot {
    background-color: transparent;
    border-color: rgba(160, 174, 192, 0.3);
}

/* ---- Expanders ---- */
[data-testid="stExpander"] {
    background-color: var(--idp-bg-secondary);
    border: 1px solid rgba(255, 255, 255, 0.07);
    border-radius: 12px;
    box-shadow: 0 2px 10px rgba(0, 0, 0, 0.25);
    overflow: hidden;
    margin-bottom: 0.6rem;
}
[data-testid="stExpander"] summary {
    padding: 0.65rem 1rem;
    transition: background-color 0.15s ease;
}
[data-testid="stExpander"] summary:hover {
    background-color: rgba(255, 255, 255, 0.04);
}

/* ---- Buttons ---- */
.stButton > button, .stDownloadButton > button, [data-testid="stBaseButton-secondary"] {
    border-radius: 10px;
    padding: 0.55rem 1.15rem;
    font-weight: 600;
    border: 1px solid rgba(255, 255, 255, 0.09);
    transition: transform 0.15s ease, box-shadow 0.15s ease, border-color 0.15s ease;
}
.stButton > button:hover,
.stDownloadButton > button:hover,
[data-testid="stBaseButton-secondary"]:hover {
    transform: translateY(-1px);
    box-shadow: 0 4px 14px rgba(16, 185, 129, 0.25);
    border-color: var(--idp-accent-success);
}
.stButton > button[kind="primary"], .stDownloadButton > button[kind="primary"] {
    background-color: var(--idp-accent-success) !important;
    border-color: var(--idp-accent-success) !important;
    color: #06120D !important;
}
.stButton > button[kind="primary"]:hover,
.stDownloadButton > button[kind="primary"]:hover {
    box-shadow: 0 4px 18px rgba(16, 185, 129, 0.4);
}

/* ---- File uploader ----
   The dropzone's copy ("Drag and drop files here" / the format+size line) is rendered
   natively by Streamlit with no Python-level way to change the wording, so the two text
   nodes are visually replaced via font-size:0 + a ::after with the desired copy (the size
   line's content is generated dynamically in inject_custom_theme() from src/config.py, not
   hardcoded here, so it can't drift out of sync with the real upload limits). */
[data-testid="stFileUploaderDropzone"] {
    background-color: var(--idp-bg-secondary);
    border: 1.5px dashed rgba(160, 174, 192, 0.3);
    border-radius: 12px;
    padding: 0.25rem 0.5rem;
    transition: border-color 0.2s ease, background-color 0.2s ease;
}
[data-testid="stFileUploaderDropzone"]:hover {
    border-color: var(--idp-accent-success);
    background-color: rgba(16, 185, 129, 0.04);
}
[data-testid="stFileUploaderDropzoneInstructions"] svg {
    width: 20px;
    height: 20px;
    opacity: 0.4;
}
[data-testid="stFileUploaderDropzoneInstructions"] > div > span:first-child {
    font-size: 0;
}
[data-testid="stFileUploaderDropzoneInstructions"] > div > span:first-child::after {
    content: "Drop tax documents here";
    font-size: 0.92rem;
    font-weight: 600;
    color: var(--idp-text-primary);
    letter-spacing: -0.01em;
}
[data-testid="stFileUploaderDropzoneInstructions"] > div > span:last-child {
    font-size: 0;
}
[data-testid="stFileUploaderDropzoneInstructions"] > div > span:last-child::after {
    font-size: 0.72rem;
    font-weight: 400;
    color: var(--idp-text-secondary);
    letter-spacing: 0.01em;
}

/* ---- Tables ---- */
[data-testid="stDataFrame"] {
    border-radius: 10px;
    overflow: hidden;
    border: 1px solid rgba(255, 255, 255, 0.07);
}

/* ---- Alerts: rounding + tighter spacing only. Streamlit's own dark-theme alert colors
   already read as success/warning/danger; we deliberately don't fight its internals here
   since there's no stable, version-safe selector for the exact success/error/warning hex. */
[data-testid="stAlert"] {
    border-radius: 10px;
    padding: 0.75rem 1rem;
}
</style>
"""


def _upload_hint_text() -> str:
    """Build the compact 'PDF · PNG · JPG · Max 10 MB' dropzone hint from the real upload
    config (src/config.py) rather than hardcoding it, so it can't drift out of sync if the
    allowed extensions or size limit ever change. jpg/jpeg collapse to one "JPG" label since
    they're the same format — display-only simplification, not a change to what's accepted."""
    labels = []
    for ext in config.ALLOWED_EXTENSIONS:
        label = "JPG" if ext.lower() in ("jpg", "jpeg") else ext.upper()
        if label not in labels:
            labels.append(label)
    return " · ".join(labels) + f" · Max {config.MAX_UPLOAD_SIZE_MB} MB"


def inject_custom_theme() -> None:
    # Built as a single line (no embedded newlines/indentation): st.markdown parses this as
    # Markdown first, and a multi-line string indented 4+ spaces (the natural result of
    # writing a triple-quoted string inside this function body) gets treated as a Markdown
    # code block and rendered as literal visible text instead of being parsed as HTML/CSS.
    hint_rule = (
        '<style>[data-testid="stFileUploaderDropzoneInstructions"] > div > '
        f'span:last-child::after {{ content: "{_upload_hint_text()}"; }}</style>'
    )
    st.markdown(_CSS + hint_rule, unsafe_allow_html=True)
