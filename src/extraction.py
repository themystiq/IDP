"""LiteLLM + Claude vision extraction: a single call classifies the document as
1099-NEC / 1099-MISC / W-2 / Schedule K-1 and extracts its fields in one shot, then the
result is validated against whichever Pydantic schema matches the detected type."""
import concurrent.futures
import json
import re

import litellm

from src import config
from src.exceptions import ExtractionError, ExtractionTimeoutError
from src.schemas import Form1099Misc, Form1099NEC, FormK1, FormW2

UNIFIED_EXTRACTION_PROMPT = """You are an expert CPA document-extraction system.

First, determine which of these four IRS form types this image is:
- "1099-NEC" (Nonemployee Compensation)
- "1099-MISC" (Miscellaneous Information)
- "W2" (Wage and Tax Statement)
- "K-1" (Schedule K-1, partner's/shareholder's share of income from a partnership)

Then extract only the fields that apply to that specific form type. Return ONLY a raw JSON
object (no markdown fences, no commentary) with exactly these keys:

- document_type (string: one of "1099-NEC", "1099-MISC", "W2", "K-1")
- payer_name (string or null — 1099-NEC/1099-MISC only)
- payer_tin (string or null, format like XX-XXXXXXX — 1099-NEC/1099-MISC only)
- recipient_name (string or null — 1099-NEC/1099-MISC only)
- recipient_tin (string or null, format like XXX-XX-XXXX or XX-XXXXXXX — 1099-NEC/1099-MISC only)
- nonemployee_compensation (number or null, 1099-NEC Box 1, no $ or commas)
- federal_tax_withheld (number or null, 1099-NEC Box 4, no $ or commas)
- rents (number or null, 1099-MISC Box 1, no $ or commas)
- other_income (number or null, 1099-MISC Box 3, no $ or commas)
- employer_name (string or null — W-2 only)
- employer_ein (string or null, format like XX-XXXXXXX — W-2 only)
- employee_name (string or null — W-2 only)
- employee_ssn (string or null, format like XXX-XX-XXXX — W-2 only)
- wages_tips_other_comp (number or null, W-2 Box 1, no $ or commas)
- federal_income_tax_withheld (number or null, W-2 Box 2, no $ or commas)
- partnership_name (string or null — K-1 only)
- partnership_ein (string or null, format like XX-XXXXXXX — K-1 only)
- partner_name (string or null — K-1 only)
- partner_tin (string or null, format like XXX-XX-XXXX or XX-XXXXXXX — K-1 only)
- ordinary_business_income (number or null, K-1 Box 1 ordinary business income (loss), no $ or
  commas; this may be negative if the K-1 reports a loss)
- net_rental_real_estate_income (number or null, K-1 Box 2, no $ or commas; may be negative)
- tax_year (string or null, 4-digit year)

Set every field that does not apply to the detected document_type, and any field that is
unreadable or not present on the document, to null rather than guessing. Return valid JSON
only."""

SCHEMA_BY_DOC_TYPE = {
    "1099-NEC": Form1099NEC,
    "1099-MISC": Form1099Misc,
    "W-2": FormW2,
    "K-1": FormK1,
}

# The model returns "W2" (matching FormW2.document_type's own default), but every dispatch
# key elsewhere in the app (RECONCILERS, sample dict, ledgers) uses "W-2". Normalize here
# rather than changing the schema default, and accept a few likely spelling variants too.
_DOC_TYPE_ALIASES = {
    "1099NEC": "1099-NEC",
    "1099MISC": "1099-MISC",
    "W2": "W-2",
    "K1": "K-1",
    "SCHEDULEK1": "K-1",
    "SCHK1": "K-1",
}


def _normalize_doc_type(raw_doc_type) -> str:
    key = str(raw_doc_type or "").strip().upper().replace(" ", "").replace("-", "")
    return _DOC_TYPE_ALIASES.get(key, "")


def _call_claude_vision(base64_image: str) -> dict:
    if not config.ANTHROPIC_API_KEY:
        raise ExtractionError(
            "ANTHROPIC_API_KEY is not set. Add it to your .env file to enable extraction."
        )

    response = litellm.completion(
        model=config.CLAUDE_MODEL,
        api_key=config.ANTHROPIC_API_KEY,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": UNIFIED_EXTRACTION_PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{base64_image}"},
                    },
                ],
            }
        ],
        max_tokens=1024,
    )
    raw_text = response["choices"][0]["message"]["content"]
    return _parse_json_payload(raw_text)


def _parse_json_payload(raw_text: str) -> dict:
    text = raw_text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidate = fenced.group(1) if fenced else text
    brace_match = re.search(r"\{.*\}", candidate, re.DOTALL)
    if brace_match:
        candidate = brace_match.group(0)
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as e:
        raise ExtractionError(f"Model response was not valid JSON: {e}") from e


def extract_and_classify(base64_image: str, timeout: int = config.PROCESSING_TIMEOUT_SECONDS):
    """Run the vision call under a hard timeout, then validate against whichever schema
    matches the model's detected document type.

    Returns (extracted_object, doc_type) where doc_type is the normalized dispatch key
    ("1099-NEC", "1099-MISC", "W-2", or "K-1").
    """
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_call_claude_vision, base64_image)
        try:
            raw_data = future.result(timeout=timeout)
        except concurrent.futures.TimeoutError as e:
            raise ExtractionTimeoutError(
                f"Extraction timed out after {timeout} seconds. Please try again."
            ) from e
        except ExtractionError:
            raise
        except Exception as e:
            raise ExtractionError(f"Claude vision extraction failed: {e}") from e

    doc_type = _normalize_doc_type(raw_data.get("document_type"))
    if doc_type not in SCHEMA_BY_DOC_TYPE:
        raise ExtractionError(
            "Could not identify a supported document type (1099-NEC, 1099-MISC, W-2, or "
            "Schedule K-1) in this file."
        )

    schema_cls = SCHEMA_BY_DOC_TYPE[doc_type]
    try:
        extracted = schema_cls(**raw_data)
    except Exception as e:
        raise ExtractionError(f"Extracted data failed schema validation: {e}") from e

    return extracted, doc_type
