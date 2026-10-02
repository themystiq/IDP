"""Best-effort real email sending for Document Chaser's "Approve & Send" (see
src/ui/chaser_panel.py). Generic SMTP via the standard library (`smtplib`/`ssl`/`email`) —
not tied to any one provider, so switching from the demo's Google Workspace account to a
production client's own mail server is purely a config change (SMTP_HOST/PORT/USERNAME/
PASSWORD/FROM_EMAIL in .env — see config.py), never a code change.

Same best-effort, non-raising contract as slack_notifier.py: a missing config, auth failure,
or network error surfaces as a quiet return value for the caller to show in the UI, never an
exception — sending one client's email can't break another's.
"""
import smtplib
import ssl
from email.message import EmailMessage

from src import config


def email_enabled() -> bool:
    return bool(
        config.SMTP_HOST
        and config.SMTP_USERNAME
        and config.SMTP_PASSWORD
        and config.SMTP_FROM_EMAIL
    )


def send_email(to_address: str, subject: str, body: str) -> tuple[bool, str]:
    """Send one plain-text email. Returns (sent, error_message) — never raises."""
    if not email_enabled():
        return False, (
            "Email sending not configured (set SMTP_HOST/SMTP_USERNAME/SMTP_PASSWORD/"
            "SMTP_FROM_EMAIL in .env)."
        )

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = config.SMTP_FROM_EMAIL
    message["To"] = to_address
    message.set_content(body)

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT) as server:
            server.starttls(context=context)
            server.login(config.SMTP_USERNAME, config.SMTP_PASSWORD)
            server.send_message(message)
        return True, ""
    except Exception as e:
        return False, str(e)
