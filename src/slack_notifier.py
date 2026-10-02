"""Best-effort Slack notification for each document's audit outcome.

Fires once per document, right after that document finishes extraction + reconciliation (see
results_panel.py's render_results_panel) — not batched into one end-of-run summary message.

Deliberately minimal payload: document name, detected type, and the audit status label only
(plus the error text itself when extraction failed, since that's already shown as plain
`st.error` text in the UI and carries no PII). Never includes TINs/SSNs/EINs, recipient or
employee names, or dollar amounts — see CLAUDE.md's "Nothing is persisted" security note for
why this boundary matters.

Slack is optional and never blocks the pipeline: a missing token/channel, a network error, or
the bot not being invited to the target channel all surface as a quiet return value for the
caller to optionally surface in the UI, never an exception.
"""
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from src import config

_STATUS_DISPLAY = {
    "GREEN": ("🟢", "Clean Match"),
    "AMBER": ("🟡", "Compliance Notice"),
    "RED": ("🔴", "Variance"),
    "INFO": ("ℹ️", "Informational — Not Reconciled"),
    "ERROR": ("⚠️", "Failed to Process"),
}


def slack_enabled() -> bool:
    return bool(config.SLACK_BOT_TOKEN and config.SLACK_CHANNEL)


def notify_document_outcome(doc_name: str, doc_type: str, status_key: str, detail: str = "") -> tuple[bool, str]:
    """Post one Slack message for a processed document. Returns (sent, error_message) —
    never raises, so a Slack hiccup can't interrupt batch processing."""
    if not slack_enabled():
        return False, "Slack not configured (set SLACK_BOT_TOKEN and SLACK_CHANNEL in .env)."

    emoji, label = _STATUS_DISPLAY.get(status_key, ("❔", status_key))
    type_part = f" [{doc_type}]" if doc_type else ""
    text = f"{emoji} *{doc_name}*{type_part} — {label}"
    if detail:
        text += f": {detail}"

    try:
        WebClient(token=config.SLACK_BOT_TOKEN).chat_postMessage(channel=config.SLACK_CHANNEL, text=text)
        return True, ""
    except SlackApiError as e:
        return False, e.response.get("error", str(e))
    except Exception as e:
        return False, str(e)
