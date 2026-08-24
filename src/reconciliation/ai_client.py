"""Thin wrapper around the Gemini API for Layers 3-4.

One deliberate design choice: every call goes through `call_tool`, which
forces a structured JSON response matching a caller-supplied schema (no
free-text parsing) and converts any client error, network failure, timeout,
or malformed response into `LLMCallFailed`. Callers are required to catch
that and degrade gracefully -- this is the "LLM timeout/error falls back
instead of hanging or guessing" failure-handling requirement from CLAUDE.md
section 5, enforced in one place rather than at every call site.

Verified against the real installed `google-genai` SDK (not assumed from
training data, per CLAUDE.md section 6): the client exposes
`client.models.generate_content(...)`, not the `client.interactions.create`
method some AI-generated doc summaries claimed exists -- there is no
`interactions` attribute on the client at all.
"""
from __future__ import annotations

import json
import os
import re
import time

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DEFAULT_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.7-flash")
DEFAULT_TIMEOUT_SECONDS = float(os.environ.get("GEMINI_TIMEOUT_SECONDS", "20"))

# 429 (quota) and 503/504 (transient overload/timeout) are worth a short backoff --
# the free tier's 5-requests/minute cap makes these routine, not a real failure.
# Anything else (400 bad request, 401 auth, a malformed response) is not retried;
# retrying those would just burn time before falling back the same way anyway.
RETRYABLE_STATUS_CODES = {429, 503, 504}
MAX_RETRIES = 3
DEFAULT_RETRY_BACKOFF_SECONDS = 15.0

_client: genai.Client | None = None


class LLMCallFailed(Exception):
    """Raised for any Gemini API error, malformed response, or timeout."""


def get_client() -> genai.Client:
    global _client
    if _client is None:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise LLMCallFailed("GEMINI_API_KEY is not set")
        _client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=int(DEFAULT_TIMEOUT_SECONDS * 1000)),
        )
    return _client


def _retry_delay_seconds(exc: genai_errors.APIError) -> float:
    details = exc.details if isinstance(exc.details, dict) else {}
    for item in details.get("error", {}).get("details", []):
        if str(item.get("@type", "")).endswith("RetryInfo"):
            match = re.match(r"([\d.]+)s", str(item.get("retryDelay", "")))
            if match:
                return float(match.group(1)) + 1.0  # small buffer past what the API asked for
    return DEFAULT_RETRY_BACKOFF_SECONDS


def call_tool(
    *, system_prompt: str, user_prompt: str, tool_name: str,
    tool_description: str, input_schema: dict, model: str = DEFAULT_MODEL,
) -> dict:
    """Force a structured JSON response matching input_schema and return it as a dict.

    tool_name/tool_description are accepted for interface parity with the
    layers' calling code (and because they make the prompt's intent explicit
    in logs) but aren't separate Gemini API parameters -- structured output
    here is schema-constrained generation, not a function-calling round trip.
    """
    response = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            response = get_client().models.generate_content(
                model=model,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    response_mime_type="application/json",
                    response_schema=input_schema,
                ),
            )
            break
        except genai_errors.APIError as exc:
            if exc.code not in RETRYABLE_STATUS_CODES or attempt == MAX_RETRIES:
                raise LLMCallFailed(f"{type(exc).__name__}: {exc}") from exc
            time.sleep(_retry_delay_seconds(exc))
        except Exception as exc:  # noqa: BLE001 - any other SDK/network error must degrade gracefully
            raise LLMCallFailed(f"{type(exc).__name__}: {exc}") from exc

    if not response.text:
        raise LLMCallFailed("Model response had no text content")

    try:
        return json.loads(response.text)
    except json.JSONDecodeError as exc:
        raise LLMCallFailed(f"Model response was not valid JSON: {exc}") from exc
