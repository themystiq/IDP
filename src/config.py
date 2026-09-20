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

MAX_UPLOAD_SIZE_MB = 10
MAX_UPLOAD_SIZE_BYTES = MAX_UPLOAD_SIZE_MB * 1024 * 1024

PROCESSING_TIMEOUT_SECONDS = 30

ALLOWED_EXTENSIONS = ["pdf", "png", "jpg", "jpeg"]
