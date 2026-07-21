"""Claude-powered explanations of routing results.

This is an optional layer of the web console: it only activates when the
``anthropic`` SDK can resolve credentials (``ANTHROPIC_API_KEY``, an
``ant auth login`` profile, …). Every explanation is grounded in the exact
JSON payload the console already displays, and the prompt pins the
teaching-simulator framing so the model never presents figures as live
quotes or financial advice.
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator

DEFAULT_MODEL = "claude-opus-4-8"
MODEL_ENV_VAR = "PAYMENT_ROUTER_AI_MODEL"
MAX_PAYLOAD_CHARS = 60_000

SYSTEM_PROMPT = """\
You explain results from payment-router, a teaching and research simulator for
cross-border payment routing. The user sends you the exact JSON the console is
displaying: either candidate routes ("route") or a cheapest/fastest/balanced
decision board ("decide").

Ground every statement in that JSON. Never invent numbers, providers, or
routes that are not in the data, and never round differently than the data
does. Amounts are strings to preserve precision.

The data carries provenance labels: VERIFIED (read from a live response or a
primary source), INDUSTRY_AVERAGE (documented aggregate), and ESTIMATED
(transparent teaching assumption). Treat ESTIMATED figures as illustrative
scenario values, and say so when they drive the conclusion.

Structure your answer as short paragraphs, in this order:
1. The bottom line: which option you would pick and what the recipient gets.
2. The trade-off that matters most in this data (fees vs. speed vs. amount).
3. One caveat grounded in the provenance labels or provider warnings.

Keep it under 180 words. No headings, no lists unless comparing 3+ options.
This is a simulator for learning: remind the reader once, briefly, that these
are not live quotes and must not be used to initiate a real payment. Respond
in the language identified by the BCP 47 tag in the request (e.g. "zh-CN" is
Simplified Chinese, "en-US" is English).
"""


class ExplainRequestError(ValueError):
    """An explanation request that cannot be fulfilled due to invalid input."""


class AIExplainer:
    """Streams grounded explanations of routing payloads from Claude."""

    def __init__(self, model: str | None = None) -> None:
        import anthropic

        # Zero-arg client: resolves ANTHROPIC_API_KEY, ANTHROPIC_AUTH_TOKEN,
        # or a stored CLI profile. Construction succeeds even without any
        # credential source, so check the resolved slots explicitly.
        self._client = anthropic.AsyncAnthropic()
        if (
            self._client.api_key is None
            and self._client.auth_token is None
            and getattr(self._client, "credentials", None) is None
        ):
            raise RuntimeError("No Anthropic credential source is configured.")
        self._model = model or os.environ.get(MODEL_ENV_VAR) or DEFAULT_MODEL

    @classmethod
    def try_create(cls) -> AIExplainer | None:
        """Build an explainer, or return ``None`` when AI is unavailable."""
        try:
            return cls()
        except Exception:
            return None

    @property
    def model(self) -> str:
        return self._model

    async def stream_explanation(
        self,
        kind: str,
        payload: dict[str, object],
        lang: str,
    ) -> AsyncIterator[str]:
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        if len(serialized) > MAX_PAYLOAD_CHARS:
            raise ExplainRequestError("The routing payload is too large to explain.")

        user_message = (
            f"Response language: {lang}\nResult kind: {kind}\nConsole JSON:\n{serialized}"
        )
        async with self._client.messages.stream(
            model=self._model,
            max_tokens=1500,
            system=SYSTEM_PROMPT,
            thinking={"type": "adaptive"},
            output_config={"effort": "low"},
            messages=[{"role": "user", "content": user_message}],
        ) as stream:
            async for text in stream.text_stream:
                yield text
