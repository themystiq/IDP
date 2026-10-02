"""Centralized configuration. All credentials load from environment variables only."""
import os

from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
# LiteLLM routes by provider prefix — "anthropic/" tells it to use the Anthropic SDK path.
# See: https://docs.litellm.ai/docs/providers/anthropic
# claude-3-5-sonnet-20241022 has been retired by Anthropic; claude-sonnet-5 is the current
# flagship Sonnet vision model. Override via CLAUDE_MODEL if your account should use another.
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "anthropic/claude-sonnet-5")

# Optional: per-document audit-outcome notifications (see src/slack_notifier.py). Both must
# be set for notifications to fire; if either is blank, slack_notifier.slack_enabled()
# returns False and the app behaves exactly as it did before Slack was added. SLACK_CHANNEL
# is a channel ID (e.g. "C0123456789") or name (e.g. "#gl-recon-alerts") — the bot must also
# be invited to that channel, or Slack returns a "not_in_channel" error.
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")
SLACK_CHANNEL = os.getenv("SLACK_CHANNEL", "")

# Optional: real email sending for Document Chaser's "Approve & Send" (see
# src/email_sender.py). Generic SMTP, not tied to any one provider — the demo uses Google
# Workspace (smtp.gmail.com:587 + an App Password), production would point this at the
# client's own mail server instead. All five must be set or email_sender.email_enabled()
# returns False and only Slack posting (the existing behavior) happens.
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL", "")

# Temporary demo safety valve: every Document Chaser "Approve & Send" goes to this address
# instead of a real client, since the demo client roster (chaser_data.py) has no real email
# addresses. Remove/generalize once clients have real addresses to send to.
CHASER_EMAIL_OVERRIDE = os.getenv("CHASER_EMAIL_OVERRIDE", "ramya.rajaram@mystiqlabs.ai")

# Where the running app can be reached from a browser — used to build the "Edit" / "Approve
# & Send" link buttons on a Document Chaser Slack post (see slack_notifier.post_chaser_email).
# Defaults to local dev; set to a real deployed URL once this app is hosted somewhere.
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8501")

MAX_UPLOAD_SIZE_MB = 10
MAX_UPLOAD_SIZE_BYTES = MAX_UPLOAD_SIZE_MB * 1024 * 1024

PROCESSING_TIMEOUT_SECONDS = 30

ALLOWED_EXTENSIONS = ["pdf", "png", "jpg", "jpeg"]
