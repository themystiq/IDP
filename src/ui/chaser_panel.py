"""Document Chaser panel: per-client checklist status, drafted reminder emails posted to
Slack, and a review step (Edit / Approve & Send) before any real email goes out. See
document_chaser.py for the scanning/matching logic this panel only renders.
"""
import streamlit as st

from src import config
from src.chaser_data import CLIENT_CHECKLISTS
from src.document_chaser import run_chaser_for_client
from src.email_sender import email_enabled, send_email
from src.slack_notifier import post_chaser_email, slack_enabled

_STATUS_ICON = {"satisfied": "✅", "missing": "❌", "mismatched": "⚠️"}


def _state_keys(folder: str) -> dict:
    return {
        "subject": f"chaser_subject_{folder}",
        "body": f"chaser_body_{folder}",
        "editing": f"chaser_editing_{folder}",
        "sent": f"chaser_sent_{folder}",
        "send_error": f"chaser_send_error_{folder}",
        "expanded": f"chaser_expanded_{folder}",
    }


def _run_batch() -> list[dict]:
    """Run the chaser for every client, posting one Slack message per client with
    outstanding items immediately after that client is scanned — same per-item-as-you-go
    pattern as the IDP workflow's Slack notifications, not batched at the end.

    Also (re)seeds each client's editable subject/body + edit/sent state for a fresh draft —
    a new scan can change what's actually outstanding, so any prior in-progress edit or
    "sent" state is intentionally reset here rather than carried over."""
    results = []
    for client in CLIENT_CHECKLISTS:
        result = run_chaser_for_client(client)
        keys = _state_keys(client["folder"])

        if result["email"]:
            st.session_state[keys["subject"]] = result["email"]["subject"]
            st.session_state[keys["body"]] = result["email"]["body"]
            st.session_state[keys["editing"]] = False
            st.session_state[keys["sent"]] = False
            st.session_state[keys["send_error"]] = None
            # Auto-open cards that need action right after a fresh scan, rather than
            # requiring the user to click open each one themselves.
            st.session_state[keys["expanded"]] = True

            if slack_enabled():
                sent, err = post_chaser_email(
                    result["client_name"], client["folder"],
                    result["email"]["subject"], result["email"]["body"],
                )
                result["slack_sent"] = sent
                result["slack_error"] = err
            else:
                result["slack_sent"] = False
                result["slack_error"] = None
        else:
            result["slack_sent"] = False
            result["slack_error"] = None
            # Nothing outstanding (or nothing to show yet) — collapse back down even if a
            # prior run had this client flagged open.
            st.session_state[keys["expanded"]] = False

        results.append(result)
    return results


def render_chaser_panel() -> None:
    # Landing here via a Slack "Edit"/"Approve & Send" link button (see
    # slack_notifier.post_chaser_email) carries ?client=<folder> — force that one card open
    # so the user doesn't have to hunt for it. Streamlit's st.tabs() has no way to select the
    # active tab programmatically, so the user still has to click the "Document Chaser" tab
    # once themselves; this just saves the second step of finding the right card.
    requested_client = st.query_params.get("client")
    if requested_client in {c["folder"] for c in CLIENT_CHECKLISTS}:
        st.session_state[f"chaser_expanded_{requested_client}"] = True

    st.subheader("📋 Document Chaser")
    st.caption(
        "Scans each client's folder, extracts and classifies every document found, and "
        "flags anything missing or mismatched against their checklist."
    )

    if not slack_enabled():
        st.caption(
            "ℹ️ Slack isn't configured (set SLACK_BOT_TOKEN/SLACK_CHANNEL in .env) — "
            "reminder emails will still be drafted below, just not posted."
        )
    if not email_enabled():
        st.caption(
            "ℹ️ Real email sending isn't configured (set SMTP_HOST/SMTP_USERNAME/"
            "SMTP_PASSWORD/SMTP_FROM_EMAIL in .env) — **Approve & Send** will show an error "
            "until it is."
        )
    else:
        st.caption(
            f"✉️ For this demo, every **Approve & Send** goes to "
            f"**{config.CHASER_EMAIL_OVERRIDE}** regardless of client — the demo roster has "
            "no real client addresses yet."
        )

    if st.button(
        "📨 Check Documents & Email Clients", type="primary", use_container_width=True
    ):
        with st.spinner("Scanning client folders and extracting documents..."):
            st.session_state["chaser_results"] = _run_batch()

    results = st.session_state.get("chaser_results")

    for client in CLIENT_CHECKLISTS:
        result = next(
            (r for r in (results or []) if r["client_name"] == client["client_name"]), None
        )
        keys = _state_keys(client["folder"])
        # Pinned to session state, not left at st.expander's default — a button click
        # inside this expander (Edit / Approve & Send) triggers a script rerun, and without
        # this, st.expander snaps back to collapsed on that rerun, hiding the very thing the
        # user just clicked to see. Same gotcha/fix as the Customer Reconciliation cards'
        # "Show Raw Extracted JSON" toggle in results_panel.py.
        with st.expander(
            f"👤 {client['client_name']}", expanded=st.session_state.get(keys["expanded"], False)
        ):
            if result is None:
                for item in client["checklist"]:
                    st.caption(f"◻️ {item['doc_type']} — not yet checked")
                continue

            for item in result["checklist_results"]:
                st.write(f"{_STATUS_ICON[item['status']]} **{item['doc_type']}** — {item['detail']}")

            if not result["email"]:
                st.success("All required documents received — no reminder needed.")
                continue

            is_sent = st.session_state.get(keys["sent"], False)
            is_editing = st.session_state.get(keys["editing"], False)

            st.markdown("**Drafted reminder email:**")

            edit_col, send_col = st.columns(2)
            if edit_col.button(
                "✏️ Edit", key=f"edit_btn_{client['folder']}",
                disabled=is_sent, use_container_width=True,
            ):
                st.session_state[keys["editing"]] = True
                st.session_state[keys["expanded"]] = True
                is_editing = True
            if send_col.button(
                "✅ Approve & Send", key=f"send_btn_{client['folder']}", type="primary",
                disabled=is_sent, use_container_width=True,
            ):
                sent, err = send_email(
                    config.CHASER_EMAIL_OVERRIDE,
                    st.session_state[keys["subject"]],
                    st.session_state[keys["body"]],
                )
                st.session_state[keys["sent"]] = sent
                st.session_state[keys["send_error"]] = err
                st.session_state[keys["editing"]] = False
                st.session_state[keys["expanded"]] = True
                is_sent, is_editing = sent, False

            field_disabled = is_sent or not is_editing
            st.text_input("Subject", key=keys["subject"], disabled=field_disabled)
            st.text_area("Body", key=keys["body"], height=200, disabled=field_disabled)

            if is_sent:
                st.success(f"Sent to {config.CHASER_EMAIL_OVERRIDE}", icon="✅")
            elif st.session_state.get(keys["send_error"]):
                st.error(f"Send failed: {st.session_state[keys['send_error']]}", icon="🛑")

            if result["slack_sent"]:
                st.caption("✅ Draft also posted to Slack")
            elif result["slack_error"]:
                st.caption(f"⚠️ Slack post failed: {result['slack_error']}")
