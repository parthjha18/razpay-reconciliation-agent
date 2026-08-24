"""Thin wrapper around the Claude API for Layers 3-4.

One deliberate design choice: every call goes through `call_tool`, which
forces a structured tool-call response (no free-text parsing) and converts
any client error, network failure, or timeout into `LLMCallFailed`. Callers
are required to catch that and degrade gracefully -- this is the "LLM
timeout/error falls back instead of hanging or guessing" failure-handling
requirement from CLAUDE.md section 5, enforced in one place rather than at
every call site.
"""
from __future__ import annotations

import os

from anthropic import Anthropic

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DEFAULT_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5")
DEFAULT_TIMEOUT_SECONDS = float(os.environ.get("CLAUDE_TIMEOUT_SECONDS", "20"))

_client: Anthropic | None = None


class LLMCallFailed(Exception):
    """Raised for any Claude API error, malformed response, or timeout."""


def get_client() -> Anthropic:
    global _client
    if _client is None:
        _client = Anthropic(timeout=DEFAULT_TIMEOUT_SECONDS)
    return _client


def call_tool(
    *, system_prompt: str, user_prompt: str, tool_name: str,
    tool_description: str, input_schema: dict, model: str = DEFAULT_MODEL,
) -> dict:
    """Force a single structured tool call and return its input dict.

    Raises LLMCallFailed on any error -- network, timeout, API error, or a
    response that doesn't include the requested tool call -- so callers
    always get one clear exception type to catch.
    """
    try:
        response = get_client().messages.create(
            model=model,
            max_tokens=1024,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
            tools=[{
                "name": tool_name,
                "description": tool_description,
                "input_schema": input_schema,
            }],
            tool_choice={"type": "tool", "name": tool_name},
        )
    except Exception as exc:  # noqa: BLE001 - any SDK/network/timeout error must degrade gracefully
        raise LLMCallFailed(f"{type(exc).__name__}: {exc}") from exc

    for block in response.content:
        if block.type == "tool_use" and block.name == tool_name:
            return block.input
    raise LLMCallFailed("Model response did not include the requested tool call")
