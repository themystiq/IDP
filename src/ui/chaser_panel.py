"""Document Chaser panel: per-client checklist status + drafted reminder emails posted to
Slack. See document_chaser.py for the scanning/matching logic this panel only renders."""
import streamlit as st

from src.chaser_data import CLIENT_CHECKLISTS
from src.document_chaser import run_chaser_for_client
from src.slack_notifier import post_chaser_email, slack_enabled

_STATUS_ICON = {"satisfied": "✅", "missing": "❌", "mismatched": "⚠️"}


def _run_batch() -> list[dict]:
    """Run the chaser for every client, posting one Slack message per client with
    outstanding items immediately after that client is scanned — same per-item-as-you-go
    pattern as the IDP workflow's Slack notifications, not batched at the end."""
    results = []
    for client in CLIENT_CHECKLISTS:
        result = run_chaser_for_client(client)
        if result["email"] and slack_enabled():
            sent, err = post_chaser_email(
                result["client_name"], result["email"]["subject"], result["email"]["body"]
            )
            result["slack_sent"] = sent
            result["slack_error"] = err
        else:
            result["slack_sent"] = False
            result["slack_error"] = None
        results.append(result)
    return results


def render_chaser_panel() -> None:
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
        with st.expander(f"👤 {client['client_name']}"):
            if result is None:
                for item in client["checklist"]:
                    st.caption(f"◻️ {item['doc_type']} — not yet checked")
                continue

            for item in result["checklist_results"]:
                st.write(f"{_STATUS_ICON[item['status']]} **{item['doc_type']}** — {item['detail']}")

            if result["email"]:
                st.markdown("**Drafted reminder email:**")
                st.text_area(
                    "Email draft",
                    f"Subject: {result['email']['subject']}\n\n{result['email']['body']}",
                    height=200,
                    key=f"chaser_email_{client['folder']}",
                    label_visibility="collapsed",
                )
                if result["slack_sent"]:
                    st.success("Posted to Slack", icon="✅")
                elif result["slack_error"]:
                    st.warning(f"Slack post failed: {result['slack_error']}", icon="⚠️")
            else:
                st.success("All required documents received — no reminder needed.")
