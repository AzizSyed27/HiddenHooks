"""
Thin synchronous wrapper around the Anthropic Messages API.

Public surface:
    call_claude(system_prompt, user_message, ...) -> dict | list
    AnthropicAPIError                              (base; HTTP errors, parse failure)
    AnthropicTimeoutError(AnthropicAPIError)       (request timeout specifically)

call_claude returns the JSON-parsed content from Claude's response. All agent prompts
instruct Claude to return a JSON code block and nothing else; this function strips the
markdown fence and parses. On malformed JSON, one repair attempt is made via a fresh
conversation before raising AnthropicAPIError.

The anthropic.Anthropic client is instantiated once at module level on first call and
reused (connection pooling). Thread-safe for single-process uvicorn.

Hygiene:
    - ANTHROPIC_API_KEY is never included in exception messages.
    - Response text in error messages is capped at 200 characters.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Final

import anthropic

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import ANTHROPIC_API_KEY, ANTHROPIC_HTTP_TIMEOUT_SECONDS  # noqa: E402

# Verified alias in anthropic==0.97.0; no dated version exists yet for Sonnet 4.6.
# Re-check: from anthropic.types import Model; print(Model.__args__)
_DEFAULT_MODEL: Final = "claude-sonnet-4-6"

_client: anthropic.Anthropic | None = None


class AnthropicAPIError(Exception):
    """HTTP error, invalid response shape, parse failure, or misconfiguration."""


class AnthropicTimeoutError(AnthropicAPIError):
    """The Anthropic request did not return within the configured timeout."""


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(
            api_key=ANTHROPIC_API_KEY,
            timeout=float(ANTHROPIC_HTTP_TIMEOUT_SECONDS),
        )
    return _client


def _extract_json(text: str) -> dict | list:
    """Extract and parse JSON from a markdown code-fenced or bare response.

    Matches the first code block when multiple are present (first-block-wins).
    """
    match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if match:
        return json.loads(match.group(1))
    return json.loads(text.strip())


def _call_api(
    client: anthropic.Anthropic,
    model: str,
    max_tokens: int,
    temperature: float,
    system: str,
    messages: list[dict],
) -> str:
    """Call the API and return the response text.

    Maps all SDK exception types to AnthropicAPIError / AnthropicTimeoutError.
    """
    try:
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            messages=messages,
        )
        return response.content[0].text
    except anthropic.APITimeoutError as exc:
        raise AnthropicTimeoutError(
            f"Anthropic request timed out after {ANTHROPIC_HTTP_TIMEOUT_SECONDS}s"
        ) from exc
    except anthropic.RateLimitError as exc:
        raise AnthropicAPIError("Anthropic rate limit exceeded") from exc
    except anthropic.AuthenticationError as exc:
        raise AnthropicAPIError("ANTHROPIC_API_KEY was rejected") from exc
    except anthropic.APIStatusError as exc:
        snippet = str(exc.message)[:200] if exc.message else ""
        raise AnthropicAPIError(
            f"Anthropic returned status {exc.status_code}: {snippet}"
        ) from exc
    except anthropic.APIConnectionError as exc:
        raise AnthropicAPIError(
            f"Anthropic connection failed: {type(exc).__name__}"
        ) from exc


def call_claude(
    system_prompt: str,
    user_message: str,
    max_tokens: int = 4096,
    temperature: float = 0.3,
    model: str = _DEFAULT_MODEL,
) -> dict | list:
    """Call Claude and return the parsed JSON from its response.

    Args:
        system_prompt: The agent's role and instructions.
        user_message: Serialized JSON input data for this call.
        max_tokens: Maximum output tokens (default 4096).
        temperature: Sampling temperature (default 0.3).
        model: Claude model ID (default 'claude-sonnet-4-6').

    Returns:
        Parsed JSON — list[dict] for specialist agents, dict for coordinators.

    Raises:
        AnthropicTimeoutError: Request did not complete within ANTHROPIC_HTTP_TIMEOUT_SECONDS.
        AnthropicAPIError: Missing API key, authentication failure, rate limit, HTTP
                           non-2xx, or JSON parse failure after one retry.
    """
    if not ANTHROPIC_API_KEY:
        raise AnthropicAPIError("ANTHROPIC_API_KEY environment variable is not set")

    client = _get_client()

    text = _call_api(
        client, model, max_tokens, temperature,
        system_prompt, [{"role": "user", "content": user_message}],
    )

    try:
        return _extract_json(text)
    except (json.JSONDecodeError, ValueError):
        pass

    # One repair retry: fresh conversation with fix-it instruction appended to user message.
    # Fresh conversation (no prior assistant turn) avoids inheriting a refusal as context.
    retry_user = user_message + "\n\nReturn ONLY a valid JSON code block, no other text."
    try:
        retry_text = _call_api(
            client, model, max_tokens, 0.0,
            system_prompt, [{"role": "user", "content": retry_user}],
        )
        return _extract_json(retry_text)
    except (json.JSONDecodeError, ValueError) as exc:
        snippet = text[:200]
        raise AnthropicAPIError(
            f"Could not parse JSON from Claude response after retry: {snippet}"
        ) from exc
