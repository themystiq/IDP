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

MAX_UPLOAD_SIZE_MB = 10
MAX_UPLOAD_SIZE_BYTES = MAX_UPLOAD_SIZE_MB * 1024 * 1024

PROCESSING_TIMEOUT_SECONDS = 30

ALLOWED_EXTENSIONS = ["pdf", "png", "jpg", "jpeg"]
