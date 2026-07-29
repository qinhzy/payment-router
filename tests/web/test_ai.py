from __future__ import annotations

import json
from collections.abc import AsyncIterator

import pytest
from fastapi.testclient import TestClient

from payment_router.web.app import create_app

from .test_api import _stub_networks


class FakeExplainer:
    def __init__(self, chunks: list[str] | None = None, error: Exception | None = None) -> None:
        self.chunks = chunks or []
        self.error = error
        self.requests: list[tuple[str, dict[str, object], str]] = []

    @property
    def model(self) -> str:
        return "fake-model"

    async def stream_explanation(
        self,
        kind: str,
        payload: dict[str, object],
        lang: str,
    ) -> AsyncIterator[str]:
        self.requests.append((kind, payload, lang))
        if self.error is not None:
            raise self.error
        for chunk in self.chunks:
            yield chunk


def _client(explainer: FakeExplainer | None) -> TestClient:
    return TestClient(
        create_app(
            networks_factory=_stub_networks,
            explainer_factory=lambda: explainer,
        )
    )


def _events(text: str) -> list[dict[str, object]]:
    return [
        json.loads(line.removeprefix("data: "))
        for line in text.splitlines()
        if line.startswith("data: ")
    ]


def test_meta_reports_ai_disabled_without_explainer() -> None:
    response = _client(None).get("/api/meta")

    assert response.json()["ai"] == {"enabled": False, "model": None}


def test_meta_reports_ai_enabled_with_model() -> None:
    response = _client(FakeExplainer()).get("/api/meta")

    assert response.json()["ai"] == {"enabled": True, "model": "fake-model"}


def test_explain_streams_deltas_and_done_event() -> None:
    explainer = FakeExplainer(chunks=["The balanced ", "route wins."])
    response = _client(explainer).post(
        "/api/explain",
        json={"kind": "decide", "data": {"decisions": []}, "lang": "zh-CN"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = _events(response.text)
    assert events == [
        {"type": "delta", "text": "The balanced "},
        {"type": "delta", "text": "route wins."},
        {"type": "done", "model": "fake-model"},
    ]
    assert explainer.requests == [("decide", {"decisions": []}, "zh-CN")]


def test_explain_reports_stream_errors_as_sse_events() -> None:
    explainer = FakeExplainer(error=RuntimeError("model unavailable"))
    response = _client(explainer).post(
        "/api/explain",
        json={"kind": "route", "data": {"routes": []}},
    )

    assert response.status_code == 200
    events = _events(response.text)
    assert events == [{"type": "error", "message": "model unavailable"}]


def test_explain_returns_503_when_ai_not_configured() -> None:
    response = _client(None).post(
        "/api/explain",
        json={"kind": "route", "data": {}},
    )

    assert response.status_code == 503
    assert "not configured" in response.json()["detail"]


def test_explain_rejects_unknown_kind() -> None:
    response = _client(FakeExplainer()).post(
        "/api/explain",
        json={"kind": "forecast", "data": {}},
    )

    assert response.status_code == 422


class _FakeStream:
    """Stands in for anthropic's streaming context manager."""

    def __init__(self, chunks: list[str], recorder: dict) -> None:
        self._chunks = chunks
        self._recorder = recorder

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info) -> bool:
        self._recorder["closed"] = True
        return False

    @property
    def text_stream(self):
        async def generate():
            for chunk in self._chunks:
                yield chunk

        return generate()


class _FakeMessages:
    def __init__(self, chunks: list[str], recorder: dict) -> None:
        self._chunks = chunks
        self._recorder = recorder

    def stream(self, **kwargs):
        self._recorder["kwargs"] = kwargs
        return _FakeStream(self._chunks, self._recorder)


def _explainer_with(chunks: list[str], recorder: dict):
    from payment_router.web.ai import AIExplainer

    explainer = AIExplainer.__new__(AIExplainer)
    explainer._client = type("C", (), {"messages": _FakeMessages(chunks, recorder)})()
    explainer._model = "test-model"
    return explainer


def test_stream_explanation_sends_the_payload_and_yields_the_text() -> None:
    import asyncio

    recorder: dict = {}
    explainer = _explainer_with(["Take ", "the direct ", "route."], recorder)

    async def collect() -> str:
        return "".join(
            [
                chunk
                async for chunk in explainer.stream_explanation(
                    "compare",
                    {"deltas": {"fee_usd": "0"}, "caveats": ["only FX moved"]},
                    "zh-CN",
                )
            ]
        )

    assert asyncio.run(collect()) == "Take the direct route."
    assert recorder["closed"] is True

    kwargs = recorder["kwargs"]
    assert kwargs["model"] == "test-model"
    message = kwargs["messages"][0]["content"]
    # The model must receive the console's exact JSON, the kind, and the language.
    assert "Response language: zh-CN" in message
    assert "Result kind: compare" in message
    assert '"fee_usd": "0"' in message
    assert "only FX moved" in message


def test_stream_explanation_rejects_an_oversized_payload() -> None:
    import asyncio

    from payment_router.web.ai import ExplainRequestError

    recorder: dict = {}
    explainer = _explainer_with(["ignored"], recorder)

    async def collect() -> None:
        async for _ in explainer.stream_explanation("route", {"blob": "x" * 70_000}, "en"):
            pass

    with pytest.raises(ExplainRequestError):
        asyncio.run(collect())
    assert "kwargs" not in recorder


def test_system_prompt_describes_every_payload_kind_the_app_can_send() -> None:
    """The console sends four kinds; a prompt that names two invites invention."""
    from payment_router.web.ai import SYSTEM_PROMPT
    from payment_router.web.app import ExplainRequest

    kinds = ExplainRequest.model_fields["kind"].annotation.__args__
    for kind in kinds:
        assert f'"{kind}"' in SYSTEM_PROMPT, f"{kind} is undescribed"


def test_system_prompt_forbids_reading_a_comparison_as_an_actual_past_cost() -> None:
    from payment_router.web.ai import SYSTEM_PROMPT

    assert "NOT a reconstruction" in SYSTEM_PROMPT
    assert "authoritative limits" in SYSTEM_PROMPT


def test_system_prompt_describes_regime_boundaries_as_sampled() -> None:
    from payment_router.web.ai import SYSTEM_PROMPT

    assert '"regime"' in SYSTEM_PROMPT
    assert "not exact thresholds" in SYSTEM_PROMPT
    assert "adjacent sampled amounts or weights" in SYSTEM_PROMPT
