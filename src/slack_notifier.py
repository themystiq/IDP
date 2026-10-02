"""Best-effort Slack notifications. Two distinct message types, two distinct privacy
boundaries — don't conflate them:

- `notify_document_outcome` (IDP workflow): fires once per document, right after that
  document finishes extraction + reconciliation (see results_panel.py's
  render_results_panel) — not batched into one end-of-run summary message. Deliberately
  minimal payload: document name, detected type, and the audit status label only (plus the
  error text itself when extraction failed, since that's already shown as plain `st.error`
  text in the UI and carries no PII). Never includes TINs/SSNs/EINs, recipient or employee
  names, or dollar amounts — see CLAUDE.md's "Nothing is persisted" security note.
- `post_chaser_email` (Document Chaser): posts a drafted client reminder email, which by
  its nature names the client and the document types they're missing — a deliberately wider
  boundary than the IDP notification above, scoped to this one feature. Still never includes
  a TIN/SSN/EIN or a dollar amount. See CLAUDE.md's Document Chaser section.

Both are optional and never block their pipeline: a missing token/channel, a network error,
or the bot not being invited to the target channel all surface as a quiet return value for
the caller to optionally surface in the UI, never an exception.
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


def _post(text: str) -> tuple[bool, str]:
    """Shared best-effort post: never raises, returns (sent, error_message)."""
    if not slack_enabled():
        return False, "Slack not configured (set SLACK_BOT_TOKEN and SLACK_CHANNEL in .env)."
    try:
        WebClient(token=config.SLACK_BOT_TOKEN).chat_postMessage(channel=config.SLACK_CHANNEL, text=text)
        return True, ""
    except SlackApiError as e:
        return False, e.response.get("error", str(e))
    except Exception as e:
        return False, str(e)


def notify_document_outcome(doc_name: str, doc_type: str, status_key: str, detail: str = "") -> tuple[bool, str]:
    """Post one Slack message for a processed document's audit outcome."""
    emoji, label = _STATUS_DISPLAY.get(status_key, ("❔", status_key))
    type_part = f" [{doc_type}]" if doc_type else ""
    text = f"{emoji} *{doc_name}*{type_part} — {label}"
    if detail:
        text += f": {detail}"
    return _post(text)


def post_chaser_email(client_name: str, subject: str, body: str) -> tuple[bool, str]:
    """Post a drafted Document Chaser reminder email as one Slack message — a fenced code
    block for the body so line breaks render readably."""
    text = f"📧 *Document Chaser — {client_name}*\n*Subject:* {subject}\n```{body}```"
    return _post(text)
